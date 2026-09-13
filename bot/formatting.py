"""Единый стиль сообщений и клавиатур бота МедКиоск."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from html import escape

DIV = '<code>────────────────────────────</code>'
DIV_T = '<code>────────────────────────────────</code>'

TICKET_EMOJI = {'created': '🆕', 'in_progress': '🔧', 'completed': '✅', 'closed': '🔒'}
REPAIR_EMOJI = {'created': '🆕', 'in_progress': '🔧', 'ready': '✅'}


def panel(title, body='', footer=''):
    parts = [f"🏥 <b>{title}</b>", DIV_T]
    if body:
        parts.append(str(body).strip('\n'))
    if footer:
        parts.append(DIV_T)
        parts.append(footer)
    return '\n'.join(parts)


def kv(label, value):
    if value is None or value == '':
        value = '—'
    value = escape(str(value))
    return f"{label} <b>{value}</b>"


def status_badge(is_online, in_repair, offline_duration=None):
    if in_repair:
        return '🟡 В ремонте'
    if is_online:
        return '🟢 Онлайн'
    return '🔴 Оффлайн' + (f" ({offline_duration})" if offline_duration else '')


def bar(pct):
    """Текстовая полоса загрузки ██░... (для моноширинного шрифта)."""
    if pct is None:
        return None
    pct = max(0, int(pct))
    filled = min(10, pct // 10)
    return '<code>' + '█' * filled + '░' * (10 - filled) + '</code>'


def device_status(data):
    """Современная карточка статуса ПАК (разделы + модули)."""
    d = data
    host = escape(str(d['hostname']))
    lines = [
        f"🖥 <b>Киоск {host}</b> · {status_badge(d['is_online'], d['in_repair'], d['offline_duration'])}",
        DIV_T,
    ]

    meta = []
    loc = d.get('client') or d.get('location')
    if loc:
        meta.append(kv('📍 Объект', loc))
    if d.get('owner'):
        meta.append(kv('👤 Владелец', d['owner']))
    if d.get('vpn_ip'):
        meta.append(kv('🌐 VPN', d['vpn_ip']))
    if d.get('anydesk'):
        meta.append(kv('💻 AnyDesk', d['anydesk']))
    if d.get('software'):
        meta.append(kv('📦 ПО', d['software']))
    if d.get('os'):
        meta.append(kv('💿 ОС', d['os']))
    if meta:
        lines.append(DIV)
        lines.extend(meta)

    c, m, dd = bar(d.get('cpu_load')), bar(d.get('memory_percent')), bar(d.get('hdd_percent'))
    if c is not None or m is not None or dd is not None:
        lines.append(DIV)
        lines.append('📈 <b>Ресурсы</b>')
    if c is not None:
        lines.append(f"💻 CPU  {c}  <b>{d['cpu_load']}%</b>")
    if m is not None:
        lines.append(f"🧠 RAM  {m}  <b>{d['memory_percent']}%</b>")
    if dd is not None:
        lines.append(f"💾 Диск {dd}  <b>{d['hdd_percent']}%</b>")
    temp = d.get('temperature') or d.get('cpu_temperature')
    if temp:
        lines.append(kv('🌡 Темп.', temp))
    if d.get('uptime_formatted'):
        lines.append(kv('⏱ Аптайм', d['uptime_formatted']))

    def _mod(name, ico, ok, enabled):
        if enabled is False:
            return f"{ico} {name:<6} · ⛔ выкл"
        good = ok if ok is not None else True
        return f"{ico} {name:<6} · {'✅ вкл' if good else '❌ проблема'}"

    lines.append(DIV)
    lines.append('🧩 <b>Модули</b>')
    lines.append(_mod('Алко', '🍺', d.get('alco_ok'), d.get('alco_enabled')))
    lines.append(_mod('Тоно', '💊', d.get('tono_ok'), d.get('tonometer_enabled')))
    lines.append(_mod('Термо', '🌡', None, d.get('thermometer_enabled')))

    if d.get('exams_today') is not None:
        lines.append(kv('📊 Осмотров сегодня', d['exams_today']))
    if d.get('verif'):
        state, until = d['verif']
        labels = {'expired': '🛡 Поверка истекла', 'soon': '🛡 Поверка скоро',
                  'ok': '🛡 Поверка действует'}
        if state in labels:
            lines.append(f"{labels[state]} · до {until:%d.%m.%Y}")
    if d.get('last_mqtt'):
        lines.append(kv('🕐 Активность', d['last_mqtt'].strftime('%d.%m.%Y %H:%M')))

    if d.get('tickets'):
        lines.append(DIV)
        lines.append('📋 <b>Последние заявки:</b>')
        for t in d['tickets'][:3]:
            lines.append(f"  #{t.id} {TICKET_EMOJI.get(t.status, '❓')} · {escape(str(t.problem))[:40]}")
    if d.get('repairs'):
        lines.append('🔧 <b>Последние ремонты:</b>')
        for r in d['repairs'][:3]:
            lines.append(f"  #{r.id} {REPAIR_EMOJI.get(r.status, '❓')} · {escape(str(r.problem))[:40]}")

    return '\n'.join(lines)


def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🔙 Главное меню', callback_data='menu')],
    ])
