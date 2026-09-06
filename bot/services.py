from django.contrib.auth.models import User
from accounts.models import UserProfile, WhitelistPhone
from tickets.models import Ticket
from devices.models import Device
from django.db.models import Q

def get_profile_sync(telegram_id):
    try:
        profile = UserProfile.objects.select_related('user').get(telegram_id=telegram_id)
        return {
            'username': profile.user.username,
            'role': profile.get_role_display(),
            'role_code': profile.role,
            'user_id': profile.user.id,
            'user': profile.user,
        }
    except UserProfile.DoesNotExist:
        return None

def create_user_sync(username, password, telegram_id, phone):
    user = User.objects.create_user(username=username, password=password)
    user.profile.telegram_id = telegram_id
    user.profile.phone = phone
    user.profile.role = 'technician'
    user.profile.save()
    return {'username': user.username, 'user': user}

def authenticate_user_sync(username, password):
    from django.contrib.auth import authenticate
    return authenticate(username=username, password=password)

def link_telegram_sync(user, telegram_id):
    user.profile.telegram_id = telegram_id
    user.profile.save()

def change_password_sync(telegram_id, current_password, new_password):
    """Меняет пароль привязанного аккаунта. Возвращает (ok, error)."""
    try:
        user = User.objects.select_related('profile').get(profile__telegram_id=telegram_id)
    except User.DoesNotExist:
        return False, 'Аккаунт не привязан к Telegram.'
    if not user.check_password(current_password):
        return False, 'Неверный текущий пароль.'
    if not new_password or len(new_password) < 6:
        return False, 'Пароль слишком короткий. Минимум 6 символов.'
    user.set_password(new_password)
    user.save()
    return True, ''

def is_phone_allowed(phone):
    return WhitelistPhone.objects.filter(phone=phone, is_active=True).exists()

def get_device_by_hostname(hostname):
    try:
        return Device.objects.get(hostname__iexact=hostname)
    except Device.DoesNotExist:
        return None

def create_ticket_sync(hostname, problem, contact_name, contact_phone, user):
    device = Device.objects.get(hostname__iexact=hostname)
    return Ticket.objects.create(
        device=device,
        problem=problem,
        contact_name=contact_name,
        contact_phone=contact_phone,
        created_by=user
    )

def get_my_tickets_sync(user_id):
    return list(Ticket.objects.select_related('device', 'assigned_to', 'created_by').filter(
        Q(created_by_id=user_id) | Q(assigned_to_id=user_id)
    ).distinct().order_by('-created_at'))

def get_all_tickets_sync():
    return list(Ticket.objects.select_related('device', 'assigned_to', 'created_by').all().order_by('-created_at'))

def get_ticket_by_id_sync(ticket_id):
    try:
        return Ticket.objects.select_related('device', 'assigned_to', 'created_by').get(id=ticket_id)
    except Ticket.DoesNotExist:
        return None

def search_tickets_sync(query, user_id=None):
    qs = Ticket.objects.select_related('device', 'assigned_to', 'created_by').filter(
        Q(device__hostname__icontains=query) | Q(problem__icontains=query)
    )
    if user_id:
        qs = qs.filter(Q(created_by_id=user_id) | Q(assigned_to_id=user_id))
    return list(qs.order_by('-created_at')[:10])

def get_admins_sync():
    return list(UserProfile.objects.filter(role='admin'))

def get_menu_stats_sync():
    """Счётчики для шапки главного меню бота."""
    from devices.models import Device
    from tickets.models import Ticket
    base = Device.objects.filter(hostname__regex=r'^\d{3,}$')
    return {
        'online': base.filter(is_online=True, in_repair=False).count(),
        'offline': base.filter(is_online=False, in_repair=False).count(),
        'repair': base.filter(in_repair=True).count(),
        'open': Ticket.objects.filter(status__in=['created', 'in_progress']).count(),
    }


def get_fleet_stats_sync():
    """Развёрнутая статистика по флоту (команда /stats и меню)."""
    from datetime import timedelta

    from django.db.models import Sum
    from django.utils import timezone

    from devices.models import DailyExam, Device, Verification
    from tickets.models import Ticket

    base = Device.objects.filter(hostname__regex=r'^\d{3,}$')
    today = timezone.localdate()
    soon_until = today + timedelta(days=30)
    agg = DailyExam.objects.filter(date=today).aggregate(
        exams=Sum('exams'), cancelled=Sum('cancelled'))

    return {
        'total': base.count(),
        'online': base.filter(is_online=True, in_repair=False).count(),
        'offline': base.filter(is_online=False, in_repair=False).count(),
        'repair': base.filter(in_repair=True).count(),
        'med_ready': base.filter(alco__contains='✅', tonometer__contains='✅').count(),
        'med_total': base.count(),
        'exams': agg['exams'] or 0,
        'cancelled': agg['cancelled'] or 0,
        'verif_soon': Verification.objects.filter(
            status='verified', valid_until__gte=today,
            valid_until__lte=soon_until).count(),
        'verif_expired': Verification.objects.filter(
            status='verified', valid_until__lt=today).count(),
        'open_tickets': Ticket.objects.filter(
            status__in=['created', 'in_progress']).count(),
    }


def update_ticket_sync(ticket_id, problem, contact_name, contact_phone, user):
    try:
        ticket = Ticket.objects.get(id=ticket_id)
        if user.profile.role == 'technician' and ticket.created_by != user:
            return None
        ticket.problem = problem
        ticket.contact_name = contact_name
        ticket.contact_phone = contact_phone
        ticket.save()
        return ticket
    except Ticket.DoesNotExist:
        return None

def can_edit_ticket_sync(ticket_id, user):
    try:
        ticket = Ticket.objects.get(id=ticket_id)
        if user.profile.role == 'admin':
            return True
        if ticket.created_by == user and ticket.status in ['created', 'in_progress']:
            return True
        return False
    except Ticket.DoesNotExist:
        return False
