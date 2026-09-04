import json
import paho.mqtt.client as mqtt
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from devices.models import Device
from devices.mqtt_utils import safe_str, safe_float, numeric_hostname, check_offline_devices

# Локальный/отладочный листенер. Основной — mqtt_listener2.
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_USER = settings.MQTT_USER
MQTT_PASS = settings.MQTT_PASS
MQTT_TOPIC = "client/status"
OFFLINE_TIMEOUT = 10

def on_connect(client, userdata, flags, rc):
    print(f"MQTT connected to {MQTT_BROKER} with result code {rc}")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        host = payload.get('host')
        if not host:
            return

        host = numeric_hostname(host, pattern=r'(\d{3})')

        now = timezone.now()

        defaults = {
            'vpn_ip': safe_str(payload.get('vpn_ip', '')) or None,
            'kernel': safe_str(payload.get('kernel', '')),
            'x11vnc': safe_str(payload.get('x11vnc', '')),
            'alco': safe_str(payload.get('alco', '')),
            'tonometer': safe_str(payload.get('tonometer', '')),
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
            'uptime_formatted': safe_str(payload.get('uptime_info', '')),
            'secureboot': safe_str(payload.get('secureboot', '')),
            'broker': 'support-pak.ru',
            'last_mqtt_message': now,
            'is_online': True,
            'offline_since': None,
        }

        device, created = Device.objects.update_or_create(
            hostname=host,
            defaults={k: v for k, v in defaults.items() if v is not None}
        )

        status = "Created" if created else "Updated"
        print(f"✅ {status} device: {host} | online | cpu={defaults.get('cpu_load', '?')}% | ram={defaults.get('memory_percent', '?')}% | disk={defaults.get('hdd_percent', '?')}%")

        check_offline_devices(OFFLINE_TIMEOUT)

    except Exception as e:
        print(f"❌ MQTT message processing error: {e}")

class Command(BaseCommand):
    help = 'Listen MQTT topics and update devices'

    def handle(self, *args, **options):
        check_offline_devices(OFFLINE_TIMEOUT)

        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message
        client.username_pw_set(MQTT_USER, MQTT_PASS)

        print(f"🚀 Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        print(f"🚀 MQTT listener started (offline timeout: {OFFLINE_TIMEOUT} min)")

        client.loop_forever()