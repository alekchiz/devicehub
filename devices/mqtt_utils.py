"""Общие утилиты для MQTT-листенеров."""
import re
from datetime import timedelta

from django.utils import timezone

from devices.models import Device, DeviceEvent, log_device_event
from devices.notifications import notify_device_status


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
    timeout = timezone.now() - timedelta(minutes=timeout_minutes)
    devices = Device.objects.filter(is_online=True, last_mqtt_message__lt=timeout)
    for device in devices:
        device.is_online = False
        device.offline_since = device.last_mqtt_message
        device.save()
        log_device_event(device, 'offline', f'Нет связи более {timeout_minutes} мин')
        notify_device_status(device, 'offline', f'Нет связи более {timeout_minutes} мин')
        print(f"⚠️ Device OFFLINE: {device.hostname}")
