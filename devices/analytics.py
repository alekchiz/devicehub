"""Расчёт доступности (uptime) киосков из истории событий."""
from collections import defaultdict

from django.utils import timezone

from devices.models import DeviceEvent

# События, определяющие состояние «онлайн/оффлайн» для расчёта доступности.
_STATE_EVENTS = {'online', 'offline', 'created'}


def _merge_uptime(state, events, start, end):
    """Доля времени online по событиям (список (ts, event)), 0.0..1.0."""
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


def device_uptime(device, start, end):
    """Доля времени online в [start, end) для одного киоска, 0.0..1.0."""
    if start >= end:
        return 0.0
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
    return _merge_uptime(state, events, start, end)


def devices_uptime(device_ids, start, end):
    """Доли online для набора киосков двумя запросами вместо 2 запросов на киоск."""
    out = {i: 0.0 for i in device_ids}
    if not device_ids or start >= end:
        return out

    last_before = {}
    seen = set()
    for did, event in (
        DeviceEvent.objects
        .filter(device_id__in=device_ids,
                event__in=_STATE_EVENTS, created_at__lt=start)
        .order_by('-created_at')
        .values_list('device_id', 'event')
    ):
        if did in seen:
            continue
        seen.add(did)
        last_before[did] = event

    by_device = defaultdict(list)
    for did, ts, event in (
        DeviceEvent.objects
        .filter(device_id__in=device_ids,
                event__in=_STATE_EVENTS,
                created_at__gte=start, created_at__lt=end)
        .order_by('device_id', 'created_at')
        .values_list('device_id', 'created_at', 'event')
    ):
        by_device[did].append((ts, event))

    for did in device_ids:
        state = 'online' if last_before.get(did) == 'online' else 'offline'
        out[did] = _merge_uptime(state, by_device.get(did, []), start, end)
    return out
