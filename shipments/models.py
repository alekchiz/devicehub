from django.db import models
from devices.models import Device, Location

class Shipment(models.Model):
    STATUS_CHOICES = [
        ('created', 'Создана'),
        ('sent', 'Отправлена'),
        ('delivered', 'Доставлена'),
    ]
    
    EQUIPMENT_CHOICES = [
        ('thermal_paper', 'Термобумага'),
        ('batteries', 'Батарейки'),
        ('tubes', 'Трубочки'),
        ('mouthpiece', 'Мундштук'),
        ('printer', 'Принтер'),
        ('alco', 'Алкотестер'),
        ('tonometer', 'Тонометр'),
        ('thermometer', 'Термометр'),
        ('other', 'Другое'),
    ]
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created', verbose_name="Статус")
    
    # Получатель
    receiver_name = models.CharField(max_length=200, verbose_name="ФИО получателя")
    receiver_contact = models.CharField(max_length=100, verbose_name="Контакт получателя")
    
    # Доставка
    transport_company = models.CharField(max_length=200, verbose_name="Транспортная компания")
    tracking_number = models.CharField(max_length=100, blank=True, verbose_name="Трек-номер")
    
    # Куда
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="На какой Киоск")
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Локация")
    
    # Даты
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    sent_date = models.DateField(null=True, blank=True, verbose_name="Дата отправки")
    delivered_date = models.DateField(null=True, blank=True, verbose_name="Дата получения")
    
    # Замена Киоска
    replacement_device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True, 
                                           related_name='replacement_for', verbose_name="Замена на Киоск")
    
    description = models.TextField(blank=True, verbose_name="Общее описание")
    
    def __str__(self):
        return f"Отправка #{self.id} - {self.get_status_display()}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Отправка"
        verbose_name_plural = "Отправки"


class ShipmentItem(models.Model):
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='items', verbose_name="Отправка")
    equipment_type = models.CharField(max_length=30, choices=Shipment.EQUIPMENT_CHOICES, verbose_name="Тип")
    item_name = models.CharField(max_length=200, blank=True, verbose_name="Название (для Другое)")
    quantity = models.PositiveIntegerField(default=1, verbose_name="Количество")
    description = models.CharField(max_length=300, blank=True, verbose_name="Описание позиции")
    
    def __str__(self):
        return f"{self.get_equipment_type_display()} x{self.quantity}"
    
    class Meta:
        verbose_name = "Позиция отправки"
        verbose_name_plural = "Позиции отправки"
