from django.contrib import admin
from .models import Owner, Location, Client, Contact, Device, Repair, Verification, DeviceEvent, DailyExam
from .admin_views import analytics_view, import_view


@admin.register(Owner)
class OwnerAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email')
    search_fields = ('name', 'phone', 'email')


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        'hostname', 'is_online', 'in_repair', 'vpn_ip', 'anydesk',
        'software', 'cpu_load', 'owner', 'client', 'location', 'last_updated',
        'password_migrated', 'vnc_ready', 'agent_deployed',
    )
    list_filter = ('owner', 'client', 'location', 'is_online', 'in_repair', 'broker')
    search_fields = ('hostname', 'vpn_ip', 'anydesk', 'sn', 'os')
    list_select_related = ('owner', 'client', 'location', 'contact')
    list_per_page = 25
    autocomplete_fields = ('owner', 'client', 'location', 'contact')
    readonly_fields = ('created_at', 'last_updated')
    fieldsets = (
        ('Основное', {'fields': ('hostname', 'vpn_ip', 'anydesk', 'sn', 'os', 'software', 'broker')}),
        ('Сеть и доступ', {'fields': ('kernel', 'secureboot', 'ver', 'network_speed', 'ssh_password')}),
        ('Оборудование', {'fields': ('alco', 'tonometer', 'x11vnc')}),
        ('Телеметрия', {'fields': (
            'cpu_load',
            'memory_total', 'memory_used', 'memory_free', 'memory_percent',
            'temperature', 'cpu_temperature', 'exam_count', 'uptime', 'uptime_formatted',
            'hdd', 'hdd_total', 'hdd_percent',
        )}),
        ('Регистрация', {'fields': ('owner', 'location', 'client', 'contact')}),
        ('Статус', {'fields': ('is_online', 'in_repair', 'offline_since', 'last_mqtt_message')}),
    )

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom = [
            path('analytics/', self.admin_site.admin_view(analytics_view), name='devices_device_analytics'),
            path('import/', self.admin_site.admin_view(import_view), name='devices_device_import'),
        ]
        return custom + urls


@admin.register(Repair)
class RepairAdmin(admin.ModelAdmin):
    list_display = ('device', 'problem', 'status', 'created_at', 'in_progress_at', 'ready_at')
    list_filter = ('status',)
    search_fields = ('device__hostname', 'problem')
    autocomplete_fields = ('device',)
    list_select_related = ('device',)
    list_per_page = 25


@admin.register(Verification)
class VerificationAdmin(admin.ModelAdmin):
    list_display = ('equipment_type', 'device', 'equipment_name', 'status', 'valid_until', 'verification_date', 'sent_date')
    list_filter = ('equipment_type', 'status')
    search_fields = ('equipment_name', 'device__hostname')
    autocomplete_fields = ('device',)
    list_per_page = 25
    fieldsets = (
        ('Основное', {'fields': ('equipment_type', 'equipment_name', 'device')}),
        ('Статус', {'fields': ('status', 'sent_date', 'verification_date', 'valid_until')}),
    )


@admin.register(DeviceEvent)
class DeviceEventAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'device', 'event', 'message')
    list_filter = ('event',)
    search_fields = ('device__hostname', 'message')
    list_select_related = ('device',)
    readonly_fields = ('device', 'event', 'message', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DailyExam)
class DailyExamAdmin(admin.ModelAdmin):
    list_display = ('device', 'date', 'exams', 'cancelled', 'last_exam')
    list_filter = ('date',)
    search_fields = ('device__hostname', 'client', 'orgunit')
    list_select_related = ('device',)
    list_per_page = 25
    readonly_fields = ('device', 'date', 'exams', 'cancelled', 'group', 'client', 'orgunit', 'last_exam')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
