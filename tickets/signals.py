from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.html import escape
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
    
    def _txt(v):
        return escape(str(v)) if v not in (None, '') else '—'

    return (
        f"{emoji} <b>Заявка #{ticket.id}</b>\n"
        f"<code>──────────────────────────────</code>\n"
        f"📦 <b>Киоск:</b> {_txt(ticket.device.hostname)}\n"
        f"📝 <b>Описание:</b> {_txt(ticket.problem)}\n"
        f"👤 <b>Контакт:</b> {_txt(ticket.contact_name)}\n"
        f"📞 <b>Телефон:</b> {_txt(ticket.contact_phone)}\n"
        f"👨‍🔧 <b>Тех. специалист:</b> {_txt(ticket.assigned_to.username if ticket.assigned_to else None)}\n"
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


@receiver(pre_save, sender=Ticket)
def _ticket_snapshot(sender, instance, **kwargs):
    """Запоминает прежние статус и исполнителя, чтобы не логировать лишнего."""
    old = None
    if instance.pk:
        old = Ticket.objects.filter(pk=instance.pk).values(
            'status', 'assigned_to_id').first()
    instance._old_status = old['status'] if old else None
    instance._old_assigned_id = old['assigned_to_id'] if old else None


@receiver(post_save, sender=Ticket)
def ticket_notifications(sender, instance, created, **kwargs):
    if created:
        log_activity(instance, instance.created_by, 'create', f'Создана заявка #{instance.id} на Киоск {instance.device.hostname}')

        admins = UserProfile.objects.filter(role='admin')
        for admin in admins:
            if admin.telegram_id:
                message = "🔔 <b>Новая заявка!</b>\n\n" + format_ticket(instance)
                send_telegram_notification(admin.telegram_id, message)
        return

    assignee = instance.assigned_to
    status_changed = getattr(instance, '_old_status', None) != instance.status
    assigned_changed = getattr(instance, '_old_assigned_id', None) != instance.assigned_to_id

    recipients = []
    if assigned_changed:
        log_activity(instance, assignee or instance.created_by, 'assign',
                     f'Заявка #{instance.id} назначена на {assignee.username if assignee else "—"}')
        if assignee and assignee.profile.telegram_id:
            recipients.append(assignee.profile.telegram_id)
        if instance.created_by and instance.created_by.profile.telegram_id:
            recipients.append(instance.created_by.profile.telegram_id)
    elif status_changed:
        log_activity(instance, assignee or instance.created_by, 'status_change',
                     f'Заявка #{instance.id} → "{instance.get_status_display()}"')
        if instance.created_by and instance.created_by.profile.telegram_id:
            recipients.append(instance.created_by.profile.telegram_id)
        if (assignee and assignee.profile.telegram_id
                and (not instance.created_by or assignee.id != instance.created_by.id)):
            recipients.append(assignee.profile.telegram_id)

    for tid in dict.fromkeys(recipients):
        message = "📋 <b>Заявка обновлена</b>\n\n" + format_ticket(instance)
        send_telegram_notification(tid, message)
