"""Определяет рабочий SSH-пароль для каждого ПАК (пользователь terminal).

Перебирает по каждому киоску пароли из списка входа (свой у киоска, общий,
резервные из DEVICE_SSH_PASSWORDS) и выводит, какой подошёл. Так как на ПАК
пароль входа и sudo совпадают, найденный пароль подходит и для sudo.

Запуск:
    python manage.py probe_ssh_passwords            # показать, кто каким работает
    python manage.py probe_ssh_passwords --save     # сохранить в Device.ssh_password
    python manage.py probe_ssh_passwords --limit 20 # проверить первые 20 киосков
"""
import subprocess

from django.core.management.base import BaseCommand

from devices.models import Device
from devices.views import _ssh_candidate_passwords, _ssh_args, _ssh_auth_failed


class Command(BaseCommand):
    help = 'Определяет SSH-пароль каждого ПАК перебором списка паролей'

    def add_arguments(self, parser):
        parser.add_argument('--save', action='store_true',
                            help='Сохранить рабочий пароль в Device.ssh_password')
        parser.add_argument('--limit', type=int, default=0,
                            help='Проверить только первые N киосков (0 = все)')

    def handle(self, *args, **options):
        save = options['save']
        limit = options['limit']

        all_devices = (
            Device.objects
            .exclude(vpn_ip__in=[None, '', '0', 'N/A'])
            .order_by('hostname')
        )
        total = all_devices.count()
        devices = all_devices[:limit] if limit else all_devices

        self.stdout.write(f'ПАК для проверки: {devices.count()} (всего с VPN IP: {total})')

        found = 0
        failed = 0
        for device in devices:
            working = self._find_working(device.vpn_ip, _ssh_candidate_passwords(device))
            if working is None:
                failed += 1
                self.stdout.write(self.style.WARNING(
                    f'  {device.hostname:>10}  {device.vpn_ip:<16}  НЕ подключился'
                ))
                continue

            found += 1
            saved = ''
            if save and device.ssh_password != working:
                Device.objects.filter(pk=device.pk).update(ssh_password=working)
                saved = '  [сохранён в киоске]'
            self.stdout.write(f'  {device.hostname:>10}  {device.vpn_ip:<16}  {working}{saved}')

        self.stdout.write(self.style.SUCCESS(
            f'Готово: с рабочим паролем — {found}, без ответа — {failed}'
        ))

    def _find_working(self, vpn_ip, candidates):
        """Пробует каждый пароль входа; возвращает рабочий или None."""
        for pwd in candidates:
            args = _ssh_args(pwd, vpn_ip, 'hostname', 5)
            try:
                result = subprocess.run(args, capture_output=True, text=True, timeout=8)
            except subprocess.TimeoutExpired:
                continue
            if result.returncode == 0 and not _ssh_auth_failed(result):
                return pwd
        return None
