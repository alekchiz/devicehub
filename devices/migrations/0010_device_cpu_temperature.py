from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('devices', '0009_verification_device_verification_reminded_for_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='cpu_temperature',
            field=models.CharField(blank=True, max_length=20, verbose_name='Температура CPU'),
        ),
    ]
