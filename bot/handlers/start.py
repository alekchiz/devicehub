from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from asgiref.sync import sync_to_async
from bot.services import get_profile_sync, get_menu_stats_sync
from bot.formatting import panel, main_keyboard

@sync_to_async
def get_profile(telegram_id):
    return get_profile_sync(telegram_id)

@sync_to_async
def get_menu_stats():
    return get_menu_stats_sync()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    profile = await get_profile(telegram_id)
    
    if profile:
        await update.message.reply_text(
            f"👋 С возвращением, {profile['username']}!\n"
            f"Роль: {profile['role']}",
            reply_markup=main_keyboard()
        )
    else:
        await update.message.reply_text(
            "👋 Добро пожаловать в МедКиоск!\n\n"
            "Для регистрации используйте /register\n"
            "Или /link для привязки аккаунта",
            reply_markup=main_keyboard()
        )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    profile = await get_profile(telegram_id)

    if not profile:
        text = "Сначала зарегистрируйтесь: /register или привяжите аккаунт: /link"
        if update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return

    stats = await get_menu_stats()
    role = profile['role_code']

    header = panel(
        'МедКиоск · главное меню',
        (
            f"Здравствуйте, <b>{profile['username']}</b> 👋\n"
            f"Роль: {profile['role']}\n\n"
            f"🖥 Киоски: 🟢 {stats['online']} · 🔴 {stats['offline']} · 🟡 {stats['repair']}\n"
            f"📋 Открытых заявок: {stats['open']}"
        ),
        footer='Выберите действие ниже'
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(header, parse_mode='HTML')
        try:
            await update.effective_message.reply_text(
                'Выберите действие ниже', reply_markup=main_keyboard())
        except Exception:
            pass
    else:
        await update.message.reply_text(header, parse_mode='HTML', reply_markup=main_keyboard())
async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /health - статистика сервера"""
    from bot.management.commands.health_check import get_server_stats
    import urllib.request
    
    stats = get_server_stats()

    message = panel(
        'Сервер МедКиоск',
        (
            f"💻 CPU: <b>{stats['cpu']}%</b>\n"
            f"🧠 RAM: <b>{stats['ram']}%</b>\n"
            f"💾 Диск: <b>{stats['disk']}%</b>"
        )
    )

    await update.message.reply_text(message, parse_mode='HTML')
