import subprocess
import logging
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
import re
from django.http import JsonResponse
from django.db.models import Q, Count, Sum, OuterRef, Subquery
from .models import Device, Owner, Client, Location, Repair, Verification, DeviceEvent, DailyExam
from tickets.models import Ticket
from shipments.models import Shipment
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.core.paginator import Paginator
from core.excel_utils import new_workbook, xlsx_response, style_header_row, autosize_columns

logger = logging.getLogger(__name__)

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

class _SSHFailed:
    """Заглушка результата при недоступности киоска (неверный пароль/нет сети)."""
    returncode = 1
    stdout = ''
    stderr = 'SSH: не удалось подключиться (неверный пароль или киоск недоступен)'

    def __init__(self, message=None):
        if message:
            self.stderr = message


def _ssh_candidate_passwords(device=None):
    """Пароли для подключения: свой у киоска, глобальный, затем резервные из настроек."""
    seen, candidates = set(), []
    pool = []
    if device and getattr(device, 'ssh_password', None):
        pool.append(device.ssh_password)
    pool.append(settings.DEVICE_SSH_PASSWORD)
    pool.extend(getattr(settings, 'DEVICE_SSH_PASSWORDS', []) or [])
    for pwd in pool:
        if pwd and pwd not in seen:
            seen.add(pwd)
            candidates.append(pwd)
    return candidates


def _ssh_sudo_passwords(device=None):
    """Пароли для sudo: сначала отдельный sudo-пароль, затем пароли входа.
    Если на ПАК пароль входа и пароль sudo совпадают, отдельный sudo-пароль
    не задан — и тогда sudo выполняется паролем входа (обратная совместимость).
    """
    seen, pool, out = set(), [], []
    sudo_pw = getattr(settings, 'DEVICE_SSH_SUDO_PASSWORD', '')
    if sudo_pw:
        pool.append(sudo_pw)
    pool.extend(_ssh_candidate_passwords(device))
    for pwd in pool:
        if pwd and pwd not in seen:
            seen.add(pwd)
            out.append(pwd)
    return out


def _authorized_keys_cmd():
    """Команда (выполняется как пользователь terminal) добавляющая SSH-ключи.
    Ключи берутся из DEVICE_SSH_PUBLIC_KEYS; добавление идемпотентно (sort -u).
    """
    keys = [k.strip() for k in
            getattr(settings, 'DEVICE_SSH_PUBLIC_KEYS', []) or [] if k.strip()]
    if not keys:
        return ''
    body = ''.join(k + '\n' for k in keys)
    return ("mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
            "{ cat >> ~/.ssh/authorized_keys <<'SSHKEYS_EOR'\n" + body +
            "SSHKEYS_EOR\n"
            "sort -u -o ~/.ssh/authorized_keys ~/.ssh/authorized_keys; "
            "chmod 600 ~/.ssh/authorized_keys; true; }")


def _ssh_args(login_pwd, vpn_ip, remote, connect_timeout):
    return ['/usr/bin/sshpass', '-p', login_pwd, '/usr/bin/ssh',
            '-o', f'ConnectTimeout={connect_timeout}',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            f'{settings.DEVICE_SSH_USER}@{vpn_ip}', remote]


def _ssh_auth_failed(result):
    """Признак ошибки аутентификации самого SSH-подключения."""
    err = (result.stderr or '').lower()
    return result.returncode == 5 or (
        'permission denied' in err or
        'authentication' in err or
        'denied.' in err
    )


def _sudo_auth_failed(result):
    """Признак неудачного sudo: неверный sudo-пароль или нет прав.
    Ключевые слова и на английском, и на русском (локали sudo бывают разными;
    вдобавок команды sudo принудительно запускаются с LC_ALL=C).
    """
    err = (result.stderr or '').lower()
    return any(k in err for k in (
        'incorrect password', 'try again', 'no password',
        'authentication failure', 'not in sudoers',
        'неправильного пароля', 'неверный пароль', 'попробуйте ещё раз',
        'требуется пароль', 'не входит в sudoers', 'не найден в sudoers',
    ))


def _run_ssh(args, timeout):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return _SSHFailed('SSH: таймаут подключения')


def _ssh_run(vpn_ip, command, candidates, sudo_passwords=None, sudo_cmd=None, timeout=15):
    """Выполняет команду по SSH, пробуя каждый пароль входа по очереди.

    sudo_cmd — функция, получающая sudo-пароль и возвращающая удалённую команду.
    При ней для каждого пароля входа перебираются sudo-пароли (сначала отдельный
    sudo-пароль, затем пароли входа) из-за возможного их различия на ПАК.
    """
    if sudo_cmd is not None:
        for login_pwd in candidates:
            for sudo_pwd in sudo_passwords or ():
                args = _ssh_args(login_pwd, vpn_ip, sudo_cmd(sudo_pwd), 5)
                result = _run_ssh(args, 10)
                if _ssh_auth_failed(result):
                    break          # этот пароль входа не подошёл — следующий
                if _sudo_auth_failed(result):
                    continue       # вход есть, но sudo-пароль не подошёл
                return result
        return _SSHFailed()

    for login_pwd in candidates:
        args = _ssh_args(login_pwd, vpn_ip, command, 5)
        result = _run_ssh(args, timeout)
        if not _ssh_auth_failed(result):
            return result
    return _SSHFailed()


def ssh_execute(device, command):
    """Выполнить команду на киоске через SSH (пробует несколько паролей)."""
    if not device or not device.vpn_ip or device.vpn_ip in ('0', 'N/A'):
        return _SSHFailed('SSH: у киоска нет VPN IP')
    return _ssh_run(device.vpn_ip, command, _ssh_candidate_passwords(device))


def ssh_reboot(device):
    """Перезагрузка киоска через sudo (раздельные пароли входа и sudo)."""
    if not device or not device.vpn_ip or device.vpn_ip in ('0', 'N/A'):
        return _SSHFailed('SSH: у киоска нет VPN IP')

    def reboot_cmd(sudo_pwd):
        escaped = sudo_pwd.replace("'", "'\\''")
        return f"printf '%s\\n' '{escaped}' | LC_ALL=C sudo -S reboot"

    return _ssh_run(device.vpn_ip, None, _ssh_candidate_passwords(device),
                    sudo_passwords=_ssh_sudo_passwords(device),
                    sudo_cmd=reboot_cmd)


def _scp_put(device, local_path, remote_path):
    """Копирует локальный файл на киоск по SCP (первый рабочий пароль)."""
    for pwd in _ssh_candidate_passwords(device):
        if not pwd:
            continue
        try:
            result = subprocess.run(
                ['/usr/bin/sshpass', '-p', pwd, '/usr/bin/scp',
                 '-o', 'ConnectTimeout=5', '-o', 'StrictHostKeyChecking=no',
                 '-o', 'UserKnownHostsFile=/dev/null',
                 local_path, f'{settings.DEVICE_SSH_USER}@{device.vpn_ip}:{remote_path}'],
                capture_output=True, text=True, timeout=25
            )
        except subprocess.TimeoutExpired:
            return False, 'Таймаут копирования'
        if result.returncode == 0:
            return True, f'Файл загружен в {remote_path}'
        lower_err = result.stderr.lower()
        if result.returncode != 5 and 'permission denied' not in lower_err:
            return False, result.stderr.strip() or 'Ошибка копирования'
    return False, 'Не удалось подключиться (проверьте SSH-пароль киоска)'


@login_required
def upload_file_to_device(device, uploaded_file, target_path):
    """Копирует загруженный файл на киоск по SCP (первый рабочий пароль)."""
    import os as _os
    import tempfile

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            for chunk in uploaded_file.chunks():
                tf.write(chunk)
            tmp = tf.name
        return _scp_put(device, tmp, target_path)
    finally:
        if tmp and _os.path.exists(tmp):
            _os.remove(tmp)


def ssh_change_password(device, new_password):
    """Меняет пароль пользователя terminal на киоске через sudo chpasswd.

    Вход по SSH — паролем из списка входа; sudo — своим sudo-паролем
    (или тем же, если отдельный не задан). После смены пароля в authorized_keys
    пользователя terminal добавляются публичные ключи из DEVICE_SSH_PUBLIC_KEYS
    (сервер и личные, например с Мака), чтобы не терять доступ. При успехе
    ставится флаг device.password_migrated (бейдж на карточке дашборда).
    Новый пароль не должен быть пустым.
    """
    if not device or not device.vpn_ip or device.vpn_ip in ('0', 'N/A'):
        return False, 'SSH: у киоска нет VPN IP'
    if not new_password:
        return False, 'Не указан новый пароль'

    escaped_user = settings.DEVICE_SSH_USER.replace("'", "'\\''")
    escaped_new = new_password.replace("'", "'\\''")

    def change_cmd(sudo_pwd):
        escaped_sudo = sudo_pwd.replace("'", "'\\''")
        base = ("printf '%s\\n' '{sudo}' | LC_ALL=C sudo -S sh -c "
                "\"printf '%s\\n' '{user}:{new}' | chpasswd\"").format(
                    sudo=escaped_sudo, user=escaped_user, new=escaped_new)
        keys_cmd = _authorized_keys_cmd()
        return base + (f" && {keys_cmd}" if keys_cmd else "")

    result = _ssh_run(device.vpn_ip, None, _ssh_candidate_passwords(device),
                      sudo_passwords=_ssh_sudo_passwords(device),
                      sudo_cmd=change_cmd)
    if result.returncode != 0:
        return False, result.stderr.strip() or 'Ошибка смены пароля'
    Device.objects.filter(pk=device.pk).update(password_migrated=True)
    return True, 'Пароль киоска изменён'


def _ssh_vnc_setup(device, vnc_password):
    """Настраивает x0vncserver на ПАК: кладёт пароль в .vnc/passwd и рестартит сервис."""
    if not device or not device.vpn_ip or device.vpn_ip in ('0', 'N/A'):
        return _SSHFailed('SSH: у киоска нет VPN IP')

    def vnc_cmd(sudo_pwd):
        es = sudo_pwd.replace("'", "'\\''")
        ev = vnc_password.replace("'", "'\\''")
        return ("mkdir -p /home/terminal/.vnc && "
                "printf '%s\\n' '{sudo}' | LC_ALL=C sudo -S sh -c "
                "\"printf '%s\\n' '{vnc}' | vncpasswd -f > /home/terminal/.vnc/passwd.new "
                "&& chown terminal:terminal /home/terminal/.vnc/passwd.new "
                "&& chmod 600 /home/terminal/.vnc/passwd.new "
                "&& mv -f /home/terminal/.vnc/passwd.new /home/terminal/.vnc/passwd "
                "&& systemctl restart x0vncserver.service\"").format(sudo=es, vnc=ev)

    return _ssh_run(device.vpn_ip, None, _ssh_candidate_passwords(device),
                    sudo_passwords=_ssh_sudo_passwords(device),
                    sudo_cmd=vnc_cmd)

@login_required
def dashboard(request):
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')

    all_devices = Device.objects.all()
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

    def _is_problem(dev):
        v = verif_states.get(dev.id)
        v_state = v[0] if v else 'none'
        return (
            (not dev.is_online) or dev.in_repair or
            v_state in ('soon', 'expired') or
            not dev.alco_ok or not dev.tono_ok
        )

    problems_filter = request.GET.get('problems') == '1'
    sort_mode = request.GET.get('sort', 'number')

    device_list = list(
        devices.order_by('hostname').select_related('owner', 'client', 'location')
    )
    for d in device_list:
        d.is_standard = bool(re.fullmatch(r'\d{3,}', d.hostname or ''))

    if problems_filter:
        device_list = [d for d in device_list if _is_problem(d)]

    if sort_mode == 'active':
        aware_min = timezone.now() - timedelta(days=3650)
        device_list.sort(key=lambda d: d.last_mqtt_message or aware_min, reverse=True)
    elif sort_mode == 'problems':
        device_list.sort(key=lambda d: (not _is_problem(d), d.hostname))
    else:
        device_list.sort(key=lambda d: d.hostname)

    med_ready = sum(1 for d in device_list if d.alco_ok and d.tono_ok)
    v_expired = sum(1 for d in device_list if verif_states.get(d.id, ('none',))[0] == 'expired')
    v_soon = sum(1 for d in device_list if verif_states.get(d.id, ('none',))[0] == 'soon')
    problems_count = sum(1 for d in device_list if _is_problem(d))
    shown_online = sum(1 for d in device_list if d.is_online and not d.in_repair)
    shown_offline = sum(1 for d in device_list if not d.is_online and not d.in_repair)

    # Осмотры: сумма по всем дням («всего») и последний снимок («за день/сегодня»).
    all_total = dict(
        DailyExam.objects.values('device_id')
        .annotate(total=Sum('exams'))
        .values_list('device_id', 'total')
    )
    # «За день» — количество осмотров из последнего снимка (без полного перебора
    # всех строк DailyExam на каждую загрузку дашборда).
    latest_snapshot = DailyExam.objects.filter(device_id=OuterRef('pk')).order_by('-date', '-pk')
    today_exams = dict(
        all_devices.annotate(
            _latest_exams=Subquery(latest_snapshot.values('exams')[:1]),
        ).values_list('pk', '_latest_exams')
    )
    # Агрегаты за сегодняшние московские сутки (для шапки дашборда).
    today = timezone.localdate()
    today_qs = DailyExam.objects.filter(date=today)
    today_agg = today_qs.aggregate(exams=Sum('exams'), cancelled=Sum('cancelled'))
    today_exams_total = today_agg['exams'] or 0
    today_cancelled_total = today_agg['cancelled'] or 0
    # Осмотры по дням за последнюю неделю (для мини-графика дашборда).
    week_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    week_agg = dict(
        DailyExam.objects.filter(date__gte=week_days[0], date__lte=today)
        .values('date').annotate(total=Sum('exams'))
        .values_list('date', 'total'))
    week_exams = [{'date': d, 'total': week_agg.get(d, 0)} for d in week_days]
    week_max = max((x['total'] for x in week_exams), default=1) or 1

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
    reset_url = build_qs(request, status='', q='', problems='', sort='')

    devices = device_list
    page_obj = None
    base_qs = ''
    result_count = len(devices)

    online_pct = round(shown_online / result_count * 100) if result_count else 0
    offline_pct = round(shown_offline / result_count * 100) if result_count else 0
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
        'med_ready': med_ready,
        'med_total': result_count,
        'all_total': all_total,
        'today_exams': today_exams,
        'verif_expired': v_expired,
        'verif_soon': v_soon,
        'today_exams_total': today_exams_total,
        'today_cancelled_total': today_cancelled_total,
        'week_exams': week_exams,
        'week_max': week_max,
        'problems_count': problems_count,
        'problems_filter': problems_filter,
        'problems_chip': build_qs(request, problems='1'),
        'problems_off_chip': build_qs(request, problems=''),
        'sort_mode': sort_mode,
        'sort_chips': {
            'number': build_qs(request, sort='number'),
            'active': build_qs(request, sort='active'),
            'problems': build_qs(request, sort='problems'),
        },
        'online_pct': online_pct,
        'offline_pct': offline_pct,
    }
    return render(request, 'devices/dashboard.html', context)


@login_required
def clients_list(request):
    return redirect('/admin/devices/client/')


@login_required
def reports_page(request):
    """Страница отчётов: единый вход ко всем выгрузкам."""
    return render(request, 'devices/reports.html')


@login_required
def analytics_uptime(request):
    return redirect('/admin/devices/device/analytics/')


def _cell_text(value):
    """Чистовой текст ячейки: числа без хвоста .0, остальное — строка."""
    if value is None:
        return ''
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


@user_passes_test(is_admin)
def import_exams(request):
    return redirect('/admin/devices/device/import/')


@login_required
def device_history(request):
    return redirect('/admin/devices/deviceevent/')


@login_required
def device_status_feed(request):
    """JSON-эндпоинт для живого обновления карточек на дашборде."""
    devices = Device.objects.all()
    total = devices.count()
    online = devices.filter(is_online=True, in_repair=False).count()
    offline = devices.filter(is_online=False, in_repair=False).count()
    repair = devices.filter(in_repair=True).count()

    page_status = 'repair' if repair else ('warn' if offline else 'ok')

    today = timezone.localdate()
    exam_agg = DailyExam.objects.filter(date=today).aggregate(
        exams=Sum('exams'), cancelled=Sum('cancelled'))

    payload = {
        'total': total,
        'online': online,
        'offline': offline,
        'repair': repair,
        'page_status': page_status,
        'exams_today': exam_agg['exams'] or 0,
        'cancelled_today': exam_agg['cancelled'] or 0,
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
    daily_exams = device.daily_exams.all()[:10]
    daily_total = device.daily_exams.aggregate(total=Sum('exams'))['total']
    
    context = {
        'device': device,
        'repairs': repairs,
        'tickets': tickets,
        'shipments': shipments,
        'events': events,
        'verifications': verifications,
        'daily_exams': daily_exams,
        'daily_total': daily_total,
    }
    return render(request, 'devices/device_detail_page.html', context)

@user_passes_test(is_admin)
def device_reboot(request, pk):
    device = get_object_or_404(Device, pk=pk)
    
    if not device.vpn_ip or device.vpn_ip in ['0', 'N/A']:
        messages.error(request, f'Нет VPN IP у {device.hostname}')
        return redirect('device_detail_page', pk=pk)
    
    try:
        result = ssh_reboot(device)

        if result.returncode == 0:
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
        result = ssh_execute(device, cmd)

        if result.returncode != 0:
            messages.warning(request, f'⚠️ Ошибка изменения конфига: {result.stderr.strip()}')
            return redirect('device_detail_page', pk=pk)

        ssh_reboot(device)
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
        result = ssh_execute(device, cmd)

        if result.returncode != 0:
            messages.warning(request, f'⚠️ Ошибка изменения конфига: {result.stderr.strip()}')
            return redirect('device_detail_page', pk=pk)

        ssh_reboot(device)
        messages.success(request, f'✅ Сервис {device.hostname} запущен, перезагрузка...')
    except Exception as e:
        messages.error(request, f'❌ Ошибка: {e}')
    
    return redirect('device_detail_page', pk=pk)

@user_passes_test(is_admin)
def device_upload(request, pk):
    """Загрузка файла на киоск по SCP."""
    device = get_object_or_404(Device, pk=pk)
    if request.method == 'POST':
        uploaded = request.FILES.get('file')
        target = (request.POST.get('target_path') or '').strip()
        if not uploaded:
            messages.error(request, 'Выберите файл для загрузки')
        elif not target:
            messages.error(request, 'Укажите путь назначения на киоске (например /tmp/файл)')
        elif not device.vpn_ip or device.vpn_ip in ('0', 'N/A'):
            messages.error(request, f'Нет VPN IP у {device.hostname}')
        else:
            ok, msg = upload_file_to_device(device, uploaded, target)
            if ok:
                messages.success(request, f'{device.hostname}: {msg}')
            else:
                messages.error(request, f'{device.hostname}: {msg}')
    return redirect('device_detail_page', pk=pk)

@user_passes_test(is_admin)
def device_set_password(request, pk):
    """Меняет SSH-пароль киоска на стандартный (settings.DEVICE_SSH_PASSWORD)."""
    device = get_object_or_404(Device, pk=pk)
    if request.method == 'POST':
        target = (request.POST.get('new_password') or '').strip() or settings.DEVICE_SSH_PASSWORD
        if not target:
            messages.error(request, 'Не задан стандартный SSH-пароль в настройках')
        else:
            ok, msg = ssh_change_password(device, target)
            if ok:
                if device.ssh_password != target:
                    Device.objects.filter(pk=device.pk).update(ssh_password=target)
                messages.success(request, f'{device.hostname}: {msg}')
            else:
                messages.error(request, f'{device.hostname}: {msg}')
    return redirect('device_detail_page', pk=pk)


@user_passes_test(is_admin)
def device_vnc_setup(request, pk):
    """Настраивает VNC (x0vncserver) на киоске по кнопке и ставит vnc_ready."""
    device = get_object_or_404(Device, pk=pk)
    if request.method == 'POST':
        if not device.vpn_ip or device.vpn_ip in ('0', 'N/A'):
            messages.error(request, f'{device.hostname}: нет VPN IP')
            return redirect('device_detail_page', pk=pk)
        vnc_pass = getattr(settings, 'DEVICE_VNC_PASSWORD', '') or settings.DEVICE_SSH_PASSWORD
        if not vnc_pass:
            messages.error(request, 'Не задан VNC-пароль (DEVICE_VNC_PASSWORD)')
            return redirect('device_detail_page', pk=pk)
        result = _ssh_vnc_setup(device, vnc_pass)
        if result.returncode == 0:
            Device.objects.filter(pk=device.pk).update(vnc_ready=True)
            messages.success(request, f'{device.hostname}: VNC настроен (x0vncserver, порт 5900)')
        else:
            messages.warning(
                request, f'{device.hostname}: {result.stderr.strip() or "ошибка настройки VNC"}')
    return redirect('device_detail_page', pk=pk)


@user_passes_test(is_admin)
def device_deploy_agent(request, pk):
    """Закидывает info2mqtt.py на киоск (SCP) и ставит agent_deployed."""
    device = get_object_or_404(Device, pk=pk)
    if request.method == 'POST':
        if not device.vpn_ip or device.vpn_ip in ('0', 'N/A'):
            messages.error(request, f'{device.hostname}: нет VPN IP')
            return redirect('device_detail_page', pk=pk)
        import os as _os
        local = _os.path.join(settings.BASE_DIR, 'client', 'info2mqtt.py')
        if not _os.path.exists(local):
            messages.error(request, 'Файл info2mqtt.py не найден в репозитории (client/)')
            return redirect('device_detail_page', pk=pk)
        ok, msg = _scp_put(device, local, '/home/terminal/rtk/info2mqtt.py')
        if ok:
            Device.objects.filter(pk=device.pk).update(agent_deployed=True)
            messages.success(request, f'{device.hostname}: info2mqtt.py загружен и обновлён')
        else:
            messages.warning(request, f'{device.hostname}: {msg}')
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
        failed_hosts = []
        
        for device in devices:
            if not device.vpn_ip or device.vpn_ip in ['0', 'N/A']:
                failed += 1
                continue
            
            try:
                if action == 'reboot':
                    ssh_reboot(device)
                elif action == 'stop':
                    cmd = "sed -i '/^storageService\\.remoteParams\\.host/s/^/#/' /home/terminal/rtk/configuration.local.conf"
                    result = ssh_execute(device, cmd)
                    if result and result.returncode == 0:
                        ssh_reboot(device)
                elif action == 'start':
                    cmd = "sed -i '/^#storageService\\.remoteParams\\.host/s/^#//' /home/terminal/rtk/configuration.local.conf"
                    result = ssh_execute(device, cmd)
                    if result and result.returncode == 0:
                        ssh_reboot(device)
                
                success += 1
            except Exception as e:
                logger.warning('Bulk action %s failed for %s: %s', action, device.hostname, e)
                failed += 1
                failed_hosts.append(device.hostname)
        
        suffix = f' ({", ".join(failed_hosts[:5])})' if failed_hosts else ''
        messages.success(request, f'✅ Выполнено: {success}, ошибок: {failed}{suffix}')
    
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
    return redirect('/admin/devices/repair/')

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
    return redirect('/admin/devices/verification/')

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
    headers = ['Киоск', 'Алкотестер', 'Тонометр', 'Средства в порядке', 'Онлайн', 'Последнее обновление']
    ws.append(headers)
    for d in devices:
        alco = 'OK' if d.alco_ok else 'Ошибка/нет'
        tono = 'OK' if d.tono_ok else 'Ошибка/нет'
        ok = 'Да' if (d.alco_ok and d.tono_ok) else 'Нет'
        ws.append([
            d.hostname, alco, tono, ok,
            'Онлайн' if d.is_online else 'Оффлайн',
            d.last_updated.strftime('%Y-%m-%d %H:%M') if d.last_updated else '',
        ])
    style_header_row(ws, len(headers))
    autosize_columns(ws)
    return xlsx_response(wb, 'med_devices_report.xlsx')
