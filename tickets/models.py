from django.db import models
from django.contrib.auth.models import User
from devices.models import Device

class Ticket(models.Model):
    STATUS_CHOICES = [
        ('created', 'Создана'),
        ('in_progress', 'В работе'),
        ('completed', 'Выполнена'),
        ('closed', 'Закрыта'),
    ]
    
    device = models.ForeignKey(Device, on_delete=models.CASCADE, verbose_name="Киоск")
    problem = models.TextField(verbose_name="Проблема")
    contact_name = models.CharField(max_length=200, verbose_name="ФИО для связи")
    contact_phone = models.CharField(max_length=50, verbose_name="Телефон для связи")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created', verbose_name="Статус")
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='tickets_created', verbose_name="Создал")
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_assigned', verbose_name="Назначен на")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлена")
    
    def __str__(self):
        return f"Заявка #{self.id} - {self.device.hostname}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"

class TicketComment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    text = models.TextField(verbose_name="Комментарий")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Комментарий к #{self.ticket.id}"
    
    class Meta:
        verbose_name = "Комментарий"
        verbose_name_plural = "Комментарии"

class ActivityLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'Создание'),
        ('update', 'Изменение'),
        ('status_change', 'Смена статуса'),
        ('assign', 'Назначение'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Пользователь")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, verbose_name="Действие")
    model_name = models.CharField(max_length=50, verbose_name="Модель")
    object_id = models.IntegerField(verbose_name="ID объекта")
    description = models.TextField(verbose_name="Описание")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время")
    
    def __str__(self):
        return f"{self.user} - {self.get_action_display()} - {self.model_name}#{self.object_id}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Лог действий"
        verbose_name_plural = "Логи действий"
