"""Редактирование заявок."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from bot.handlers.start import menu_command
from .tickets_common import (
    STATUS_EMOJI, EDIT_TICKET_SELECT, EDIT_TICKET_FIELD,
    EDIT_TICKET_PROBLEM, EDIT_TICKET_NAME, EDIT_TICKET_PHONE,
    format_ticket_message, menu_keyboard,
    get_profile, get_my_tickets, get_all_tickets,
    get_ticket, can_edit_ticket, update_ticket,
)
from bot.formatting import panel


async def edit_ticket_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    telegram_id = update.effective_user.id
    profile = await get_profile(telegram_id)

    if profile['role_code'] == 'observer':
        text = "❌ У вас нет прав на редактирование заявок"
        if query:
            await query.edit_message_text(text, reply_markup=menu_keyboard())
        else:
            await update.message.reply_text(text, reply_markup=menu_keyboard())
        return ConversationHandler.END

    if profile['role_code'] == 'admin':
        tickets = await get_all_tickets()
    else:
        tickets = await get_my_tickets(profile['user_id'])

    editable = [t for t in tickets if t.status in ['created', 'in_progress']]
    if profile['role_code'] == 'technician':
        editable = [t for t in editable if t.created_by_id == profile['user_id']]

    if not editable:
        text = "📝 Нет заявок доступных для редактирования"
        if query:
            await query.edit_message_text(text, reply_markup=menu_keyboard())
        else:
            await update.message.reply_text(text, reply_markup=menu_keyboard())
        return ConversationHandler.END

    keyboard = []
    for t in editable[:8]:
        keyboard.append([
            InlineKeyboardButton(
                f"#{t.id} {STATUS_EMOJI.get(t.status, '❓')} {t.device.hostname}",
                callback_data=f'edit_{t.id}'
            )
        ])
    keyboard.append([InlineKeyboardButton("🔙 В главное меню", callback_data='menu')])

    text = panel('Редактирование заявки', 'Выберите заявку для изменения:')
    markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=markup)
    return EDIT_TICKET_SELECT


async def edit_ticket_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    ticket_id = int(query.data.split('_')[1])
    ticket = await get_ticket(ticket_id)

    telegram_id = update.effective_user.id
    profile = await get_profile(telegram_id)

    can = await can_edit_ticket(ticket_id, profile['user'])
    if not can:
        await query.edit_message_text("❌ Нет доступа к редактированию", reply_markup=menu_keyboard())
        return ConversationHandler.END

    context.user_data['edit_ticket_id'] = ticket_id
    context.user_data['edit_problem'] = ticket.problem
    context.user_data['edit_name'] = ticket.contact_name
    context.user_data['edit_phone'] = ticket.contact_phone

    text = panel(
        f"Редактирование заявки #{ticket.id}",
        (
            f"📦 Киоск: {ticket.device.hostname}\n"
            f"📝 Проблема: {ticket.problem[:100]}\n"
            f"👤 ФИО: {ticket.contact_name}\n"
            f"📞 Телефон: {ticket.contact_phone}\n\n"
            f"<b>Что меняем?</b>"
        )
    )

    keyboard = [
        [InlineKeyboardButton("📝 Проблема", callback_data='field_problem')],
        [InlineKeyboardButton("👤 ФИО", callback_data='field_name')],
        [InlineKeyboardButton("📞 Телефон", callback_data='field_phone')],
        [InlineKeyboardButton("✅ Сохранить", callback_data='edit_save')],
        [InlineKeyboardButton("🔙 Отмена", callback_data='menu')],
    ]

    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    return EDIT_TICKET_FIELD


async def edit_field_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    field = query.data

    if field == 'edit_save':
        ticket_id = context.user_data.get('edit_ticket_id')
        telegram_id = update.effective_user.id
        profile = await get_profile(telegram_id)

        ticket = await update_ticket(
            ticket_id=ticket_id,
            problem=context.user_data.get('edit_problem', ''),
            contact_name=context.user_data.get('edit_name', ''),
            contact_phone=context.user_data.get('edit_phone', ''),
            user=profile['user']
        )

        if ticket:
            message = "✅ <b>Заявка обновлена!</b>\n\n" + format_ticket_message(ticket)
            await query.edit_message_text(message, parse_mode='HTML', reply_markup=menu_keyboard())
        else:
            await query.edit_message_text("❌ Ошибка сохранения", reply_markup=menu_keyboard())

        return ConversationHandler.END
    elif field == 'menu':
        return await menu_command(update, context)

    context.user_data['edit_field'] = field

    if field == 'field_problem':
        await query.edit_message_text(
            f"📝 Текущая проблема:\n{context.user_data.get('edit_problem', '')}\n\nВведите новое описание:"
        )
        return EDIT_TICKET_PROBLEM
    elif field == 'field_name':
        await query.edit_message_text(
            f"👤 Текущее ФИО: {context.user_data.get('edit_name', '')}\n\nВведите новое ФИО:"
        )
        return EDIT_TICKET_NAME
    elif field == 'field_phone':
        await query.edit_message_text(
            f"📞 Текущий телефон: {context.user_data.get('edit_phone', '')}\n\nВведите новый телефон:"
        )
        return EDIT_TICKET_PHONE


async def edit_problem_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['edit_problem'] = update.message.text
    await update.message.reply_text("✅ Проблема обновлена. Нажмите /edit для продолжения.")
    return ConversationHandler.END


async def edit_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['edit_name'] = update.message.text
    await update.message.reply_text("✅ ФИО обновлено. Нажмите /edit для продолжения.")
    return ConversationHandler.END


async def edit_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['edit_phone'] = update.message.text
    await update.message.reply_text("✅ Телефон обновлён. Нажмите /edit для продолжения.")
    return ConversationHandler.END
