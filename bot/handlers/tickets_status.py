"""Статус Киоска."""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .tickets_common import (
    STATUS_HOSTNAME, menu_keyboard, get_device_full, require_privileged,
)
from bot.formatting import panel, device_status
from bot.nav import send


async def status_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status - запрос номера киоска."""
    _, denied = await require_privileged(update.effective_user.id)
    if denied:
        await send(update, context, panel('Доступ запрещён', denied))
        return ConversationHandler.END
    await send(update, context,
        panel(
            'Проверка статуса',
            "Введите <b>номер киоска</b> (например: 123):\n"
            "Или /cancel для отмены"
        ))
    return STATUS_HOSTNAME


async def status_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ статуса Киоска."""
    hostname = update.message.text.strip()
    data = await get_device_full(hostname)

    if not data['found']:
        await update.message.reply_text(
            panel('Ошибка', f"Киоск <b>{hostname}</b> не найден. Проверьте номер."),
            parse_mode='HTML',
            reply_markup=menu_keyboard()
        )
        return ConversationHandler.END

    text = device_status(data)
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=menu_keyboard())
    return ConversationHandler.END
