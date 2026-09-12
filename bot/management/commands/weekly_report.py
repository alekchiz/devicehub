from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from devices.models import Device, Repair
from tickets.models import Ticket
from accounts.models import UserProfile
from devices.notifications import send_telegram

class Command(BaseCommand):
    help = 'Еженедельная сводка'
    
    def handle(self, *args, **options):
        week_ago = timezone.now() - timedelta(days=7)

        # Киоски в ремонте вынесены из сводки (как в daily_report).
        scope = Device.objects.filter(is_standard=True, in_repair=False)
        total = scope.count()
        online = scope.filter(is_online=True).count()
        offline = total - online
        
        repairs = Repair.objects.filter(created_at__gte=week_ago).count()
        tickets = Ticket.objects.filter(created_at__gte=week_ago).count()
        
        message = (
            f"📊 <b>Еженедельная сводка</b>\n"
            f"<code>──────────────────────</code>\n\n"
            f"🖥 Киоски: {total} всего\n"
            f"  🟢 Онлайн: {online}\n"
            f"  🔴 Оффлайн: {offline}\n\n"
            f"🔧 Ремонтов за неделю: {repairs}\n"
            f"📋 Заявок за неделю: {tickets}\n"
        )
        
        recipients = UserProfile.objects.filter(notify_weekly_report=True, telegram_id__isnull=False)
        n_recipients = recipients.count()
        for up in recipients:
            send_telegram(up.telegram_id, message)

        self.stdout.write(self.style.SUCCESS(f'Сводка отправлена {n_recipients} пользователям'))
