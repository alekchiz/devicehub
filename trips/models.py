from django.db import models
from devices.models import Device

class Trip(models.Model):
    date = models.DateField(verbose_name="Дата поездки")
    description = models.TextField(verbose_name="Что сделано")
    devices = models.ManyToManyField(Device, blank=True, verbose_name="Киоски")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    
    def devices_list(self):
        return ", ".join([d.hostname for d in self.devices.all()])
    devices_list.short_description = 'Киоски'
    
    def __str__(self):
        return f"Поездка {self.date} - {self.description[:50]}"
    
    class Meta:
        ordering = ['-date']
        verbose_name = "Поездка СТОЛИЦА"
        verbose_name_plural = "Поездки СТОЛИЦА"
