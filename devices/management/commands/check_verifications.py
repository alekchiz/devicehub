from django.core.management.base import BaseCommand

from devices.notifications import run_verification_reminders


class Command(BaseCommand):
    help = 'Напоминания о сроках поверок (скорый/истёкший срок)'

    def handle(self, *args, **options):
        sent = run_verification_reminders()
        self.stdout.write(self.style.SUCCESS(f"Отправлено напоминаний: {sent}"))
