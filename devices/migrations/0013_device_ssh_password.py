from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('devices', '0012_device_exam_count'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='ssh_password',
            field=models.CharField(blank=True, max_length=100, verbose_name='SSH пароль'),
        ),
    ]
