"""Расчёт доступности (uptime) киосков из истории событий."""
from django.utils import timezone

from devices.models import DeviceEvent

# События, определяющие состояние «онлайн/оффлайн» для расчёта доступности.
_STATE_EVENTS = {'online', 'offline', 'created'}


def device_uptime(device, start, end):
    """Доля времени online в [start, end) по событиям, 0.0..1.0.

    Начальное состояние на момент start определяется последним событием
    до start; далее состояние переключается по событиям внутри периода.
    """
    if start >= end:
        return 0.0

    # Последнее событие, случившееся до начала периода, задаёт исходное состояние.
    last_before = (
        DeviceEvent.objects
        .filter(device=device, event__in=_STATE_EVENTS, created_at__lt=start)
        .order_by('-created_at')
        .values_list('event', flat=True)
        .first()
    )
    state = 'online' if last_before == 'online' else 'offline'

    events = (
        DeviceEvent.objects
        .filter(device=device, event__in=_STATE_EVENTS,
                created_at__gte=start, created_at__lt=end)
        .order_by('created_at')
        .values_list('created_at', 'event')
    )

    online_seconds = 0.0
    cursor = start
    for ts, event in events:
        if timezone.is_naive(ts):
            ts = timezone.make_aware(ts)
        if ts > cursor:
            if state == 'online':
                online_seconds += (ts - cursor).total_seconds()
            cursor = ts
        state = 'offline' if event == 'created' else ('online' if event == 'online' else 'offline')

    if state == 'online' and end > cursor:
        online_seconds += (end - cursor).total_seconds()

    total = (end - start).total_seconds()
    if total <= 0:
        return 0.0
    return online_seconds / total
