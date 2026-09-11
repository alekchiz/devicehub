from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from asgiref.sync import sync_to_async
from django.db import IntegrityError
from bot.services import create_user_sync, authenticate_user_sync, link_telegram_sync, is_phone_allowed
import re

PHONE_WAIT = 1
PASSWORD_WAIT = 2
LINK_PASSWORD_WAIT = 20

@sync_to_async
def create_user(username, password, telegram_id, phone):
    return create_user_sync(username, password, telegram_id, phone)

@sync_to_async
def authenticate_user(username, password):
    return authenticate_user_sync(username, password)

@sync_to_async
def link_telegram(user, telegram_id):
    link_telegram_sync(user, telegram_id)

@sync_to_async
def check_phone(phone):
    return is_phone_allowed(phone)

@sync_to_async
def telegram_registered(telegram_id):
    from accounts.models import UserProfile
    return UserProfile.objects.filter(telegram_id=telegram_id).exists()

@sync_to_async
def phone_registered(phone):
    from accounts.models import UserProfile
    return UserProfile.objects.filter(phone=phone).exists()

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 <b>Регистрация нового пользователя</b>\n\n"
        "Введите ваш номер телефона в формате +7XXXXXXXXXX\n"
        "Или /cancel для отмены",
        parse_mode='HTML'
    )
    return PHONE_WAIT

async def register_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not re.match(r'^\+7\d{10}$', phone):
        await update.message.reply_text("❌ Неверный формат. Введите +7XXXXXXXXXX")
        return PHONE_WAIT
    
    allowed = await check_phone(phone)
    if not allowed:
        await update.message.reply_text(
            "❌ Ваш номер телефона не найден в списке разрешённых.\n"
            "Обратитесь к администратору для получения доступа."
        )
        return ConversationHandler.END
    
    context.user_data['phone'] = phone
    await update.message.reply_text("Придумайте пароль для входа на сайт (минимум 6 символов):")
    return PASSWORD_WAIT

async def register_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    if len(password) < 6:
        await update.message.reply_text("❌ Пароль слишком короткий. Минимум 6 символов.")
        return PASSWORD_WAIT
    
    phone = context.user_data['phone']
    telegram_id = update.effective_user.id

    if await telegram_registered(telegram_id):
        await update.message.reply_text(
            '❌ Этот Telegram уже зарегистрирован. Используйте /menu.')
        return ConversationHandler.END
    if await phone_registered(phone):
        await update.message.reply_text(
            '❌ На этот номер уже создан аккаунт.')
        return ConversationHandler.END

    username = str(telegram_id)

    try:
        await create_user(username, password, telegram_id, phone)
        await update.message.reply_text(
            f"✅ Регистрация завершена!\n\n"
            f"Логин: {username}\n"
            f"Роль: Техник\n\n"
            f"Используйте /menu"
        )
    except IntegrityError:
        await update.message.reply_text(
            '❌ Ошибка регистрации: учётная запись уже существует.')
    except Exception:
        await update.message.reply_text(
            '❌ Не удалось зарегистрироваться. Попробуйте позже или обратитесь к администратору.')

    return ConversationHandler.END

async def link_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔗 Привязка аккаунта\n\n"
        "Введите ваш логин и пароль через пробел:\n"
        "Или /cancel для отмены"
    )
    return LINK_PASSWORD_WAIT

async def link_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        parts = update.message.text.strip().split()
        if len(parts) != 2:
            await update.message.reply_text("❌ Введите логин и пароль через пробел")
            return LINK_PASSWORD_WAIT

        username, password = parts
        user = await authenticate_user(username, password)

        if user:
            await link_telegram(user, update.effective_user.id)
            await update.message.reply_text(f"✅ Аккаунт {username} привязан! Используйте /menu")
        else:
            await update.message.reply_text("❌ Неверный логин или пароль")
            return LINK_PASSWORD_WAIT
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено. Используйте /menu")
    return ConversationHandler.END
