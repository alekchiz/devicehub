"""Поиск заявок."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from .tickets_common import (
    STATUS_EMOJI, SEARCH_QUERY, menu_keyboard, get_profile, search_tickets,
)


async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['search_type'] = query.data

    await query.edit_message_text(
        "🔍 <b>Поиск заявок</b>\n\nВведите часть номера Киоска или текст проблемы:",
        parse_mode='HTML'
    )
    return SEARCH_QUERY


async def search_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.message.text.strip()
    user_id = None

    if context.user_data.get('search_type') == 'search_my':
        profile = await get_profile(update.effective_user.id)
        user_id = profile['user_id']

    tickets = await search_tickets(q, user_id)

    if not tickets:
        await update.message.reply_text(
            f"🔍 По запросу '<b>{q}</b>' ничего не найдено",
            parse_mode='HTML',
            reply_markup=menu_keyboard()
        )
        return ConversationHandler.END

    keyboard = []
    for t in tickets[:8]:
        keyboard.append([
            InlineKeyboardButton(
                f"#{t.id} {STATUS_EMOJI.get(t.status, '❓')} {t.device.hostname}",
                callback_data=f'ticket_{t.id}'
            )
        ])
    keyboard.append([InlineKeyboardButton("🔙 В главное меню", callback_data='menu')])

    await update.message.reply_text(
        f"🔍 <b>Результаты поиска:</b> '{q}'\nВыберите заявку:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END