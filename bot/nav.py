"""Навигация бота: отправка ответов и главное меню на инлайн-кнопках."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


async def send(update, context, text, **kwargs):
    """Отправить ответ безопасно: если диалог начат кнопкой — редактируем её
    сообщение, иначе просто отвечаем на текст. Параметры Telegram-лишние.
    """
    kwargs.setdefault('parse_mode', 'HTML')
    q = update.callback_query
    if q:
        try:
            await q.answer()
            await q.edit_message_text(text, **kwargs)
            return
        except Exception:
            pass
    await update.effective_message.reply_text(text, **kwargs)


def main_menu(is_admin):
    """Главное меню инлайн-кнопками (без reply-клавиатуры)."""
    rows = [
        [InlineKeyboardButton('🔍 Статус киоска', callback_data='menu_status'),
         InlineKeyboardButton('📊 Статистика', callback_data='menu_stats')],
        [InlineKeyboardButton('✍️ Новая заявка', callback_data='menu_create'),
         InlineKeyboardButton('📋 Мои заявки', callback_data='menu_my')],
        [InlineKeyboardButton('🚑 Сервер', callback_data='menu_health'),
         InlineKeyboardButton('❓ Помощь', callback_data='menu_help')],
    ]
    if is_admin:
        rows.insert(2, [InlineKeyboardButton('🛠 Киоск-инструменты', callback_data='menu_tools')])
    return InlineKeyboardMarkup(rows)