"""Статус Киоска."""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .tickets_common import STATUS_HOSTNAME, menu_keyboard, get_device_full


async def status_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status - запрос номера киоска."""
    await update.message.reply_text(
        "🔍 <b>Проверка статуса Киоска</b>\n\n"
        "Введите номер киоска:\n"
        "Или /cancel для отмены",
        parse_mode='HTML'
    )
    return STATUS_HOSTNAME


async def status_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ статуса Киоска."""
    hostname = update.message.text.strip()
    data = await get_device_full(hostname)

    if not data['found']:
        await update.message.reply_text(
            f"❌ Киоск '<b>{hostname}</b>' не найден",
            parse_mode='HTML',
            reply_markup=menu_keyboard()
        )
        return ConversationHandler.END

    if data['in_repair']:
        status_text = "🟡 В ремонте"
    elif data['is_online']:
        status_text = "🟢 Онлайн"
    else:
        status_text = f"🔴 Оффлайн ({data['offline_duration']})" if data['offline_duration'] else "🔴 Оффлайн"

    text = (
        f"🖥 <b>{data['hostname']}</b>\n"
        f"<code>──────────────────────────────</code>\n"
        f"📡 Статус: {status_text}\n"
        f"🌐 VPN: {data['vpn_ip'] or '—'}\n"
        f"💻 AnyDesk: {data['anydesk'] or '—'}\n"
        f"📦 ПО: {data['software'] or '—'}\n"
        f"💿 ОС: {data['os'] or '—'}\n"
        f"🍺 Алкотестер: {data['alco'] or '—'}\n"
        f"💊 Тонометр: {data['tonometer'] or '—'}\n"
        f"👤 Владелец: {data['owner'] or '—'}\n"
        f"📍 Локация: {data['location'] or '—'}\n"
    )

    if data['last_mqtt']:
        text += f"\n🕐 Последняя активность: {data['last_mqtt'].strftime('%d.%m.%Y %H:%M')}"

    if data['tickets']:
        text += "\n\n📋 <b>Последние заявки:</b>"
        for t in data['tickets']:
            text += f"\n  #{t.id} | {t.get_status_display()} | {t.problem[:40]}"

    if data['repairs']:
        text += "\n\n🔧 <b>Последние ремонты:</b>"
        for r in data['repairs']:
            text += f"\n  #{r.id} | {r.get_status_display()} | {r.problem[:40]}"

    await update.message.reply_text(text, parse_mode='HTML', reply_markup=menu_keyboard())
    return ConversationHandler.END