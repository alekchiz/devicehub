from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('devices', '0013_device_ssh_password'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailyExam',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='Дата')),
                ('exams', models.IntegerField(default=0, verbose_name='Осмотров')),
                ('cancelled', models.IntegerField(default=0, verbose_name='Отменено')),
                ('group', models.CharField(blank=True, max_length=50, verbose_name='Группа')),
                ('client', models.CharField(blank=True, max_length=200, verbose_name='Объект')),
                ('orgunit', models.CharField(blank=True, max_length=300, verbose_name='Местоположение')),
                ('last_exam', models.DateTimeField(blank=True, null=True, verbose_name='Последний осмотр')),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                             related_name='daily_exams', to='devices.device', verbose_name='Киоск')),
            ],
            options={
                'verbose_name': 'Осмотры за сутки',
                'verbose_name_plural': 'Осмотры за сутки',
                'ordering': ['-date', 'device__hostname'],
                'unique_together': {('device', 'date')},
            },
        ),
    ]
