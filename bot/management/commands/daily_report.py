from django.core.management.base import BaseCommand
from django.utils import timezone
from devices.models import Device
from tickets.models import Ticket
from accounts.models import UserProfile
from devices.notifications import send_telegram

class Command(BaseCommand):
    help = 'Ежедневная сводка для наблюдателей и админов'

    def handle(self, *args, **options):
        now = timezone.now()
        
        # Статистика
        total = Device.objects.count()
        online = Device.objects.filter(is_online=True, in_repair=False).count()
        offline = Device.objects.filter(is_online=False, in_repair=False).count()
        in_repair = Device.objects.filter(in_repair=True).count()
        
        # Заявки
        open_tickets = Ticket.objects.filter(status__in=['created', 'in_progress']).count()
        today_tickets = Ticket.objects.filter(created_at__date=now.date()).count()
        
        # Оффлайн Киоски
        offline_devices = Device.objects.filter(is_online=False, in_repair=False)[:10]
        
        message = (
            f"📊 <b>Сводка МедКиоск</b>\n"
            f"📅 {now.strftime('%d.%m.%Y %H:%M')}\n"
            f"<code>──────────────────────────────</code>\n\n"
            f"🖥 <b>Киоски:</b>\n"
            f"  Всего: {total}\n"
            f"  🟢 Онлайн: {online}\n"
            f"  🔴 Оффлайн: {offline}\n"
            f"  🟡 В ремонте: {in_repair}\n\n"
            f"📋 <b>Заявки:</b>\n"
            f"  Открыто: {open_tickets}\n"
            f"  За сегодня: {today_tickets}\n"
        )
        
        if offline_devices:
            message += f"\n🔴 <b>Оффлайн Киоски:</b>\n"
            for d in offline_devices:
                duration = d.offline_duration or '?'
                message += f"  • {d.hostname} ({d.vpn_ip or 'нет IP'}) — {duration}\n"
        
        # Отправляем наблюдателям и админам
        recipients = UserProfile.objects.filter(role__in=['admin', 'observer'])
        sent = 0
        for user_profile in recipients:
            if user_profile.telegram_id:
                if send_telegram(user_profile.telegram_id, message):
                    sent += 1
        
        self.stdout.write(self.style.SUCCESS(f'✅ Сводка отправлена {sent} пользователям (наблюдатели + админы)'))
