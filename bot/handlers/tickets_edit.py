"""Редактирование заявок: ввод поля НЕ выкидывает из диалога (единый «Назад»)."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from bot.formatting import panel, menu_keyboard
from bot.handlers.start import menu_command
from .tickets_common import (
    STATUS_EMOJI, EDIT_TICKET_SELECT, EDIT_TICKET_FIELD,
    EDIT_TICKET_PROBLEM, EDIT_TICKET_NAME, EDIT_TICKET_PHONE,
    format_ticket_message, get_profile, get_my_tickets, get_all_tickets,
    get_ticket, can_edit_ticket, update_ticket,
)


def _edit_ui(ticket, problem, name, phone):
    """Экран «Что меняем?» (значения из context)."""
    text = panel(
        'Редактирование заявки #{}'.format(ticket.id),
        (
            '📦 Киоск: {}\n'
            '📝 Проблема: {}\n'
            '👤 ФИО: {}\n'
            '📞 Телефон: {}\n\n'
            '<b>Что меняем?</b>'
        ).format(ticket.device.hostname, problem, name, phone),
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton('📝 Проблема', callback_data='field_problem')],
        [InlineKeyboardButton('👤 ФИО', callback_data='field_name')],
        [InlineKeyboardButton('📞 Телефон', callback_data='field_phone')],
        [InlineKeyboardButton('✅ Сохранить', callback_data='edit_save')],
        [InlineKeyboardButton('🔙 Главное меню', callback_data='menu')],
    ])
    return text, markup


def _field_prompt(label, current):
    text = panel(
        'Изменение: ' + label,
        'Текущее значение:\n<b>{}</b>\n\nВведите новое:'.format(current),
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton('◀️ Назад', callback_data='edit_back')],
    ])
    return text, markup


async def edit_ticket_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    telegram_id = update.effective_user.id
    profile = await get_profile(telegram_id)

    if profile['role_code'] == 'observer':
        text = '❌ У вас нет прав на редактирование заявок'
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
        text = '📝 Нет заявок доступных для редактирования'
        if query:
            await query.edit_message_text(text, reply_markup=menu_keyboard())
        else:
            await update.message.reply_text(text, reply_markup=menu_keyboard())
        return ConversationHandler.END

    keyboard = []
    for t in editable[:8]:
        keyboard.append([
            InlineKeyboardButton(
                '#{} {} {}'.format(t.id, STATUS_EMOJI.get(t.status, '❓'), t.device.hostname),
                callback_data='edit_{}'.format(t.id)
            )
        ])
    keyboard.append([InlineKeyboardButton('🔙 Главное меню', callback_data='menu')])

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

    parts = query.data.split('_')
    if len(parts) < 2 or not parts[1].isdigit():
        # Стrayный callback (edit_save/edit_back вне диалога) — не падаем.
        await query.edit_message_text('❌ Заявка не выбрана', reply_markup=menu_keyboard())
        return ConversationHandler.END
    ticket_id = int(parts[1])
    ticket = await get_ticket(ticket_id)

    telegram_id = update.effective_user.id
    profile = await get_profile(telegram_id)

    can = await can_edit_ticket(ticket_id, profile['user'])
    if not can:
        await query.edit_message_text('❌ Нет доступа к редактированию', reply_markup=menu_keyboard())
        return ConversationHandler.END

    context.user_data['edit_ticket_id'] = ticket_id
    context.user_data['edit_problem'] = ticket.problem
    context.user_data['edit_name'] = ticket.contact_name
    context.user_data['edit_phone'] = ticket.contact_phone

    text, markup = _edit_ui(ticket, ticket.problem, ticket.contact_name, ticket.contact_phone)
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
    return EDIT_TICKET_FIELD


async def edit_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат на экран «Что меняем?» из шага ввода поля."""
    query = update.callback_query
    await query.answer()
    ticket_id = context.user_data.get('edit_ticket_id')
    if not ticket_id:
        return await menu_command(update, context)
    ticket = await get_ticket(ticket_id)
    if not ticket:
        await query.edit_message_text('❌ Заявка не найдена', reply_markup=menu_keyboard())
        return ConversationHandler.END
    text, markup = _edit_ui(
        ticket,
        context.user_data.get('edit_problem', ticket.problem),
        context.user_data.get('edit_name', ticket.contact_name),
        context.user_data.get('edit_phone', ticket.contact_phone),
    )
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
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
            message = '✅ <b>Заявка обновлена!</b>\n\n' + format_ticket_message(ticket)
            await query.edit_message_text(message, parse_mode='HTML', reply_markup=menu_keyboard())
        else:
            await query.edit_message_text('❌ Ошибка сохранения', reply_markup=menu_keyboard())
        return ConversationHandler.END

    if field == 'menu':
        return await menu_command(update, context)

    context.user_data['edit_field'] = field
    label_map = {
        'field_problem': ('Проблема', context.user_data.get('edit_problem', '')),
        'field_name': ('ФИО', context.user_data.get('edit_name', '')),
        'field_phone': ('Телефон', context.user_data.get('edit_phone', '')),
    }
    label, current = label_map.get(field, ('Поле', ''))
    text, markup = _field_prompt(label, current)

    if field == 'field_problem':
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
        return EDIT_TICKET_PROBLEM
    if field == 'field_name':
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
        return EDIT_TICKET_NAME
    if field == 'field_phone':
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
        return EDIT_TICKET_PHONE
    return EDIT_TICKET_FIELD


async def _continue_after_field(update, context, key):
    """Сохраняет введённое поле и возвращает на экран редактирования (без выхода)."""
    context.user_data[key] = update.message.text
    ticket = await get_ticket(context.user_data.get('edit_ticket_id'))
    if not ticket:
        await update.message.reply_text('❌ Заявка не найдена', reply_markup=menu_keyboard())
        return ConversationHandler.END
    text, markup = _edit_ui(
        ticket,
        context.user_data.get('edit_problem', ticket.problem),
        context.user_data.get('edit_name', ticket.contact_name),
        context.user_data.get('edit_phone', ticket.contact_phone),
    )
    await update.message.reply_text('✅ Поле сохранено. Продолжаем редактирование...')
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=markup)
    return EDIT_TICKET_FIELD


async def edit_problem_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _continue_after_field(update, context, 'edit_problem')


async def edit_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _continue_after_field(update, context, 'edit_name')


async def edit_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _continue_after_field(update, context, 'edit_phone')
