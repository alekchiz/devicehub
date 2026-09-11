"""Общие утилиты для MQTT-листенеров."""
import logging
import re
import time
from datetime import timedelta

from django.utils import timezone

from devices.models import Device, DeviceEvent, log_device_event
from devices.notifications import notify_device_status

logger = logging.getLogger('devices.mqtt')

# Не сканировать БД на каждое MQTT-сообщение: достаточно раз в интервал.
CHECK_INTERVAL_SECONDS = 10
_last_check = 0.0


def safe_str(value):
    if value is None:
        return ''
    return str(value)


def safe_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def numeric_hostname(host, pattern=r'(\d{3,})'):
    """Извлекает числовой идентификатор киоска из строки хоста."""
    match = re.search(pattern, str(host))
    return match.group(1) if match else str(host)


def check_offline_devices(timeout_minutes=10):
    """Помечает киоска, от которых давно не было MQTT-сообщений, как офлайн."""
    global _last_check
    now = time.time()
    if now - _last_check < CHECK_INTERVAL_SECONDS:
        return
    _last_check = now

    timeout = timezone.now() - timedelta(minutes=timeout_minutes)
    # Киоски в ремонте сознательно оффлайн — не алертим и не трогаем.
    devices = Device.objects.filter(
        is_online=True, in_repair=False, last_mqtt_message__lt=timeout)
    for device in devices:
        device.is_online = False
        device.offline_since = device.last_mqtt_message
        Device.objects.filter(pk=device.pk).update(
            is_online=False, offline_since=device.offline_since)
        log_device_event(device, 'offline', f'Нет связи более {timeout_minutes} мин')
        notify_device_status(device, 'offline', f'Нет связи более {timeout_minutes} мин')
        logger.warning('Оффлайн: %s (%s)', device.hostname, device.vpn_ip)
