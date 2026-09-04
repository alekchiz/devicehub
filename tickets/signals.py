from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Ticket, ActivityLog
from django.conf import settings
import urllib.request
import json
from django.utils import timezone
from accounts.models import UserProfile

def send_telegram_notification(telegram_id, message):
    try:
        token = settings.TELEGRAM_BOT_TOKEN
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({
            'chat_id': telegram_id,
            'text': message,
            'parse_mode': 'HTML'
        }).encode('utf-8')
        
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")

def format_ticket(ticket):
    status_emoji = {
        'created': '🆕',
        'in_progress': '🔧',
        'completed': '✅',
        'closed': '🔒'
    }
    
    emoji = status_emoji.get(ticket.status, '❓')
    now = timezone.now()
    
    if ticket.created_at:
        delta = now - ticket.created_at
        hours, rem = divmod(delta.seconds, 3600)
        mins = rem // 60
        if delta.days > 0:
            work_time = f"{delta.days} дн. назад"
        elif hours > 0:
            work_time = f"{hours} ч. назад"
        else:
            work_time = f"{mins} мин. назад"
    else:
        work_time = "—"
    
    return (
        f"{emoji} <b>Заявка #{ticket.id}</b>\n"
        f"<code>──────────────────────────────</code>\n"
        f"📦 <b>Киоск:</b> {ticket.device.hostname}\n"
        f"📝 <b>Описание:</b> {ticket.problem}\n"
        f"👤 <b>Контакт:</b> {ticket.contact_name}\n"
        f"📞 <b>Телефон:</b> {ticket.contact_phone}\n"
        f"👨‍🔧 <b>Тех. специалист:</b> {ticket.assigned_to.username if ticket.assigned_to else 'Не назначен'}\n"
        f"🔄 <b>Статус:</b> {emoji} {ticket.get_status_display()}\n"
        f"📅 <b>Создана:</b> {ticket.created_at.strftime('%d.%m.%Y %H:%M') if ticket.created_at else '—'} МСК\n"
        f"⏱️ <b>В работе:</b> {work_time}"
    )

def log_activity(ticket, user, action, description):
    ActivityLog.objects.create(
        user=user,
        action=action,
        model_name='Ticket',
        object_id=ticket.id,
        description=description
    )

@receiver(post_save, sender=Ticket)
def ticket_notifications(sender, instance, created, **kwargs):
    if created:
        # Лог
        log_activity(instance, instance.created_by, 'create', f'Создана заявка #{instance.id} на Киоск {instance.device.hostname}')
        
        # Уведомляем админов
        admins = UserProfile.objects.filter(role='admin')
        for admin in admins:
            if admin.telegram_id:
                message = "🔔 <b>Новая заявка!</b>\n\n" + format_ticket(instance)
                send_telegram_notification(admin.telegram_id, message)
    else:
        # Определяем что изменилось
        if instance.assigned_to and instance.status == 'in_progress':
            log_activity(instance, instance.assigned_to, 'assign', f'Заявка #{instance.id} назначена на {instance.assigned_to.username}')
        
        if instance.status in ['completed', 'closed']:
            log_activity(instance, instance.assigned_to or instance.created_by, 'status_change', f'Заявка #{instance.id} переведена в статус "{instance.get_status_display()}"')
        
        # Уведомления
        if instance.assigned_to and instance.assigned_to.profile.telegram_id:
            message = "📋 <b>Заявка обновлена</b>\n\n" + format_ticket(instance)
            send_telegram_notification(instance.assigned_to.profile.telegram_id, message)
        
        if instance.created_by and instance.created_by.profile.telegram_id:
            if instance.created_by != instance.assigned_to:
                message = "📋 <b>Статус вашей заявки изменён</b>\n\n" + format_ticket(instance)
                send_telegram_notification(instance.created_by.profile.telegram_id, message)
