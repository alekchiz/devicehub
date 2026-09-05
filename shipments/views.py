from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import Shipment, ShipmentItem
from devices.models import Device, Location
from core.excel_utils import new_workbook, xlsx_response, style_header_row, autosize_columns

@login_required
def shipments_list(request):
    return redirect('/admin/shipments/shipment/')

@login_required
def shipment_create(request):
    if request.method == 'POST':
        receiver_name = request.POST.get('receiver_name')
        receiver_contact = request.POST.get('receiver_contact')
        transport_company = request.POST.get('transport_company')
        tracking_number = request.POST.get('tracking_number', '')
        device_id = request.POST.get('device_id') or None
        location_id = request.POST.get('location_id') or None
        description = request.POST.get('description', '')
        replacement_device_id = request.POST.get('replacement_device_id') or None
        
        if receiver_name and transport_company:
            shipment = Shipment.objects.create(
                receiver_name=receiver_name,
                receiver_contact=receiver_contact,
                transport_company=transport_company,
                tracking_number=tracking_number,
                device_id=device_id,
                location_id=location_id,
                description=description,
                replacement_device_id=replacement_device_id,
            )
            
            # Сохраняем позиции
            equipment_types = request.POST.getlist('equipment_type[]')
            quantities = request.POST.getlist('quantity[]')
            descriptions = request.POST.getlist('item_description[]')
            item_names = request.POST.getlist('item_name[]')
            
            for i in range(len(equipment_types)):
                if equipment_types[i]:
                    ShipmentItem.objects.create(
                        shipment=shipment,
                        equipment_type=equipment_types[i],
                        quantity=int(quantities[i]) if quantities[i] else 1,
                        description=descriptions[i] if i < len(descriptions) else '',
                        item_name=item_names[i] if i < len(item_names) else '',
                    )
            
            messages.success(request, f'Отправка #{shipment.id} создана')
            return redirect('shipments_list')
    
    return redirect('shipments_list')

@login_required
def shipment_change_status(request, pk):
    if request.method == 'POST':
        shipment = get_object_or_404(Shipment, pk=pk)
        new_status = request.POST.get('status')
        if new_status in dict(Shipment.STATUS_CHOICES):
            shipment.status = new_status
            if new_status == 'sent':
                shipment.sent_date = request.POST.get('sent_date') or None
            elif new_status == 'delivered':
                shipment.delivered_date = request.POST.get('delivered_date') or None
            shipment.save()
            messages.success(request, f'Статус отправки #{shipment.id} изменён')
    return redirect('shipments_list')

@login_required
def export_shipments_excel(request):
    wb, ws = new_workbook("Отправки")
    headers = ['Номер', 'Статус', 'Получатель', 'Контакт', 'Транспортная', 'Трек', 
               'Киоск', 'Локация', 'Замена на Киоск', 'Создана', 'Отправлена', 'Получена']
    ws.append(headers)
    
    for s in Shipment.objects.all():
        items = ', '.join([str(i) for i in s.items.all()])
        ws.append([
            s.id,
            s.get_status_display(),
            s.receiver_name,
            s.receiver_contact,
            s.transport_company,
            s.tracking_number,
            s.device.hostname if s.device else '',
            s.location.name if s.location else '',
            s.replacement_device.hostname if s.replacement_device else '',
            s.created_at.strftime('%Y-%m-%d %H:%M'),
            s.sent_date.strftime('%Y-%m-%d') if s.sent_date else '',
            s.delivered_date.strftime('%Y-%m-%d') if s.delivered_date else '',
        ])
    
    style_header_row(ws, len(headers))
    autosize_columns(ws)
    return xlsx_response(wb, 'shipments.xlsx')
