"""Создание заявки классификации."""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .tickets_common import (
    TICKET_PAK, TICKET_PROBLEM, TICKET_NAME, TICKET_PHONE,
    format_ticket_message, menu_keyboard, get_profile, find_device, create_ticket, get_admins,
)
from bot.formatting import panel


async def ticket_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        panel('Новая заявка',
              "Введите <b>номер киоска</b> (например: 123):\n"
              "Или /cancel для отмены"),
        parse_mode='HTML'
    )
    return TICKET_PAK


async def ticket_pak_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hostname = update.message.text.strip()
    device = await find_device(hostname)

    if not device:
        await update.message.reply_text(
            f"❌ Киоск '<b>{hostname}</b>' не найден.\nПроверьте номер и введите ещё раз:",
            parse_mode='HTML'
        )
        return TICKET_PAK

    context.user_data['ticket_hostname'] = hostname
    await update.message.reply_text("📝 <b>Опишите проблему:</b>", parse_mode='HTML')
    return TICKET_PROBLEM


async def ticket_problem_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ticket_problem'] = update.message.text
    await update.message.reply_text("👤 <b>Введите ФИО для связи:</b>", parse_mode='HTML')
    return TICKET_NAME


async def ticket_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ticket_name'] = update.message.text
    await update.message.reply_text("📞 <b>Введите телефон для связи:</b>", parse_mode='HTML')
    return TICKET_PHONE


async def ticket_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        telegram_id = update.effective_user.id
        profile = await get_profile(telegram_id)

        ticket = await create_ticket(
            hostname=context.user_data['ticket_hostname'],
            problem=context.user_data['ticket_problem'],
            contact_name=context.user_data['ticket_name'],
            contact_phone=update.message.text,
            user=profile['user']
        )

        message = "✅ <b>Заявка создана!</b>\n\n" + format_ticket_message(ticket)
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=menu_keyboard())

        admins = await get_admins()
        for admin in admins:
            if admin.telegram_id:
                try:
                    await context.bot.send_message(
                        admin.telegram_id,
                        "🔔 <b>Новая заявка!</b>\n\n" + format_ticket_message(ticket),
                        parse_mode='HTML'
                    )
                except Exception:
                    pass

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

    return ConversationHandler.END
