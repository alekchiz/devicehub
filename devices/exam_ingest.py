"""Загрузка снимков осмотров ПАК за сутки из MQTT (topic *…*/day/YYYY-MM-DD)."""
import re
from datetime import datetime

from django.db.models import Max
from django.utils import timezone

from .models import Device, Client, Location, DailyExam


def extract_day_date(topic):
    """Достаёт дату из топика вида …*/day/YYYY-MM-DD."""
    m = re.search(r'/day/(\d{4}-\d{2}-\d{2})$', topic or '')
    return m.group(1) if m else None


def _parse_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def ingest_day_snapshot(payload, topic_date=None):
    """Сохраняет суточный снимок осмотров. Дата берётся из payload или топика.

    Сопоставление киоска по hostname/SN; при отсутствии киоск создаётся.
    Обновляет объект/расположение из данных ПАК и exam_count последней даты.
    Возвращает число обработанных киосков.
    """
    if not isinstance(payload, dict):
        return 0

    date_str = payload.get('date') or topic_date
    if not date_str:
        return 0
    try:
        day = datetime.strptime(str(date_str), '%Y-%m-%d').date()
    except ValueError:
        return 0

    count = 0
    for item in payload.get('items') or []:
        if not isinstance(item, dict):
            continue
        sn = item.get('sn')
        if sn is None:
            continue
        sn = str(sn).strip()
        if not sn:
            continue

        device = (Device.objects.filter(hostname__iexact=sn).first()
                  or Device.objects.filter(sn__iexact=sn).first())
        if not device:
            device = Device.objects.create(hostname=sn)

        exams = _parse_int(item.get('exams'))
        cancelled = _parse_int(item.get('cancelled'))
        client_name = (item.get('client') or '').strip()
        orgunit = (item.get('orgunit') or '').strip()
        last_exam = _parse_datetime(item.get('last_exam'))

        DailyExam.objects.update_or_create(
            device=device,
            date=day,
            defaults={
                'exams': exams,
                'cancelled': cancelled,
                'group': (item.get('group') or '').strip(),
                'client': client_name,
                'orgunit': orgunit,
                'last_exam': last_exam,
            },
        )

        update_fields = []
        if client_name:
            client, _ = Client.objects.get_or_create(name=client_name)
            if device.client_id != client.pk:
                device.client = client
                update_fields.append('client')
        if orgunit:
            location, _ = Location.objects.get_or_create(name=orgunit)
            if device.location_id != location.pk:
                device.location = location
                update_fields.append('location')

        max_day = device.daily_exams.aggregate(m=Max('date'))['m']
        if max_day is None or day >= max_day:
            if device.exam_count != exams:
                device.exam_count = exams
                update_fields.append('exam_count')

        if update_fields:
            device.save(update_fields=update_fields)
        count += 1

    return count
