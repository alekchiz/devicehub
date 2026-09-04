from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Ticket, TicketComment, ActivityLog
from devices.models import Device
from django.contrib.auth.models import User
from core.excel_utils import new_workbook, xlsx_response, style_header_row, autosize_columns

@login_required
def tickets_list(request):
    user = request.user
    
    if user.profile.role == 'technician':
        tickets = Ticket.objects.filter(
            Q(created_by=user) | Q(assigned_to=user)
        ).distinct()
    elif user.profile.role == 'observer':
        tickets = Ticket.objects.all()
    else:
        tickets = Ticket.objects.all()
    
    query = request.GET.get('q', '')
    if query:
        tickets = tickets.filter(
            Q(device__hostname__icontains=query) |
            Q(problem__icontains=query)
        )
    
    devices = Device.objects.all().order_by('hostname')
    technicians = User.objects.filter(profile__role='technician')
    
    context = {
        'tickets': tickets,
        'devices': devices,
        'technicians': technicians,
    }
    return render(request, 'tickets/tickets.html', context)

@login_required
def ticket_create(request):
    if request.method == 'POST':
        device_id = request.POST.get('device_id')
        problem = request.POST.get('problem')
        contact_name = request.POST.get('contact_name')
        contact_phone = request.POST.get('contact_phone')
        
        if device_id and problem:
            device = get_object_or_404(Device, id=device_id)
            ticket = Ticket.objects.create(
                device=device,
                problem=problem,
                contact_name=contact_name,
                contact_phone=contact_phone,
                created_by=request.user
            )
            # Лог
            ActivityLog.objects.create(
                user=request.user,
                action='create',
                model_name='Ticket',
                object_id=ticket.id,
                description=f'Создана заявка #{ticket.id} на Киоск {device.hostname}'
            )
            messages.success(request, f'Заявка #{ticket.id} создана')
    return redirect('tickets_list')

@login_required
def ticket_edit(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    
    if request.user.profile.role == 'technician' and ticket.created_by != request.user:
        messages.error(request, 'Вы можете редактировать только свои заявки')
        return redirect('tickets_list')
    
    if request.method == 'POST':
        problem = request.POST.get('problem')
        contact_name = request.POST.get('contact_name')
        contact_phone = request.POST.get('contact_phone')
        
        if problem:
            ticket.problem = problem
            ticket.contact_name = contact_name
            ticket.contact_phone = contact_phone
            ticket.save()
            # Лог
            ActivityLog.objects.create(
                user=request.user,
                action='update',
                model_name='Ticket',
                object_id=ticket.id,
                description=f'Изменена заявка #{ticket.id}'
            )
            messages.success(request, f'Заявка #{ticket.id} обновлена')
            return redirect('tickets_list')
    
    devices = Device.objects.all().order_by('hostname')
    context = {
        'ticket': ticket,
        'devices': devices,
    }
    return render(request, 'tickets/ticket_edit.html', context)

@login_required
def ticket_assign(request, pk):
    if request.method == 'POST':
        ticket = get_object_or_404(Ticket, pk=pk)
        user_id = request.POST.get('user_id')
        if user_id:
            user = get_object_or_404(User, id=user_id)
            ticket.assigned_to = user
            ticket.status = 'in_progress'
            ticket.save()
            # Лог
            ActivityLog.objects.create(
                user=request.user,
                action='assign',
                model_name='Ticket',
                object_id=ticket.id,
                description=f'Заявка #{ticket.id} назначена на {user.username}'
            )
            messages.success(request, f'Заявка #{ticket.id} назначена на {user.username}')
    return redirect('tickets_list')

@login_required
def ticket_change_status(request, pk):
    if request.method == 'POST':
        ticket = get_object_or_404(Ticket, pk=pk)
        new_status = request.POST.get('status')
        if new_status in dict(Ticket.STATUS_CHOICES):
            ticket.status = new_status
            ticket.save()
            # Лог
            ActivityLog.objects.create(
                user=request.user,
                action='status_change',
                model_name='Ticket',
                object_id=ticket.id,
                description=f'Заявка #{ticket.id} → "{ticket.get_status_display()}"'
            )
            messages.success(request, f'Статус заявки #{ticket.id} изменён на "{ticket.get_status_display()}"')
    return redirect('tickets_list')

@login_required
def ticket_comment(request, pk):
    if request.method == 'POST':
        ticket = get_object_or_404(Ticket, pk=pk)
        text = request.POST.get('text')
        if text:
            TicketComment.objects.create(
                ticket=ticket,
                user=request.user,
                text=text
            )
            messages.success(request, 'Комментарий добавлен')
    return redirect('tickets_list')

@login_required
def activity_log_list(request):
    logs = ActivityLog.objects.all()[:100]
    return render(request, 'tickets/activity_log.html', {'logs': logs})

@login_required
def export_tickets_excel(request):
    wb, ws = new_workbook("Заявки")
    headers = ['Номер', 'Киоск', 'Проблема', 'ФИО', 'Телефон', 'Статус', 'Создал', 'Назначен', 'Создана']
    ws.append(headers)
    
    user = request.user
    if user.profile.role == 'technician':
        tickets = Ticket.objects.filter(
            Q(created_by=user) | Q(assigned_to=user)
        ).distinct()
    else:
        tickets = Ticket.objects.all()
    
    for t in tickets:
        ws.append([
            t.id,
            t.device.hostname,
            t.problem,
            t.contact_name,
            t.contact_phone,
            t.get_status_display(),
            t.created_by.username if t.created_by else '',
            t.assigned_to.username if t.assigned_to else '',
            t.created_at.strftime('%Y-%m-%d %H:%M'),
        ])
    
    style_header_row(ws, len(headers))
    autosize_columns(ws)
    return xlsx_response(wb, 'tickets.xlsx')
