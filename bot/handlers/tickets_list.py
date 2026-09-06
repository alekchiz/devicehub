"""Просмотр/детали заявок."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from .tickets_common import (
    STATUS_EMOJI, format_ticket_message, menu_keyboard,
    get_profile, get_my_tickets, get_all_tickets, get_ticket,
)
from bot.formatting import panel


async def my_tickets_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id
    profile = await get_profile(telegram_id)
    tickets = await get_my_tickets(profile['user_id'])

    if not tickets:
        await query.edit_message_text(
            panel('Мои заявки', 'Пока нет заявок'), parse_mode='HTML',
            reply_markup=menu_keyboard())
        return ConversationHandler.END

    keyboard = []
    for t in tickets[:8]:
        keyboard.append([
            InlineKeyboardButton(
                f"#{t.id} {STATUS_EMOJI.get(t.status, '❓')} {t.device.hostname}",
                callback_data=f'ticket_{t.id}'
            )
        ])
    keyboard.append([InlineKeyboardButton("🔍 Поиск по заявкам", callback_data='search_my')])
    keyboard.append([InlineKeyboardButton("🔙 В главное меню", callback_data='menu')])

    await query.edit_message_text(
        panel('Мои заявки', 'Выберите заявку для просмотра:'),
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


async def all_tickets_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    tickets = await get_all_tickets()

    if not tickets:
        await query.edit_message_text(
            panel('Все заявки', 'Пока нет заявок'), parse_mode='HTML',
            reply_markup=menu_keyboard())
        return ConversationHandler.END

    keyboard = []
    for t in tickets[:8]:
        keyboard.append([
            InlineKeyboardButton(
                f"#{t.id} {STATUS_EMOJI.get(t.status, '❓')} {t.device.hostname}",
                callback_data=f'ticket_{t.id}'
            )
        ])
    keyboard.append([InlineKeyboardButton("🔍 Поиск по заявкам", callback_data='search_all')])
    keyboard.append([InlineKeyboardButton("🔙 В главное меню", callback_data='menu')])

    await query.edit_message_text(
        panel('Все заявки', 'Выберите заявку для просмотра:'),
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


async def ticket_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    ticket_id = int(query.data.split('_')[1])
    ticket = await get_ticket(ticket_id)

    if not ticket:
        await query.edit_message_text("❌ Заявка не найдена", reply_markup=menu_keyboard())
        return ConversationHandler.END

    await query.edit_message_text(
        format_ticket_message(ticket),
        parse_mode='HTML',
        reply_markup=menu_keyboard()
    )
    return ConversationHandler.END


async def my_tickets_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """«Мои заявки» по кнопке reply-клавиатуры (через text-сообщение)."""
    profile = await get_profile(update.effective_user.id)
    tickets = await get_my_tickets(profile['user_id'])

    if not tickets:
        await update.message.reply_text(
            panel('Мои заявки', 'Пока нет заявок'), parse_mode='HTML',
            reply_markup=menu_keyboard())
        return

    keyboard = []
    for t in tickets[:8]:
        keyboard.append([
            InlineKeyboardButton(
                f"#{t.id} {STATUS_EMOJI.get(t.status, '❓')} {t.device.hostname}",
                callback_data=f'ticket_{t.id}'
            )
        ])
    keyboard.append([InlineKeyboardButton('🔍 Поиск по заявкам', callback_data='search_my')])
    keyboard.append([InlineKeyboardButton('🔙 Главное меню', callback_data='menu')])

    await update.message.reply_text(
        panel('Мои заявки', 'Выберите заявку для просмотра:'),
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
