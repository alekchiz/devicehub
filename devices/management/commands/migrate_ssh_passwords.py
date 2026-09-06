"""Меняет SSH-пароль ПАК на стандартный и помечает password_migrated.

Запуск:
    python manage.py migrate_ssh_passwords                 # все киоски
    python manage.py migrate_ssh_passwords --limit 10      # первые 10 по номеру
    python manage.py migrate_ssh_passwords --hostname 00044

При смене пароля (ssh_change_password) на киоск дополнительно кладутся
SSH-ключи из DEVICE_SSH_PUBLIC_KEYS.
"""
from django.core.management.base import BaseCommand

from devices.models import Device
from devices.views import ssh_change_password

TARGET = 'Pochta@medQaZ'


class Command(BaseCommand):
    help = 'Меняет SSH-пароль ПАК на стандартный и ставит password_migrated'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0,
                            help='Только первые N киосков по номеру (0 = все)')
        parser.add_argument('--offset', type=int, default=0,
                            help='Пропустить первые N киосков по номеру')
        parser.add_argument('--hostname', default='',
                            help='Обработать только один киоск по номеру')

    def handle(self, *args, **options):
        limit = options['limit']
        offset = options['offset']
        single = options['hostname'].strip()

        qs = (Device.objects.filter(hostname__regex=r'^\d{3,}$')
              .exclude(vpn_ip__in=[None, '', '0', 'N/A'])
              .order_by('hostname'))
        if single:
            qs = qs.filter(hostname__iexact=single)
        else:
            if offset:
                qs = qs[offset:]
            if limit:
                qs = qs[:limit]
        devices = list(qs)

        self.stdout.write(f'Обработать киосков: {len(devices)}')
        done = fail = 0
        skipped = 0
        for d in devices:
            if d.password_migrated:
                skipped += 1
                continue
            ok, msg = ssh_change_password(d, TARGET)
            if ok:
                Device.objects.filter(pk=d.pk).update(
                    ssh_password=TARGET, password_migrated=True)
                done += 1
                self.stdout.write(f'OK   {d.hostname} ({d.vpn_ip})')
            else:
                fail += 1
                self.stdout.write(self.style.WARNING(
                    f'FAIL {d.hostname} ({d.vpn_ip}) -> {msg.strip()[-140:]}'))
        if skipped:
            self.stdout.write(f'Пропущено уже готовых: {skipped}')
        self.stdout.write(self.style.SUCCESS(
            f'Итог: успешно {done}, ошибок {fail}'))
