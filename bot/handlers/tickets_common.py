"""Общие константы, форматирование и DB-обёртки для обработчиков заявок."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from asgiref.sync import sync_to_async
from bot.services import (
    get_profile_sync, create_ticket_sync, get_my_tickets_sync,
    get_all_tickets_sync, get_admins_sync, get_device_by_hostname,
    get_ticket_by_id_sync, search_tickets_sync,
    update_ticket_sync, can_edit_ticket_sync
)
from devices.models import Device, Repair
from tickets.models import Ticket
from django.utils import timezone

TICKET_PAK = 1
TICKET_PROBLEM = 2
TICKET_NAME = 3
TICKET_PHONE = 4
SEARCH_QUERY = 5
EDIT_TICKET_SELECT = 6
EDIT_TICKET_FIELD = 7
EDIT_TICKET_PROBLEM = 8
EDIT_TICKET_NAME = 9
EDIT_TICKET_PHONE = 10
STATUS_HOSTNAME = 11

STATUS_EMOJI = {
    'created': '🆕',
    'in_progress': '🔧',
    'completed': '✅',
    'closed': '🔒',
}

def format_ticket_message(ticket):
    emoji = STATUS_EMOJI.get(ticket.status, '❓')
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

def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 В главное меню", callback_data='menu')]
    ])


@sync_to_async
def get_profile(telegram_id):
    return get_profile_sync(telegram_id)

@sync_to_async
def find_device(hostname):
    return get_device_by_hostname(hostname)

@sync_to_async
def create_ticket(hostname, problem, contact_name, contact_phone, user):
    return create_ticket_sync(hostname, problem, contact_name, contact_phone, user)

@sync_to_async
def get_my_tickets(user_id):
    return get_my_tickets_sync(user_id)

@sync_to_async
def get_all_tickets():
    return get_all_tickets_sync()

@sync_to_async
def get_admins():
    return get_admins_sync()

@sync_to_async
def get_ticket(ticket_id):
    return get_ticket_by_id_sync(ticket_id)

@sync_to_async
def search_tickets(query, user_id=None):
    return search_tickets_sync(query, user_id)

@sync_to_async
def update_ticket(ticket_id, problem, contact_name, contact_phone, user):
    return update_ticket_sync(ticket_id, problem, contact_name, contact_phone, user)

@sync_to_async
def can_edit_ticket(ticket_id, user):
    return can_edit_ticket_sync(ticket_id, user)

@sync_to_async
def get_device_full(hostname):
    try:
        device = Device.objects.select_related('owner', 'location', 'client', 'contact').get(hostname__iexact=hostname)
        tickets = list(Ticket.objects.filter(device=device).order_by('-created_at')[:3])
        repairs = list(Repair.objects.filter(device=device).order_by('-created_at')[:3])
        return {
            'found': True,
            'hostname': device.hostname,
            'vpn_ip': device.vpn_ip,
            'anydesk': device.anydesk,
            'software': device.software,
            'os': device.os,
            'is_online': device.is_online,
            'in_repair': device.in_repair,
            'offline_duration': device.offline_duration,
            'last_mqtt': device.last_mqtt_message,
            'alco': device.alco,
            'tonometer': device.tonometer,
            'owner': device.owner.name if device.owner else None,
            'location': device.location.name if device.location else None,
            'tickets': tickets,
            'repairs': repairs,
        }
    except Device.DoesNotExist:
        return {'found': False}