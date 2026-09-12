"""Загрузка снимков осмотров ПАК за сутки из MQTT (topic *…*/day/YYYY-MM-DD)."""
import re
from datetime import datetime

from django.db import IntegrityError, transaction

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
    with transaction.atomic():
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
                # Гонка: два потока (основной и day-клиент) могут одновременно
                # не найти киоск. Повторяем попытку с учётом IntegrityError.
                try:
                    with transaction.atomic():
                        device = Device.objects.create(hostname=sn)
                except IntegrityError:
                    device = Device.objects.filter(hostname__iexact=sn).first()
                    if not device:
                        continue

            client_name = (item.get('client') or '').strip()
            orgunit = (item.get('orgunit') or '').strip()
            last_exam = _parse_datetime(item.get('last_exam'))

            # exams/cancelled пишем только если поле реально пришло: иначе
            # частичный payload обнулял бы ранее сохранённые значения.
            defaults = {
                'group': (item.get('group') or '').strip(),
                'client': client_name,
                'orgunit': orgunit,
                'last_exam': last_exam,
            }
            if 'exams' in item:
                defaults['exams'] = _parse_int(item['exams'])
            if 'cancelled' in item:
                defaults['cancelled'] = _parse_int(item['cancelled'])

            DailyExam.objects.update_or_create(
                device=device,
                date=day,
                defaults=defaults,
            )

            # exam_count = осмотры последней даты киоска (того же дня).
            if 'exams' in defaults:
                latest = device.daily_exams.order_by('-date').values_list('date', flat=True).first()
                if latest is not None and latest == day and device.exam_count != defaults['exams']:
                    device.exam_count = defaults['exams']
                    Device.objects.filter(pk=device.pk).update(exam_count=defaults['exams'])

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

            if update_fields:
                device.save(update_fields=update_fields)
            count += 1

    return count
