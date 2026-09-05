from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('devices', '0011_move_temperature_to_cpu'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='exam_count',
            field=models.IntegerField(blank=True, null=True, verbose_name='Количество осмотров'),
        ),
    ]
