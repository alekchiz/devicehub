from django.db import models

class Owner(models.Model):
    name = models.CharField(max_length=200, verbose_name="Владелец")
    def __str__(self):
        return self.name
    class Meta:
        verbose_name = "Владелец"
        verbose_name_plural = "Владельцы"

class Location(models.Model):
    name = models.CharField(max_length=300, verbose_name="Локация")
    def __str__(self):
        return self.name
    class Meta:
        verbose_name = "Локация"
        verbose_name_plural = "Локации"

class Client(models.Model):
    name = models.CharField(max_length=200, verbose_name="Объект")
    def __str__(self):
        return self.name
    class Meta:
        verbose_name = "Объект"
        verbose_name_plural = "Объекты"

class Contact(models.Model):
    name = models.CharField(max_length=200, verbose_name="Контактное лицо")
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    def __str__(self):
        return self.name
    class Meta:
        verbose_name = "Контакт"
        verbose_name_plural = "Контакты"

class Device(models.Model):
    hostname = models.CharField(max_length=100, unique=True, verbose_name="Hostname")
    vpn_ip = models.CharField(max_length=50, null=True, blank=True, verbose_name="VPN IP")
    kernel = models.CharField(max_length=50, blank=True)
    x11vnc = models.CharField(max_length=50, blank=True)
    alco = models.CharField(max_length=50, blank=True, verbose_name="Алкотестер")
    tonometer = models.CharField(max_length=50, blank=True, verbose_name="Тонометр")
    software = models.CharField(max_length=50, blank=True, verbose_name="Версия ПО")
    network_speed = models.CharField(max_length=50, blank=True)
    uptime = models.CharField(max_length=100, blank=True)
    hdd = models.FloatField(null=True, blank=True, verbose_name="Свободно ГБ")
    hdd_total = models.FloatField(null=True, blank=True, verbose_name="Всего ГБ")
    hdd_percent = models.FloatField(null=True, blank=True, verbose_name="Занято %")
    anydesk = models.CharField(max_length=50, blank=True, verbose_name="AnyDesk")
    sn = models.CharField(max_length=50, blank=True, verbose_name="Серийный номер")
    os = models.CharField(max_length=100, blank=True, verbose_name="ОС")
    ver = models.CharField(max_length=10, blank=True)
    secureboot = models.CharField(max_length=20, blank=True, verbose_name="Secure Boot")
    broker = models.CharField(max_length=50, blank=True, verbose_name="Брокер")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан", null=True)
    cpu_load = models.FloatField(null=True, blank=True, verbose_name="CPU %")
    memory_total = models.FloatField(null=True, blank=True, verbose_name="RAM всего ГБ")
    memory_used = models.FloatField(null=True, blank=True, verbose_name="RAM исп. ГБ")
    memory_free = models.FloatField(null=True, blank=True, verbose_name="RAM своб. ГБ")
    memory_percent = models.FloatField(null=True, blank=True, verbose_name="RAM %")
    temperature = models.CharField(max_length=20, blank=True, verbose_name="Температура")
    cpu_temperature = models.CharField(max_length=20, blank=True, verbose_name="Температура CPU")
    uptime_formatted = models.CharField(max_length=100, blank=True, verbose_name="Аптайм")

    owner = models.ForeignKey(Owner, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Владелец")
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Локация")
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Объект")
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Контакт")

    last_updated = models.DateTimeField(auto_now=True, verbose_name="Последнее обновление")
    last_mqtt_message = models.DateTimeField(null=True, blank=True, verbose_name="Последнее MQTT сообщение")
    is_online = models.BooleanField(default=False, verbose_name="Онлайн")
    offline_since = models.DateTimeField(null=True, blank=True, verbose_name="Оффлайн с")
    in_repair = models.BooleanField(default=False, verbose_name="В ремонте")

    @property
    def offline_duration(self):
        if self.is_online or not self.offline_since:
            return None
        from django.utils import timezone
        delta = timezone.now() - self.offline_since
        hours, remainder = divmod(delta.seconds, 3600)
        minutes = remainder // 60
        if delta.days > 0:
            return f"{delta.days}д {hours}ч {minutes}м"
        elif hours > 0:
            return f"{hours}ч {minutes}м"
        else:
            return f"{minutes}м"

    @staticmethod
    def _device_ok(value):
        return bool(value) and '✅' in value

    @property
    def alco_ok(self):
        """Алкотестер исправен и подключён."""
        return self._device_ok(self.alco)

    @property
    def tono_ok(self):
        """Тонометр исправен и подключён."""
        return self._device_ok(self.tonometer)

    @property
    def temp_ok(self):
        """Термометр отдаёт корректные показания."""
        if not self.temperature:
            return False
        return self.temperature.strip() not in ('0', '0.0', 'N/A', '-')

    def __str__(self):
        return self.hostname

    class Meta:
        ordering = ['hostname']
        verbose_name = "Киоск"
        verbose_name_plural = "Киоски"

class Repair(models.Model):
    STATUS_CHOICES = [
        ('created', 'Создан'),
        ('in_progress', 'В ремонте'),
        ('ready', 'Готов'),
    ]
    
    device = models.ForeignKey(Device, on_delete=models.CASCADE, verbose_name="Киоск")
    problem = models.TextField(verbose_name="Проблема", default="")
    repair_description = models.TextField(verbose_name="Описание ремонта", blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created', verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата заявки")
    in_progress_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата начала ремонта")
    ready_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата готовности")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Последнее изменение")
    
    def save(self, *args, **kwargs):
        from django.utils import timezone
        previous_status = None
        if self.pk:
            previous_status = Repair.objects.filter(pk=self.pk).values_list('status', flat=True).first()

        if self.status in ('created', 'in_progress'):
            self.device.in_repair = True
            if not self.in_progress_at:
                if self.status == 'in_progress':
                    self.in_progress_at = timezone.now()
        elif self.status == 'ready':
            self.device.in_repair = False
            if not self.ready_at:
                self.ready_at = timezone.now()
        self.device.save()
        super().save(*args, **kwargs)

        if previous_status != self.status:
            entering_repair = self.status in ('created', 'in_progress')
            leaving_repair = self.status == 'ready'
            if leaving_repair and previous_status in ('created', 'in_progress'):
                log_device_event(self.device, 'repair_out', f'Ремонт #{self.pk} завершён')
            elif entering_repair and (previous_status is None or previous_status == 'ready'):
                log_device_event(self.device, 'repair_in', f'Ремонт #{self.pk}: {self.problem[:80]}')
    
    def __str__(self):
        return f"Ремонт {self.device.hostname} - {self.get_status_display()}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Ремонт"
        verbose_name_plural = "Ремонты"

class Verification(models.Model):
    EQUIPMENT_CHOICES = [
        ('alco', 'Алкотестер'),
        ('tonometer', 'Тонометр'),
        ('thermometer', 'Термометр'),
    ]
    
    STATUS_CHOICES = [
        ('sent', 'Отправлен на поверку'),
    ('verified', 'Поверен'),
    ]

    # За сколько дней до окончания поверки слать напоминание.
    EXPIRY_SOON_DAYS = 30
    
    equipment_type = models.CharField(max_length=20, choices=EQUIPMENT_CHOICES, verbose_name="Тип оборудования")
    equipment_name = models.CharField(max_length=200, verbose_name="Наименование оборудования")
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='verifications', verbose_name="Киоск")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='sent', verbose_name="Статус")
    sent_date = models.DateField(verbose_name="Дата отправки")
    verification_date = models.DateField(null=True, blank=True, verbose_name="Дата поверки")
    valid_until = models.DateField(null=True, blank=True, verbose_name="Действует до")
    reminded_for = models.CharField(max_length=20, default='none', verbose_name="Напомнено")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    
    def __str__(self):
        return f"Поверка {self.get_equipment_type_display()} - {self.equipment_name}"

    @property
    def expiry_state(self):
        """Состояние срока действия поверки: ok / soon / expired / none."""
        if self.status != 'verified' or not self.valid_until:
            return 'none'
        from django.utils import timezone
        days_left = (self.valid_until - timezone.localdate()).days
        if days_left < 0:
            return 'expired'
        if days_left <= self.EXPIRY_SOON_DAYS:
            return 'soon'
        return 'ok'
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Поверка"
        verbose_name_plural = "Поверки"


def log_device_event(device, event, message=''):
    """Записывает событие в историю киоска (аудит переходов статуса)."""
    DeviceEvent.objects.create(device=device, event=event, message=message)


class DeviceEvent(models.Model):
    EVENT_CHOICES = [
        ('created', 'Создано'),
        ('online', 'Онлайн'),
        ('offline', 'Оффлайн'),
        ('repair_in', 'В ремонт'),
        ('repair_out', 'Из ремонта'),
    ]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='events',
                               verbose_name="Киоск")
    event = models.CharField(max_length=20, choices=EVENT_CHOICES, verbose_name="Событие")
    message = models.CharField(max_length=300, blank=True, verbose_name="Описание")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время")

    def __str__(self):
        return f"{self.device.hostname} - {self.get_event_display()} - {self.created_at:%d.%m.%Y %H:%M}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Событие"
        verbose_name_plural = "События киосков"
