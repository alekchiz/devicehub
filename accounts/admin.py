from django.contrib import admin
from .models import UserProfile, WhitelistPhone

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'telegram_id', 'phone')
    list_filter = ('role',)
    search_fields = ('user__username', 'telegram_id', 'phone')
    fieldsets = (
        ('Основное', {'fields': ('user', 'role', 'telegram_id', 'phone', 'bot_admin')}),
        ('Уведомления', {'fields': (
            'notify_device_offline',
            'notify_device_online',
            'notify_health_check',
            'notify_weekly_report',
            'notify_verification_expiry',
        )}),
    )

@admin.register(WhitelistPhone)
class WhitelistPhoneAdmin(admin.ModelAdmin):
    list_display = ('phone', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('phone',)
