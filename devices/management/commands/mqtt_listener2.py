import json
import logging
import time
import paho.mqtt.client as mqtt
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from devices.models import Device
from devices.models import log_device_event
from devices.notifications import notify_device_status, run_verification_reminders
from devices.mqtt_utils import safe_str, safe_float, numeric_hostname, check_offline_devices
from devices.exam_ingest import extract_day_date, ingest_day_snapshot

logger = logging.getLogger('devices.mqtt')

MQTT_BROKER = settings.MQTT_BROKER
MQTT_PORT = settings.MQTT_PORT
MQTT_USER = settings.MQTT_USER
MQTT_PASS = settings.MQTT_PASS
MQTT_TOPIC = settings.MQTT_TOPIC
OFFLINE_TIMEOUT = 10

DAY_BROKER = getattr(settings, 'MQTT_DAY_BROKER', '')
DAY_PORT = int(getattr(settings, 'MQTT_DAY_PORT', MQTT_PORT))
DAY_USER = getattr(settings, 'MQTT_DAY_USER', '') or MQTT_USER
DAY_PASS = getattr(settings, 'MQTT_DAY_PASS', '') or MQTT_PASS
DAY_TOPICS = [t.strip() for t in
              getattr(settings, 'MQTT_DAY_TOPICS', 'pak/day,client/day').split(',') if t.strip()]


def on_day_connect(client, userdata, flags, rc):
    logger.info('Day-broker connected (%s), rc=%s', DAY_BROKER, rc)
    if rc != 0:
        logger.warning('Day-broker connection refused (rc=%s)', rc)
        return
    for topic in DAY_TOPICS:
        client.subscribe(f"{topic}/+")


def on_day_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        day_date = extract_day_date(msg.topic)
        processed = ingest_day_snapshot(payload, day_date)
        logger.info('EXAM_DAY %s: %s paks', day_date, processed)
    except Exception as e:
        logger.error('Day MQTT error: %s', e)


def on_connect(client, userdata, flags, rc):
    logger.info('MQTT connected to %s, rc=%s', MQTT_BROKER, rc)
    if rc != 0:
        logger.warning('MQTT connection refused (rc=%s)', rc)
        return
    for topic in [t.strip() for t in MQTT_TOPIC.split(',') if t.strip()]:
        client.subscribe(topic)

def on_message(client, userdata, msg):
    try:
        if 'sensors' in msg.topic:
            return

        payload = json.loads(msg.payload.decode('utf-8'))

        # Суточный снимок осмотров: …*/day/YYYY-MM-DD
        day_date = extract_day_date(msg.topic)
        if day_date:
            # Суточные снимки обрабатывает выделенный day-клиент (он подписан
            # на конкретные топики). Здесь — только если day-брокера нет.
            if not DAY_BROKER:
                processed = ingest_day_snapshot(payload, day_date)
                logger.info('EXAM_DAY %s: %s paks', day_date, processed)
            return

        host = safe_str(payload.get('host') or payload.get('hostname') or '')
        host = numeric_hostname(host)
        if not host:
            logger.warning('Пропуск сообщения без hostname: %s', msg.topic)
            return

        now = timezone.now()

        defaults = {
            'vpn_ip': safe_str(payload.get('vpn_ip', '')) or None,
            'kernel': safe_str(payload.get('kernel', '')),
            'x11vnc': safe_str(payload.get('x11vnc', '')),
            'alco': safe_str(payload.get('alco', '')),
            'tonometer': safe_str(payload.get('tonometer', '')),
            'alco_enabled': payload.get('alco_enabled'),
            'tonometer_enabled': payload.get('tonometer_enabled'),
            'thermometer_enabled': payload.get('thermometer_enabled'),
            'software': safe_str(payload.get('software', '')),
            'network_speed': safe_str(payload.get('network_speed', '')),
            'uptime': safe_str(payload.get('uptime', '')),
            'hdd': safe_float(payload.get('hdd')),
            'hdd_total': safe_float(payload.get('hdd_total')),
            'hdd_percent': safe_float(payload.get('hdd_percent')),
            'anydesk': safe_str(payload.get('anydesk', '')),
            'sn': safe_str(payload.get('sn', '')),
            'os': safe_str(payload.get('os', '')),
            'ver': safe_str(payload.get('ver', '')),
            'cpu_load': safe_float(payload.get('cpu_load')),
            'memory_percent': safe_float(payload.get('memory_percent')),
            'temperature': safe_str(payload.get('temperature', '')),
            'cpu_temperature': safe_str(payload.get('cpu_temperature', '')),
            'uptime_formatted': safe_str(payload.get('uptime_info', '')),
            'secureboot': safe_str(payload.get('secureboot', '')),
            'broker': MQTT_BROKER,
            'last_mqtt_message': now,
            'is_online': True,
            'offline_since': None,
        }

        previous = Device.objects.filter(hostname=host).values('is_online').first()

        device, created = Device.objects.update_or_create(
            hostname=host,
            defaults={k: v for k, v in defaults.items() if v is not None}
        )

        if created:
            log_device_event(device, 'created', 'Киоск впервые прислало данные')
        elif previous and not previous['is_online']:
            log_device_event(device, 'online', 'Связь восстановлена')
            notify_device_status(device, 'online', 'Связь восстановлена')

        status = "Created" if created else "Updated"
        logger.info('%s device: %s | online | cpu=%s%% | ram=%s%% | disk=%s%%',
                    status, host, defaults.get('cpu_load', '?'),
                    defaults.get('memory_percent', '?'), defaults.get('hdd_percent', '?'))

        check_offline_devices(OFFLINE_TIMEOUT)

    except Exception as e:
        logger.error('MQTT message processing error: %s', e)

class Command(BaseCommand):
    help = f'Listen MQTT topics from broker {MQTT_BROKER}'

    def handle(self, *args, **options):
        check_offline_devices(OFFLINE_TIMEOUT)
        # Один раз при старте проверяем, не подошли ли сроки поверок.
        run_verification_reminders()

        day_client = None
        if DAY_BROKER:
            day_client = mqtt.Client()
            day_client.on_connect = on_day_connect
            day_client.on_message = on_day_message
            day_client.username_pw_set(DAY_USER, DAY_PASS)
            logger.info('Day-broker: connecting to %s:%s (topics: %s)',
                        DAY_BROKER, DAY_PORT, ', '.join(DAY_TOPICS))
            while True:
                try:
                    day_client.connect(DAY_BROKER, DAY_PORT, 30)
                    break
                except Exception as e:
                    logger.warning('Day-broker connect failed: %s; retry in 5s', e)
                    time.sleep(5)
            day_client.loop_start()

        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message
        client.username_pw_set(MQTT_USER, MQTT_PASS)

        logger.info('Connecting to %s:%s...', MQTT_BROKER, MQTT_PORT)
        while True:
            try:
                client.connect(MQTT_BROKER, MQTT_PORT, 30)
                break
            except Exception as e:
                logger.warning('MQTT connect failed: %s; retry in 5s', e)
                time.sleep(5)
        logger.info('MQTT listener started (offline timeout: %s min)', OFFLINE_TIMEOUT)

        client.loop_forever()
