from django.db import migrations
from django.db.models import F


def move_temperature_to_cpu(apps, schema_editor):
    """Исторически в поле temperature клиент слал температуру CPU.
    Переносим её в cpu_temperature и очищаем temperature (детектор термометра
    больше не должен считать это показанием мед.термометра)."""
    Device = apps.get_model('devices', 'Device')
    Device.objects.filter(temperature__gt='', cpu_temperature='').update(
        cpu_temperature=F('temperature'),
        temperature='',
    )


def restore_temperature(apps, schema_editor):
    Device = apps.get_model('devices', 'Device')
    Device.objects.filter(cpu_temperature__gt='', temperature='').update(
        temperature=F('cpu_temperature'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('devices', '0010_device_cpu_temperature'),
    ]

    operations = [
        migrations.RunPython(move_temperature_to_cpu, restore_temperature),
    ]
