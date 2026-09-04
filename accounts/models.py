from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('technician', 'Техник'),
        ('observer', 'Наблюдатель'),
        ('admin', 'Админ'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='technician', verbose_name="Роль")
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True, verbose_name="Telegram ID")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Телефон")
    
    # Уведомления
    notify_device_offline = models.BooleanField(default=False, verbose_name="Уведомлять о падении Киоск")
    notify_device_online = models.BooleanField(default=False, verbose_name="Уведомлять о возврате Киоск")
    notify_health_check = models.BooleanField(default=False, verbose_name="Уведомлять о health-check")
    notify_weekly_report = models.BooleanField(default=False, verbose_name="Уведомлять о еженедельной сводке")
    notify_verification_expiry = models.BooleanField(
        default=False, verbose_name="Уведомлять о сроках поверок"
    )
    bot_admin = models.BooleanField(default=False, verbose_name="Может добавлять пользователей через бот")
    
    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"
    
    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

class WhitelistPhone(models.Model):
    phone = models.CharField(max_length=20, unique=True, verbose_name="Номер телефона")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Добавлен")
    
    def __str__(self):
        return self.phone
    
    class Meta:
        verbose_name = "Разрешённый номер"
        verbose_name_plural = "Разрешённые номера"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
