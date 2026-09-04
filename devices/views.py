import subprocess
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.db.models import Q, Count
from .models import Device, Owner, Client, Location, Repair, Verification, DeviceEvent
from tickets.models import Ticket
from shipments.models import Shipment
from django.utils import timezone
from django.conf import settings
from django.core.paginator import Paginator
from core.excel_utils import new_workbook, xlsx_response, style_header_row, autosize_columns

def is_admin(user):
    return user.is_authenticated and user.profile.role == 'admin'

def build_qs(request, **overrides):
    """Формирует querystring из текущего request.GET с учётом переопределений."""
    qs = request.GET.copy()
    qs.pop('page', None)
    for key, value in overrides.items():
        if value is None or value == '':
            qs.pop(key, None)
        else:
            qs[key] = value
    return '?' + qs.urlencode() if qs else ''

def ssh_execute(vpn_ip, command):
    result = subprocess.run(
        ['/usr/bin/sshpass', '-p', settings.DEVICE_SSH_PASSWORD,
         '/usr/bin/ssh',
         '-o', 'ConnectTimeout=5',
         '-o', 'StrictHostKeyChecking=no',
         '-o', 'UserKnownHostsFile=/dev/null',
         f'{settings.DEVICE_SSH_USER}@{vpn_ip}', command],
        capture_output=True, text=True, timeout=15
    )
    return result

def ssh_reboot(vpn_ip):
    try:
        result = subprocess.run(
            ['/usr/bin/sshpass', '-p', settings.DEVICE_SSH_PASSWORD,
             '/usr/bin/ssh',
             '-o', 'ConnectTimeout=3',
             '-o', 'StrictHostKeyChecking=no',
             '-o', 'UserKnownHostsFile=/dev/null',
             f'{settings.DEVICE_SSH_USER}@{vpn_ip}',
             f'echo {settings.DEVICE_SSH_PASSWORD} | sudo -S reboot'],
            capture_output=True, text=True, timeout=10
        )
        return result
    except subprocess.TimeoutExpired:
        return None

@login_required
def dashboard(request):
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')

    all_devices = Device.objects.filter(hostname__regex=r'^\d{3,}$')
    devices = all_devices

    if query:
        devices = devices.filter(hostname__icontains=query)
    if status_filter == 'online':
        devices = devices.filter(is_online=True, in_repair=False)
    elif status_filter == 'offline':
        devices = devices.filter(is_online=False, in_repair=False)
    elif status_filter == 'repair':
        devices = devices.filter(in_repair=True)

    active_filters = bool(query or status_filter)
    search_mode = bool(query)

    total_count = all_devices.count()
    online_count = all_devices.filter(is_online=True, in_repair=False).count()
    offline_count = all_devices.filter(is_online=False, in_repair=False).count()
    repair_count = all_devices.filter(in_repair=True).count()

    # Прогресс активных ремонтов для карточек киосков.
    repair_map = {}
    active_repairs = Repair.objects.filter(
        device__in=all_devices, status__in=['created', 'in_progress']
    ).select_related('device')
    for rep in active_repairs:
        start = rep.in_progress_at or rep.created_at
        days = max((timezone.now().date() - start.date()).days, 0) if start else 0
        repair_map[rep.device_id] = {
            'status': rep.get_status_display(),
            'days': days,
            'percent': min(int(days / 14 * 100), 100),
        }

    # Последняя действующая поверка по каждому киоску (для индикатора на карточках).
    verif_states = {}
    for v in Verification.objects.filter(
        device__in=all_devices, status='verified', valid_until__isnull=False
    ):
        current = verif_states.get(v.device_id)
        if current is None or v.valid_until > current[1]:
            verif_states[v.device_id] = (v.expiry_state, v.valid_until, v.id)

    if repair_count:
        page_status = 'repair'
    elif offline_count:
        page_status = 'warn'
    else:
        page_status = 'ok'

    status_chips = {
        'all': build_qs(request, status=''),
        'online': build_qs(request, status='online'),
        'offline': build_qs(request, status='offline'),
        'repair': build_qs(request, status='repair'),
    }
    reset_url = build_qs(request, status='', q='')

    # Все киоски на одной странице; поиск/статус лишь сужают выборку.
    devices = list(
        devices.order_by('hostname').select_related('owner', 'client', 'location')
    )
    page_obj = None
    base_qs = ''
    result_count = len(devices)

    context = {
        'devices': devices,
        'page_obj': page_obj,
        'base_qs': base_qs,
        'total_count': total_count,
        'online_count': online_count,
        'offline_count': offline_count,
        'repair_count': repair_count,
        'page_status': page_status,
        'repair_map': repair_map,
        'verif_states': verif_states,
        'status_chips': status_chips,
        'reset_url': reset_url,
        'filter_active': active_filters,
        'result_count': result_count,
        'search_mode': search_mode,
    }
    return render(request, 'devices/dashboard.html', context)


@login_required
def clients_list(request):
    """Страница объектов со списком их киосков и агрегированным статусом."""
    clients = (
        Client.objects
        .annotate(
            total=Count('device'),
            online=Count('device', filter=Q(device__is_online=True, device__in_repair=False)),
            offline=Count('device', filter=Q(device__is_online=False, device__in_repair=False)),
            repair=Count('device', filter=Q(device__in_repair=True)),
        )
        .prefetch_related('device_set')
        .order_by('name')
    )
    return render(request, 'devices/clients.html', {'clients': clients})


@login_required
def device_history(request):
    """Страница истории событий киосков (аудит)."""
    events = DeviceEvent.objects.select_related('device')

    ev_type = request.GET.get('event', '')
    q = request.GET.get('q', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if ev_type:
        events = events.filter(event=ev_type)
    if q:
        events = events.filter(device__hostname__icontains=q)
    if date_from:
        events = events.filter(created_at__date__gte=date_from)
    if date_to:
        events = events.filter(created_at__date__lte=date_to)

    paginator = Paginator(events, 60)
    page_obj = paginator.get_page(request.GET.get('page'))

    qs_params = request.GET.copy()
    qs_params.pop('page', None)
    qs_string = qs_params.urlencode()
    base_qs = f'&{qs_string}' if qs_string else ''

    return render(request, 'devices/history.html', {
        'page_obj': page_obj,
        'events': page_obj.object_list,
        'ev_type': ev_type,
        'q': q,
        'date_from': date_from,
        'date_to': date_to,
        'base_qs': base_qs,
        'filter_active': bool(ev_type or q or date_from or date_to),
        'result_count': paginator.count,
        'event_choices': DeviceEvent.EVENT_CHOICES,
    })


@login_required
def device_status_feed(request):
    """JSON-эндпоинт для живого обновления карточек на дашборде."""
    devices = Device.objects.all()
    total = devices.count()
    online = devices.filter(is_online=True, in_repair=False).count()
    offline = devices.filter(is_online=False, in_repair=False).count()
    repair = devices.filter(in_repair=True).count()

    page_status = 'repair' if repair else ('warn' if offline else 'ok')

    payload = {
        'total': total,
        'online': online,
        'offline': offline,
        'repair': repair,
        'page_status': page_status,
        'now': timezone.localtime().strftime('%H:%M:%S'),
        'devices': {},
    }

    for d in devices:
        payload['devices'][d.id] = {
            'online': bool(d.is_online),
            'in_repair': bool(d.in_repair),
            'cpu': d.cpu_load,
            'hdd': d.hdd_percent,
            'ram': d.memory_percent,
            'offline_duration': d.offline_duration,
            'temperature': d.temperature,
            'uptime': d.uptime_formatted,
        }

    return JsonResponse(payload)

def device_detail_modal(request, pk):
    device = get_object_or_404(Device, pk=pk)
    return render(request, 'devices/device_detail_modal.html', {'device': device})

def device_detail_page(request, pk):
    device = get_object_or_404(Device, pk=pk)
    repairs = Repair.objects.filter(device=device).order_by('-created_at')[:10]
    tickets = Ticket.objects.filter(device=device).order_by('-created_at')[:10]
    shipments = Shipment.objects.filter(device=device).order_by('-created_at')[:10]
    events = device.events.all()[:10]
    verifications = device.verifications.all()[:10]
    
    context = {
        'device': device,
        'repairs': repairs,
        'tickets': tickets,
        'shipments': shipments,
        'events': events,
        'verifications': verifications,
    }
    return render(request, 'devices/device_detail_page.html', context)

@user_passes_test(is_admin)
def device_reboot(request, pk):
    device = get_object_or_404(Device, pk=pk)
    
    if not device.vpn_ip or device.vpn_ip in ['0', 'N/A']:
        messages.error(request, f'Нет VPN IP у {device.hostname}')
        return redirect('device_detail_page', pk=pk)
    
    try:
        result = ssh_reboot(device.vpn_ip)
        
        if result is None:
            messages.success(request, f'✅ {device.hostname} ушёл в перезагрузку')
        elif result.returncode == 0:
            messages.success(request, f'✅ Команда reboot отправлена на {device.hostname}')
        else:
            messages.warning(request, f'⚠️ {device.hostname}: {result.stderr.strip() or "код ошибки: "+str(result.returncode)}')
    except Exception as e:
        messages.error(request, f'❌ Ошибка подключения к {device.hostname}: {e}')
    
    return redirect('device_detail_page', pk=pk)

@user_passes_test(is_admin)
def device_stop(request, pk):
    device = get_object_or_404(Device, pk=pk)
    
    if not device.vpn_ip or device.vpn_ip in ['0', 'N/A']:
        messages.error(request, f'Нет VPN IP у {device.hostname}')
        return redirect('device_detail_page', pk=pk)
    
    try:
        cmd = "sed -i '/^storageService\\.remoteParams\\.host/s/^/#/' /home/terminal/rtk/configuration.local.conf"
        result = ssh_execute(device.vpn_ip, cmd)
        
        if result.returncode != 0:
            messages.warning(request, f'⚠️ Ошибка изменения конфига: {result.stderr.strip()}')
            return redirect('device_detail_page', pk=pk)
        
        ssh_reboot(device.vpn_ip)
        messages.success(request, f'✅ Сервис {device.hostname} остановлен, перезагрузка...')
    except Exception as e:
        messages.error(request, f'❌ Ошибка: {e}')
    
    return redirect('device_detail_page', pk=pk)

@user_passes_test(is_admin)
def device_start(request, pk):
    device = get_object_or_404(Device, pk=pk)
    
    if not device.vpn_ip or device.vpn_ip in ['0', 'N/A']:
        messages.error(request, f'Нет VPN IP у {device.hostname}')
        return redirect('device_detail_page', pk=pk)
    
    try:
        cmd = "sed -i '/^#storageService\\.remoteParams\\.host/s/^#//' /home/terminal/rtk/configuration.local.conf"
        result = ssh_execute(device.vpn_ip, cmd)
        
        if result.returncode != 0:
            messages.warning(request, f'⚠️ Ошибка изменения конфига: {result.stderr.strip()}')
            return redirect('device_detail_page', pk=pk)
        
        ssh_reboot(device.vpn_ip)
        messages.success(request, f'✅ Сервис {device.hostname} запущен, перезагрузка...')
    except Exception as e:
        messages.error(request, f'❌ Ошибка: {e}')
    
    return redirect('device_detail_page', pk=pk)

@user_passes_test(is_admin)
def bulk_action(request):
    if request.method == 'POST':
        device_ids = request.POST.getlist('device_ids')
        action = request.POST.get('action')
        
        if not device_ids:
            messages.warning(request, 'Не выбраны киоска')
            return redirect('dashboard')
        
        devices = Device.objects.filter(id__in=device_ids)
        success = 0
        failed = 0
        
        for device in devices:
            if not device.vpn_ip or device.vpn_ip in ['0', 'N/A']:
                failed += 1
                continue
            
            try:
                if action == 'reboot':
                    ssh_reboot(device.vpn_ip)
                elif action == 'stop':
                    cmd = "sed -i '/^storageService\\.remoteParams\\.host/s/^/#/' /home/terminal/rtk/configuration.local.conf"
                    result = ssh_execute(device.vpn_ip, cmd)
                    if result and result.returncode == 0:
                        ssh_reboot(device.vpn_ip)
                elif action == 'start':
                    cmd = "sed -i '/^#storageService\\.remoteParams\\.host/s/^#//' /home/terminal/rtk/configuration.local.conf"
                    result = ssh_execute(device.vpn_ip, cmd)
                    if result and result.returncode == 0:
                        ssh_reboot(device.vpn_ip)
                
                success += 1
            except:
                failed += 1
        
        messages.success(request, f'✅ Выполнено: {success}, ошибок: {failed}')
    
    return redirect('dashboard')

@login_required
def export_devices_excel(request):
    wb, ws = new_workbook("Киоски")
    headers = ['Hostname', 'VPN IP', 'AnyDesk', 'Владелец', 'Локация', 'Объект',
               'Контакт', 'Версия ПО', 'Алкотестер', 'Тонометр', 'Скорость сети',
               'Ядро', 'Uptime', 'HDD свободно', 'HDD всего', 'HDD %', 'ОС', 'SN', 'Онлайн', 'В ремонте']
    ws.append(headers)
    for d in Device.objects.filter(hostname__regex=r'^\d{3,}$').select_related('owner', 'location', 'client', 'contact'):
        ws.append([
            d.hostname, d.vpn_ip, d.anydesk,
            d.owner.name if d.owner else '',
            d.location.name if d.location else '',
            d.client.name if d.client else '',
            d.contact.name if d.contact else '',
            d.software, d.alco, d.tonometer, d.network_speed,
            d.kernel, d.uptime, d.hdd, d.hdd_total, d.hdd_percent,
            d.os, d.sn, 'Да' if d.is_online else 'Нет', 'Да' if d.in_repair else 'Нет'
        ])
    style_header_row(ws, len(headers))
    autosize_columns(ws)
    return xlsx_response(wb, 'devices.xlsx')

@login_required
def export_devices_history(request):
    wb, ws = new_workbook("История киосков")
    headers = ['Hostname', 'VPN IP', 'AnyDesk', 'SN', 'Дата создания', 'Последняя активность', 'Статус', 'Брокер']
    ws.append(headers)
    
    row = 2
    for d in Device.objects.filter(hostname__regex=r'^\d{3,}$').order_by('-created_at'):
        ws.cell(row=row, column=1, value=d.hostname)
        ws.cell(row=row, column=2, value=d.vpn_ip or '')
        ws.cell(row=row, column=3, value=d.anydesk or '')
        ws.cell(row=row, column=4, value=d.sn or '')
        
        if d.created_at and d.created_at.year > 2020:
            cell = ws.cell(row=row, column=5, value=d.created_at.replace(tzinfo=None))
            cell.number_format = 'DD.MM.YYYY HH:MM'
        
        last_active = None
        if d.last_mqtt_message and d.last_mqtt_message.year > 2020:
            last_active = d.last_mqtt_message
        elif d.last_updated and d.last_updated.year > 2020:
            last_active = d.last_updated
        
        if last_active:
            cell = ws.cell(row=row, column=6, value=last_active.replace(tzinfo=None))
            cell.number_format = 'DD.MM.YYYY HH:MM'
        
        ws.cell(row=row, column=7, value='Онлайн' if d.is_online else 'Оффлайн')
        ws.cell(row=row, column=8, value=d.broker or '')
        row += 1
    
    style_header_row(ws, len(headers))
    autosize_columns(ws)
    return xlsx_response(wb, 'devices_history.xlsx')

@login_required
def export_devices_stats(request):
    from django.db.models import Count
    from django.db.models.functions import TruncDate, TruncMonth
    from datetime import timedelta, date
    
    wb, ws1 = new_workbook("По дням")
    headers = ['Дата', 'Всего киосков', 'Онлайн', 'Оффлайн', '% онлайн']
    ws1.append(headers)
    
    today = date.today()
    devices = Device.objects.filter(hostname__regex=r'^\d{3,}$')
    
    for i in range(90):
        day = today - timedelta(days=i)
        day_start = timezone.make_aware(timezone.datetime(day.year, day.month, day.day, 0, 0, 0))
        day_end = day_start + timedelta(days=1)
        
        existed = devices.filter(created_at__lt=day_end).count()
        online = devices.filter(
            last_mqtt_message__gte=day_start,
            last_mqtt_message__lt=day_end
        ).count()
        
        offline = existed - online
        pct = round(online / existed * 100, 1) if existed > 0 else 0
        
        ws1.append([day.strftime('%d.%m.%Y'), existed, online, offline, pct])
    style_header_row(ws1, len(headers))

    ws2 = wb.create_sheet("По месяцам")
    headers2 = ['Месяц', 'Всего киосков', 'Онлайн (среднее)', 'Оффлайн (среднее)', '% онлайн']
    ws2.append(headers2)
    
    for i in range(12):
        month_date = today.replace(day=1) - timedelta(days=i*30)
        month_start = timezone.make_aware(timezone.datetime(month_date.year, month_date.month, 1, 0, 0, 0))
        if month_date.month == 12:
            month_end = timezone.make_aware(timezone.datetime(month_date.year + 1, 1, 1, 0, 0, 0))
        else:
            month_end = timezone.make_aware(timezone.datetime(month_date.year, month_date.month + 1, 1, 0, 0, 0))
        
        existed = devices.filter(created_at__lt=month_end).count()
        online = devices.filter(
            last_mqtt_message__gte=month_start,
            last_mqtt_message__lt=month_end
        ).count()
        
        offline = existed - online
        pct = round(online / existed * 100, 1) if existed > 0 else 0
        
        ws2.append([month_date.strftime('%B %Y'), existed, online, offline, pct])
    style_header_row(ws2, len(headers2))

    autosize_columns(ws1)
    autosize_columns(ws2)
    return xlsx_response(wb, 'devices_stats.xlsx')

@login_required
def export_device_report(request, pk):
    device = get_object_or_404(Device, pk=pk)
    repairs = Repair.objects.filter(device=device)
    tickets = Ticket.objects.filter(device=device)
    
    wb, ws = new_workbook("Сводка по Киоску")
    
    ws.append(['Киоск', device.hostname])
    ws.append(['VPN IP', device.vpn_ip or '—'])
    ws.append(['AnyDesk', device.anydesk or '—'])
    ws.append(['SN', device.sn or '—'])
    ws.append(['ОС', device.os or '—'])
    ws.append(['Статус', 'Онлайн' if device.is_online else 'Оффлайн'])
    ws.append([])
    
    ws.append(['РЕМОНТЫ'])
    ws.append(['#', 'Проблема', 'Описание', 'Статус', 'Создан', 'Готов'])
    for r in repairs:
        ws.append([r.id, r.problem, r.repair_description or '', r.get_status_display(),
                   r.created_at.strftime('%d.%m.%Y') if r.created_at else '',
                   r.ready_at.strftime('%d.%m.%Y') if r.ready_at else ''])
    
    ws.append([])
    ws.append(['ЗАЯВКИ'])
    ws.append(['#', 'Проблема', 'Статус', 'Создал', 'Дата'])
    for t in tickets:
        ws.append([t.id, t.problem, t.get_status_display(),
                   t.created_by.username if t.created_by else '',
                   t.created_at.strftime('%d.%m.%Y') if t.created_at else ''])
    
    autosize_columns(ws)
    return xlsx_response(wb, f'device_{device.hostname}.xlsx')

@login_required
def export_repairs_report(request):
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    repairs = Repair.objects.select_related('device')
    if date_from:
        repairs = repairs.filter(created_at__date__gte=date_from)
    if date_to:
        repairs = repairs.filter(created_at__date__lte=date_to)
    
    wb, ws = new_workbook("Ремонты за период")
    
    ws.append(['Отчёт по ремонтам'])
    ws.append(['Период', f'{date_from} — {date_to}'])
    ws.append(['Всего ремонтов', repairs.count()])
    ws.append([])
    
    ws.append(['#', 'Киоск', 'Проблема', 'Статус', 'Создан', 'Готов', 'Длительность (дней)'])
    for r in repairs:
        duration = ''
        if r.ready_at and r.created_at:
            duration = (r.ready_at.date() - r.created_at.date()).days
        ws.append([r.id, r.device.hostname, r.problem, r.get_status_display(),
                   r.created_at.strftime('%d.%m.%Y') if r.created_at else '',
                   r.ready_at.strftime('%d.%m.%Y') if r.ready_at else '',
                   duration])
    
    autosize_columns(ws)
    return xlsx_response(wb, 'repairs_report.xlsx')

@login_required
def export_alco_report(request):
    devices = Device.objects.filter(hostname__regex=r'^\d{3,}$')
    
    wb, ws = new_workbook("Алкотестеры")
    headers = ['Киоск', 'VPN IP', 'AnyDesk', 'Статус алкотестера', 'Статус Киоска']
    ws.append(headers)
    
    for d in devices:
        alco_ok = '✅' in (d.alco or '')
        ws.append([d.hostname, d.vpn_ip or '', d.anydesk or '',
                   'Подключён' if alco_ok else 'НЕ ПОДКЛЮЧЁН',
                   'Онлайн' if d.is_online else 'Оффлайн'])
    
    style_header_row(ws, len(headers))
    autosize_columns(ws)
    return xlsx_response(wb, 'alco_report.xlsx')

@login_required
def export_tonometer_report(request):
    devices = Device.objects.filter(hostname__regex=r'^\d{3,}$')
    
    wb, ws = new_workbook("Тонометры")
    headers = ['Киоск', 'VPN IP', 'AnyDesk', 'Статус тонометра', 'Статус Киоска']
    ws.append(headers)
    
    for d in devices:
        ton_ok = '✅' in (d.tonometer or '')
        ws.append([d.hostname, d.vpn_ip or '', d.anydesk or '',
                   'Подключён' if ton_ok else 'НЕ ПОДКЛЮЧЁН',
                   'Онлайн' if d.is_online else 'Оффлайн'])
    
    style_header_row(ws, len(headers))
    autosize_columns(ws)
    return xlsx_response(wb, 'tonometer_report.xlsx')

def repairs_list(request):
    repairs = Repair.objects.select_related('device').all()
    devices = Device.objects.filter(hostname__regex=r'^\d{3,}$').order_by('hostname')
    
    context = {
        'repairs': repairs,
        'devices': devices,
    }
    return render(request, 'devices/repairs.html', context)

def repair_create(request):
    if request.method == 'POST':
        device_id = request.POST.get('device_id')
        problem = request.POST.get('problem')
        if device_id and problem:
            device = get_object_or_404(Device, id=device_id)
            Repair.objects.create(device=device, problem=problem)
            messages.success(request, f'Заявка на ремонт {device.hostname} создана')
    return redirect('repairs_list')

def repair_start(request, pk):
    if request.method == 'POST':
        repair = get_object_or_404(Repair, pk=pk)
        repair.status = 'in_progress'
        repair.save()
        messages.success(request, f'Ремонт {repair.device.hostname} начат')
    return redirect('repairs_list')

def repair_ready(request, pk):
    repair = get_object_or_404(Repair, pk=pk)
    if request.method == 'POST':
        repair_description = request.POST.get('repair_description')
        repair.status = 'ready'
        repair.repair_description = repair_description
        repair.save()
        messages.success(request, f'Ремонт {repair.device.hostname} завершён')
    return redirect('repairs_list')

@login_required
def export_repairs_excel(request):
    wb, ws = new_workbook("Ремонты")
    headers = ['Hostname', 'Проблема', 'Описание ремонта', 'Статус',
               'Дата заявки', 'Дата начала', 'Дата готовности']
    ws.append(headers)
    for r in Repair.objects.select_related('device').all():
        ws.append([
            r.device.hostname,
            r.problem,
            r.repair_description or '',
            r.get_status_display(),
            r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
            r.in_progress_at.strftime('%Y-%m-%d %H:%M') if r.in_progress_at else '',
            r.ready_at.strftime('%Y-%m-%d %H:%M') if r.ready_at else '',
        ])
    style_header_row(ws, len(headers))
    autosize_columns(ws)
    return xlsx_response(wb, 'repairs.xlsx')

@login_required
def verifications_list(request):
    verifications = Verification.objects.select_related('device').all()
    devices = Device.objects.filter(hostname__regex=r'^\d{3,}$').order_by('hostname')
    context = {'verifications': verifications, 'devices': devices}
    return render(request, 'devices/verifications.html', context)

@login_required
def verification_create(request):
    if request.method == 'POST':
        equipment_type = request.POST.get('equipment_type')
        equipment_name = request.POST.get('equipment_name')
        sent_date = request.POST.get('sent_date')
        device_id = request.POST.get('device_id') or None
        valid_until = request.POST.get('valid_until') or None
        if equipment_type and equipment_name and sent_date:
            Verification.objects.create(
                equipment_type=equipment_type,
                equipment_name=equipment_name,
                sent_date=sent_date,
                device_id=device_id,
                valid_until=valid_until,
            )
            messages.success(request, f'Поверка "{equipment_name}" создана')
    return redirect('verifications_list')

@login_required
def verification_verify(request, pk):
    if request.method == 'POST':
        verification = get_object_or_404(Verification, pk=pk)
        verification_date = request.POST.get('verification_date')
        valid_until = request.POST.get('valid_until') or None
        if verification_date:
            verification.status = 'verified'
            verification.verification_date = verification_date
            verification.valid_until = valid_until
            verification.reminded_for = 'none'
            verification.save()
            messages.success(request, 'Поверка отмечена как выполненная')
    return redirect('verifications_list')

@login_required
def export_verifications_excel(request):
    wb, ws = new_workbook("Поверки")
    headers = ['Тип оборудования', 'Киоск', 'Наименование', 'Статус',
               'Дата отправки', 'Дата поверки', 'Действует до', 'Состояние срока']
    ws.append(headers)
    for v in Verification.objects.select_related('device').all():
        expiry = {
            'ok': 'В сроке', 'soon': 'Скоро истекает', 'expired': 'Истекла', 'none': '—'
        }.get(v.expiry_state, '—')
        ws.append([
            v.get_equipment_type_display(),
            v.device.hostname if v.device else '',
            v.equipment_name,
            v.get_status_display(),
            v.sent_date.strftime('%Y-%m-%d') if v.sent_date else '',
            v.verification_date.strftime('%Y-%m-%d') if v.verification_date else '',
            v.valid_until.strftime('%Y-%m-%d') if v.valid_until else '',
            expiry,
        ])
    style_header_row(ws, len(headers))
    autosize_columns(ws)
    return xlsx_response(wb, 'verifications.xlsx')

@login_required
def export_med_devices_report(request):
    """Отчёт по киоскам: состояние средств измерений (алко/тоно/термо)."""
    devices = Device.objects.filter(hostname__regex=r'^\d{3,}$').order_by('hostname')
    wb, ws = new_workbook("Мед.средства")
    headers = ['Киоск', 'Алкотестер', 'Тонометр', 'Термометр', 'Средства в порядке', 'Онлайн', 'Последнее обновление']
    ws.append(headers)
    for d in devices:
        alco = 'OK' if d.alco_ok else 'Ошибка/нет'
        tono = 'OK' if d.tono_ok else 'Ошибка/нет'
        temp = 'OK' if d.temp_ok else 'Нет данных'
        ok = 'Да' if (d.alco_ok and d.tono_ok and d.temp_ok) else 'Нет'
        ws.append([
            d.hostname, alco, tono, temp, ok,
            'Онлайн' if d.is_online else 'Оффлайн',
            d.last_updated.strftime('%Y-%m-%d %H:%M') if d.last_updated else '',
        ])
    style_header_row(ws, len(headers))
    autosize_columns(ws)
    return xlsx_response(wb, 'med_devices_report.xlsx')
