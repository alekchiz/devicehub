"""Единый стиль сообщений и клавиатур бота МедКиоск."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

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
    """Стильная карточка статуса ПАК."""
    d = data
    lines = [
        f"🖥 <b>Киоск {d['hostname']}</b> · {status_badge(d['is_online'], d['in_repair'], d['offline_duration'])}",
        DIV_T,
    ]
    loc = d.get('client') or d.get('location')
    if loc:
        lines.append(kv('📍 Объект', loc))
    if d.get('vpn_ip'):
        lines.append(kv('🌐 VPN', d['vpn_ip']))
    if d.get('anydesk'):
        lines.append(kv('💻 AnyDesk', d['anydesk']))
    if d.get('software'):
        lines.append(kv('📦 ПО', d['software']))
    if d.get('os'):
        lines.append(kv('💿 ОС', d['os']))

    c, m, dd = bar(d.get('cpu_load')), bar(d.get('memory_percent')), bar(d.get('hdd_percent'))
    if c is not None or m is not None or dd is not None:
        lines.append(DIV)
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

    lines.append('')
    alco = '✅' if d.get('alco_ok') else '❌'
    tono = '✅' if d.get('tono_ok') else '❌'
    lines.append(f"🍺 Алко {alco}   ·   💊 Тоно {tono}")
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
            lines.append(f"  #{t.id} {TICKET_EMOJI.get(t.status, '❓')} · {t.problem[:40]}")
    if d.get('repairs'):
        lines.append('🔧 <b>Последние ремонты:</b>')
        for r in d['repairs'][:3]:
            lines.append(f"  #{r.id} {REPAIR_EMOJI.get(r.status, '❓')} · {r.problem[:40]}")

    return '\n'.join(lines)


def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🔙 Главное меню', callback_data='menu')],
    ])
