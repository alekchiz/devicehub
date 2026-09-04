from django.contrib import admin
from .models import Trip

@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('date', 'description_short', 'devices_list', 'created_at')
    list_filter = ('date', 'devices')
    search_fields = ('description', 'devices__hostname')
    date_hierarchy = 'date'
    filter_horizontal = ('devices',)
    
    def description_short(self, obj):
        return obj.description[:80] + '...' if len(obj.description) > 80 else obj.description
    description_short.short_description = 'Описание'
    
    def devices_list(self, obj):
        return obj.devices_list()
    devices_list.short_description = 'Киоски'
