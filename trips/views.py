from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import Trip
from devices.models import Device
from core.excel_utils import new_workbook, xlsx_response, style_header_row, autosize_columns


def _is_admin(user):
    return getattr(getattr(user, 'profile', None), 'role', '') == 'admin'


@login_required
def trips_list(request):
    return redirect('/admin/trips/trip/')

@login_required
def trip_create(request):
    if not _is_admin(request.user):
        messages.error(request, 'Только администратор может создавать поездки')
        return redirect('trips_list')
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
    if not _is_admin(request.user):
        messages.error(request, 'Только администратор может удалять поездки')
        return redirect('trips_list')
    if request.method == 'POST':
        trip = get_object_or_404(Trip, pk=pk)
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
