"""Telegram-уведомления о смене статуса Киоск.

Получателей выбирает админ: в профиле пользователя (UserProfile) нужно включить
"Уведомлять о падении Киоск" и/или "Уведомлять о возврате Киоск" и указать telegram_id.
"""
import logging
import requests
from django.utils.html import escape

from django.conf import settings

from accounts.models import UserProfile

logger = logging.getLogger('devices.notifications')


def send_telegram(telegram_id, message):
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {'chat_id': telegram_id, 'text': message, 'parse_mode': 'HTML'}
    proxies = None
    proxy = getattr(settings, 'TELEGRAM_PROXY', '')
    if proxy:
        proxies = {'http': proxy, 'https': proxy}
    try:
        resp = requests.post(url, data=data, timeout=10, proxies=proxies)
        return resp.ok
    except Exception as e:
        logger.error('Telegram send error: %s', e)
        return False


def notify_device_status(device, event, message=''):
    """Слает уведомление выбранным получателям о переходе Киоск онлайн/оффлайн."""
    flag = 'notify_device_offline' if event == 'offline' else 'notify_device_online'
    recipients = (
        UserProfile.objects
        .filter(**{flag: True})
        .exclude(telegram_id__isnull=True)
    )

    if event == 'offline':
        text = (f"🚨 <b>Киоск оффлайн</b>\n"
                f"Киоск: <b>{escape(device.hostname)}</b>\n"
                f"{escape(message)}")
    else:
        text = (f"✅ <b>Киоск вернулся онлайн</b>\n"
                f"Киоск: <b>{escape(device.hostname)}</b>\n"
                f"{escape(message)}")

    for profile in recipients:
        send_telegram(profile.telegram_id, text)


def notify_verification_expiry(verification):
    """Шлёт выбранным получателям напоминание о скором/истёкшем сроке поверки."""
    recipients = (
        UserProfile.objects
        .filter(notify_verification_expiry=True)
        .exclude(telegram_id__isnull=True)
    )

    state = verification.expiry_state
    if state not in ('soon', 'expired'):
        return

    if state == 'expired':
        head = "🚨 <b>Поверка истекла</b>"
    else:
        head = "⚠️ <b>Скоро истекает поверка</b>"

    text = (
        f"{head}\n"
        f"Оборудование: <b>{escape(verification.get_equipment_type_display())}</b>"
        f"{' на киоске ' + escape(verification.device.hostname) if verification.device else ''}\n"
        f"Действует до: <b>{verification.valid_until:%d.%m.%Y}</b>"
    )

    for profile in recipients:
        send_telegram(profile.telegram_id, text)


def run_verification_reminders():
    """Сканирует поверки и шлёт напоминания о скором/истёкшем сроке (не чаще раза)."""
    from devices.models import Verification

    verifications = (
        Verification.objects
        .filter(status='verified', valid_until__isnull=False)
        .select_related('device')
    )
    sent = 0
    for verification in verifications:
        state = verification.expiry_state
        if state in ('soon', 'expired') and verification.reminded_for != state:
            notify_verification_expiry(verification)
            verification.reminded_for = state
            verification.save(update_fields=['reminded_for'])
            sent += 1
    return sent
