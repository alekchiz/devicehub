from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import Trip
from devices.models import Device
from core.excel_utils import new_workbook, xlsx_response, style_header_row, autosize_columns

@login_required
def trips_list(request):
    return redirect('/admin/trips/trip/')

@login_required
def trip_create(request):
    if request.method == 'POST':
        date = request.POST.get('date')
        description = request.POST.get('description')
        device_ids = request.POST.getlist('device_ids')
        
        if date and description:
            trip = Trip.objects.create(
                date=date,
                description=description,
            )
            if device_ids:
                trip.devices.set(device_ids)
            
            messages.success(request, 'Поездка добавлена')
    return redirect('trips_list')

@login_required
def trip_delete(request, pk):
    if request.method == 'POST':
        trip = Trip.objects.get(pk=pk)
        trip.delete()
        messages.success(request, 'Поездка удалена')
    return redirect('trips_list')

@login_required
def export_trips_excel(request):
    wb, ws = new_workbook("Поездки СТОЛИЦА")
    headers = ['Дата', 'Что сделано', 'Киоски']
    ws.append(headers)
    
    for t in Trip.objects.all():
        ws.append([
            t.date.strftime('%d.%m.%Y'),
            t.description,
            t.devices_list(),
        ])
    
    style_header_row(ws, len(headers))
    autosize_columns(ws)
    return xlsx_response(wb, 'trips.xlsx')
