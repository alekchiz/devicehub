"""Статистика по флоту."""
from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import ContextTypes

from bot.formatting import panel, menu_keyboard
from bot.services import get_fleet_stats_sync


@sync_to_async
def get_fleet_stats():
    return get_fleet_stats_sync()


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from bot.management.commands.health_check import get_server_stats

    query = update.callback_query
    if query:
        await query.answer()

    st = await get_fleet_stats()
    try:
        srv = get_server_stats()
    except Exception:
        srv = {}

    body = (
        f"🖥 <b>Киоски:</b> всего {st['total']}\n"
        f"   🟢 Онлайн: {st['online']}   🔴 Оффлайн: {st['offline']}   🟡 В ремонте: {st['repair']}\n\n"
        f"🏥 Средства готовы: <b>{st['med_ready']}/{st['med_total']}</b>\n"
        f"📊 Осмотров сегодня: <b>{st['exams']}</b> (отменено {st['cancelled']})\n"
        f"🛡 Поверок: скоро {st['verif_soon']}, истекло {st['verif_expired']}\n"
        f"📋 Открытых заявок: <b>{st['open_tickets']}</b>"
    )
    if srv:
        body += (
            "\n\n💻 <b>Сервер:</b>\n"
            f"   CPU {srv.get('cpu', '—')}% · RAM {srv.get('ram', '—')}% · Диск {srv.get('disk', '—')}%"
        )

    text = panel('Статистика МедКиоск', body, footer='Обновлено на данный момент')
    if query:
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=menu_keyboard())
    else:
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=menu_keyboard())
