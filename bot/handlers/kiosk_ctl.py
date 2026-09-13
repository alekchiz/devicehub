"""Бот: управление и доступ к киоску (только для админов).

Дублирует часть кнопок веб-раздела «Управление и доступ» на детальной странице
киоска: Reboot / Стоп / Старт, смена SSH-пароля, настройка VNC, обновление
info2mqtt, тумблеры модулей (алко/тоно/термо) и показ ссылок доступа.
Загрузка файла на киоск остаётся только в вебе.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler
from asgiref.sync import sync_to_async

from bot.formatting import panel
from bot.nav import send

TOOLS_HOSTNAME = 40

# callback-данные для inline-клавиатуры (короткие, <64 байт)
TOOL_REBOOT = 'tst_reboot'
TOOL_STOP = 'tst_stop'
TOOL_START = 'tst_start'
TOOL_PW = 'tst_pw'
TOOL_VNC = 'tst_vnc'
TOOL_AGENT = 'tst_agent'
TOOL_LINKS = 'tst_links'
TOOL_EXIT = 'tst_exit'
TOOL_YES = 'tst_yes'
TOOL_NO = 'tst_no'
TOOL_MOD_ALCO = 'tst_module_alco'
TOOL_MOD_TONO = 'tst_module_tono'
TOOL_MOD_THERMO = 'tst_module_thermo'
TOOL_MOD_PREFIX = 'tst_mod_'  # tst_mod_<mod>_on / _off
TOOL_CHECK = 'tst_check'
TOOL_FULL = 'tst_full'

_LABEL = {'alco': 'алкотестер', 'tonometer': 'тонометр', 'thermometer': 'термометр'}


def _parse_module_toggle(data):
    """Разбор callback модуля: 'tst_mod_<mod>_<on|off>' -> (mod, action)."""
    parts = data.split('_')
    if len(parts) == 4 and parts[0] == 'tst' and parts[1] == 'mod' and parts[3] in ('on', 'off'):
        return parts[2], parts[3]
    return None


# ---------- синхронные обёртки над devices.views ----------

@sync_to_async
def _admin_profile(telegram_id):
    from bot.services import get_profile_sync
    p = get_profile_sync(telegram_id)
    if p and p.get('role_code') == 'admin':
        return p
    return None


@sync_to_async
def _get_device(pk):
    from devices.models import Device
    from django.core.exceptions import ObjectDoesNotExist
    try:
        return Device.objects.get(pk=pk)
    except ObjectDoesNotExist:
        return None


@sync_to_async
def _exec_reboot(device):
    from devices.views import ssh_reboot
    r = ssh_reboot(device)
    return 'OK' if r.returncode == 0 else (r.stderr or 'ошибка reboot')


@sync_to_async
def _exec_stop_start(device, mode):
    from devices.views import ssh_execute, ssh_reboot
    if mode == 'stop':
        cmd = "sed -i '/^storageService\\.remoteParams\\.host/s/^/#/' /home/terminal/rtk/configuration.local.conf"
    else:
        cmd = "sed -i '/^#storageService\\.remoteParams\\.host/s/^#//' /home/terminal/rtk/configuration.local.conf"
    r = ssh_execute(device, cmd)
    if r.returncode != 0:
        return 'Ошибка: ' + (r.stderr or 'команда не выполнена')
    rr = ssh_reboot(device)
    if rr.returncode == 0:
        return 'OK, киоск перезапускается'
    return 'Конфиг изменён, но перезагрузка не прошла: ' + (rr.stderr or '')


@sync_to_async
def _exec_pw(device):
    from django.conf import settings
    from devices.models import Device
    from devices.views import ssh_change_password
    ok, msg = ssh_change_password(device, settings.DEVICE_SSH_PASSWORD)
    if ok:
        Device.objects.filter(pk=device.pk).update(
            ssh_password=settings.DEVICE_SSH_PASSWORD)
    return msg


@sync_to_async
def _exec_vnc(device):
    from django.conf import settings
    from devices.models import Device
    from devices.views import _ssh_vnc_setup, _clean_ssh_msg
    vnc = getattr(settings, 'DEVICE_VNC_PASSWORD', '') or settings.DEVICE_SSH_PASSWORD
    r = _ssh_vnc_setup(device, vnc)
    if r.returncode == 0:
        Device.objects.filter(pk=device.pk).update(vnc_ready=True)
        return 'VNC настроен (порт 5900)'
    return _clean_ssh_msg(r.stderr) or f'ошибка настройки VNC (код {r.returncode})'


@sync_to_async
def _exec_agent(device):
    import os
    from django.conf import settings
    from devices.models import Device
    from devices.views import _scp_put
    local = os.path.join(settings.BASE_DIR, 'client', 'info2mqtt.py')
    if not os.path.exists(local):
        return 'Файл info2mqtt.py не найден в client/'
    ok, msg = _scp_put(device, local, '/home/terminal/rtk/info2mqtt.py')
    if ok:
        Device.objects.filter(pk=device.pk).update(agent_deployed=True)
    return msg


@sync_to_async
def _exec_module(device, module, action):
    from django.conf import settings
    from devices.models import Device
    from devices.views import (_read_device_conf, _toggle_module_in_conf,
                               _write_device_conf, ssh_reboot)
    key = getattr(settings, 'DEVICE_MODULE_TOGGLE_KEYS', {}).get(module)
    field = {'alco': 'alco_enabled', 'tonometer': 'tonometer_enabled',
             'thermometer': 'thermometer_enabled'}.get(module)
    name = _LABEL.get(module, module)
    verb = 'включён' if action == 'enable' else 'выключен'
    if not key or not field:
        return 'Неизвестный модуль'
    conf = _read_device_conf(device)
    if conf is None:
        return 'Не удалось прочитать device.conf'
    new_conf, changed = _toggle_module_in_conf(conf, key, action)
    if not changed:
        return f'{name} уже {verb}'
    if not _write_device_conf(device, new_conf):
        return 'Не удалось записать device.conf'
    Device.objects.filter(pk=device.pk).update(**{field: action == 'enable'})
    ssh_reboot(device)
    return f'{name} {verb}, киоск перезапускается'


@sync_to_async
def _exec_module_states(device):
    """Текущее состояние модулей: device.conf (живое) + флаг в БД."""
    from django.conf import settings
    from devices.views import _read_device_conf, _module_enabled
    keys = getattr(settings, 'DEVICE_MODULE_TOGGLE_KEYS', {})
    labels = {'alco': 'Алко', 'tonometer': 'Тоно', 'thermometer': 'Термо'}
    dbflag = {
        'alco': device.alco_enabled,
        'tonometer': device.tonometer_enabled,
        'thermometer': device.thermometer_enabled,
    }
    conf = _read_device_conf(device)
    lines = []
    for mod, key in keys.items():
        if conf is not None:
            live = 'вкл ✅' if _module_enabled(conf, key) else 'выкл ⛔'
        else:
            live = 'не прочитано'
        dbv = dbflag.get(mod)
        db = 'вкл' if dbv is not False else ('выкл' if dbv is False else '—')
        lines.append(f"{labels.get(mod, mod)}: конфиг — {live} · БД — {db}")
    online = '🟢 онлайн' if device.is_online else '🔴 оффлайн'
    return f"{online}\n" + '\n'.join(lines)


async def _run_full(device):
    """Комплекс: сменить пароль -> info2mqtt -> VNC, отчёт по шагам."""
    steps = []
    steps.append('🔑 Пароль: ' + await _exec_pw(device))
    steps.append('📡 info2mqtt: ' + await _exec_agent(device))
    steps.append('👁 VNC: ' + await _exec_vnc(device))
    return '\n'.join(steps)


# ---------- вью меню и клавиатуры ----------

def tools_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('⚡ Reboot', callback_data=TOOL_REBOOT),
         InlineKeyboardButton('⏹ Стоп', callback_data=TOOL_STOP),
         InlineKeyboardButton('▶️ Старт', callback_data=TOOL_START)],
        [InlineKeyboardButton('⚙️ Полная настройка', callback_data=TOOL_FULL)],
        [InlineKeyboardButton('🔑 Сменить пароль', callback_data=TOOL_PW),
         InlineKeyboardButton('👁 VNC', callback_data=TOOL_VNC)],
        [InlineKeyboardButton('📡 info2mqtt', callback_data=TOOL_AGENT),
         InlineKeyboardButton('🔗 Ссылки', callback_data=TOOL_LINKS)],
        [InlineKeyboardButton('🍺 Алко', callback_data=TOOL_MOD_ALCO),
         InlineKeyboardButton('💊 Тоно', callback_data=TOOL_MOD_TONO),
         InlineKeyboardButton('🌡 Термо', callback_data=TOOL_MOD_THERMO)],
        [InlineKeyboardButton('🔎 Состояние модулей', callback_data=TOOL_CHECK)],
        [InlineKeyboardButton('✅ Выйти', callback_data=TOOL_EXIT)],
    ])


def module_markup(module):
    on = f'{TOOL_MOD_PREFIX}{module}_on'
    off = f'{TOOL_MOD_PREFIX}{module}_off'
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🟢 Включить', callback_data=on),
         InlineKeyboardButton('🔴 Выключить', callback_data=off)],
        [InlineKeyboardButton('🔙 Назад', callback_data='tst_back')],
    ])


def _confirm_text(action_text):
    return (f'Подтвердите действие:\n{action_text}\n\n'
            f'Это перезапустит сервис/киоск при необходимости.')


def _confirm_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ Да', callback_data=TOOL_YES),
         InlineKeyboardButton('❌ Нет', callback_data=TOOL_NO)],
    ])


async def tools_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_profile(update.effective_user.id):
        await send(update, context, panel('Доступ запрещён', 'Только администраторы.'))
        return ConversationHandler.END
    context.user_data.pop('tools_hostname', None)
    context.user_data.pop('tools_device_id', None)
    context.user_data.pop('tools_pending', None)
    await send(update, context,
               '🛠 <b>Киоск-инструменты</b>\n\nВведите номер киоска (например 001):')
    return TOOLS_HOSTNAME


async def tools_hostname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from bot.handlers.tickets_common import find_device
    host = (update.message.text or '').strip()
    device = await find_device(host)
    if not device:
        await update.message.reply_text(
            f'Киоск «{host}» не найден. Введите другой номер или /cancel:')
        return TOOLS_HOSTNAME
    context.user_data['tools_hostname'] = device.hostname
    context.user_data['tools_device_id'] = device.pk
    context.user_data.pop('tools_pending', None)
    await update.message.reply_text(
        panel('Киоск-инструменты',
              f"Киоск: <b>{device.hostname}</b> · {device.vpn_ip or '—'}\n"
              'Выберите действие:'),
        parse_mode='HTML', reply_markup=tools_markup())
    return ConversationHandler.END


# ---------- обработка inline-кнопок ----------

async def tools_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    hostname = context.user_data.get('tools_hostname')
    if not hostname:
        await query.edit_message_text('Сессия завершена. Запустите /tools заново.')
        return
    device = await _get_device(context.user_data.get('tools_device_id'))
    if not device:
        await query.edit_message_text('Киоск не найден. Запустите /tools заново.')
        return

    data = query.data
    pending = context.user_data.pop('tools_pending', None)

    # Выход / отмена
    if data == TOOL_EXIT:
        context.user_data.pop('tools_hostname', None)
        context.user_data.pop('tools_device_id', None)
        await query.edit_message_text('🛠 Завершено. Используйте /menu.')
        return

    if data == TOOL_NO or data == 'tst_back':
        context.user_data.pop('tools_pending', None)
        await query.edit_message_text(
            panel('Киоск-инструменты', f'Киоск: <b>{hostname}</b>\nВыберите действие:'),
            parse_mode='HTML', reply_markup=tools_markup())
        return

    if data == TOOL_YES:
        if not pending:
            await query.edit_message_text('Нет ожидающего действия.',
                                          reply_markup=tools_markup())
            return
        text = await _run_pending(device, pending)
        await query.edit_message_text(
            panel('Киоск-инструменты', f'Киоск: <b>{hostname}</b>\n📌 {text}\nВыберите действие:'),
            parse_mode='HTML', reply_markup=tools_markup())
        return

    # Ссылки доступа — сразу, без подтверждения
    if data == TOOL_LINKS:
        links = []
        vpn = device.vpn_ip
        if vpn and vpn not in ('0', 'N/A'):
            links.append(f'🌐 <b>VPN:</b> {vpn}')
            links.append(f'<a href="ssh://terminal@{vpn}">SSH</a> · '
                         f'<a href="vnc://{vpn}:5900">VNC (:5900)</a>')
        if device.anydesk and device.anydesk not in ('0', 'N/A', 'not_installed'):
            links.append(f'💻 <b>AnyDesk:</b> {device.anydesk}')
        await query.edit_message_text(
            panel('Ссылки доступа', f"Киоск: <b>{hostname}</b>\n" + '\n'.join(links or ['—'])),
            parse_mode='HTML', reply_markup=tools_markup())
        return

    # info2mqtt — безопасно, выполняем сразу
    if data == TOOL_AGENT:
        text = await _exec_agent(device)
        await query.edit_message_text(
            panel('Киоск-инструменты', f"Киоск: <b>{hostname}</b>\n📡 {text}\nВыберите действие:"),
            parse_mode='HTML', reply_markup=tools_markup())
        return

    # Состояние модулей — безопасно, выполняем сразу
    if data == TOOL_CHECK:
        text = await _exec_module_states(device)
        await query.edit_message_text(
            panel('Состояние модулей', f"Киоск: <b>{hostname}</b>\n{text}\nВыберите действие:"),
            parse_mode='HTML', reply_markup=tools_markup())
        return

    # Подменю модулей
    if data in (TOOL_MOD_ALCO, TOOL_MOD_TONO, TOOL_MOD_THERMO):
        module = {'tst_module_alco': 'alco', 'tst_module_tono': 'tonometer',
                  'tst_module_thermo': 'thermometer'}[data]
        await query.edit_message_text(
            panel('Модуль', f"Киоск: <b>{hostname}</b>\n{_LABEL[module]} — включить или выключить?"),
            parse_mode='HTML', reply_markup=module_markup(module))
        return

    # Модуль on/off — просим подтверждение
    if data.startswith(TOOL_MOD_PREFIX):
        parsed = _parse_module_toggle(data)
        if not parsed:
            await query.edit_message_text('Неизвестная команда модуля.',
                                          reply_markup=tools_markup())
            return
        module, action = parsed
        context.user_data['tools_pending'] = f'mod_{module}_{action}'
        await query.edit_message_text(
            _confirm_text(f"{_LABEL.get(module, module)}: {action == 'on' and 'включить' or 'выключить'}"),
            reply_markup=_confirm_markup())
        return

    # Разрушительные действия — просим подтверждение
    confirm_map = {
        TOOL_REBOOT: ('reboot', 'Перезагрузить киоск'),
        TOOL_FULL: ('full', 'Полная настройка: сменить пароль + info2mqtt + VNC'),
        TOOL_STOP: ('stop', 'Остановить сервис (перезапуск)'),
        TOOL_START: ('start', 'Запустить сервис (перезапуск)'),
        TOOL_PW: ('pw', 'Сменить SSH-пароль на стандартный'),
        TOOL_VNC: ('vnc', 'Настроить VNC (перезапуск)'),
    }
    if data in confirm_map:
        action, desc = confirm_map[data]
        context.user_data['tools_pending'] = action
        await query.edit_message_text(_confirm_text(desc), reply_markup=_confirm_markup())
        return

    # Неизвестный callback
    await query.edit_message_text('Неизвестная команда.', reply_markup=tools_markup())


async def _run_pending(device, pending):
    """Выполняет отложенное после подтверждения действие."""
    if pending == 'reboot':
        return '⚡ Reboot: ' + await _exec_reboot(device)
    if pending == 'full':
        return '⚙️ <b>Полная настройка</b>:\n' + await _run_full(device)
    if pending == 'stop':
        return '⏹ Стоп: ' + await _exec_stop_start(device, 'stop')
    if pending == 'start':
        return '▶️ Старт: ' + await _exec_stop_start(device, 'start')
    if pending == 'pw':
        return '🔑 Пароль: ' + await _exec_pw(device)
    if pending == 'vnc':
        return '👁 VNC: ' + await _exec_vnc(device)
    if pending.startswith('mod_'):
        _, module, action = pending.split('_')
        act = 'enable' if action == 'on' else 'disable'
        return '🛠 ' + await _exec_module(device, module, act)
    return 'Неизвестное действие'
