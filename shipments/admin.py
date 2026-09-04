from django.contrib import admin
from .models import Shipment, ShipmentItem

class ShipmentItemInline(admin.TabularInline):
    model = ShipmentItem
    extra = 1
    fields = ('equipment_type', 'item_name', 'quantity', 'description')

@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'receiver_name', 'transport_company', 'status', 'device', 'created_at')
    list_filter = ('status',)
    search_fields = ('receiver_name', 'tracking_number', 'device__hostname')
    inlines = [ShipmentItemInline]
    autocomplete_fields = ('device', 'replacement_device')
    list_select_related = ('device', 'location', 'replacement_device')
    list_per_page = 25
