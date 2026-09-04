"""Добавление пользователей через бота (только для пользователей с правом bot_admin)."""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from asgiref.sync import sync_to_async

ADD_USERNAME, ADD_PASSWORD, ADD_ROLE = range(3)

ROLE_CHOICES = {
    'technician': 'Техник',
    'observer': 'Наблюдатель',
    'admin': 'Админ',
}


@sync_to_async
def _is_bot_admin(telegram_id):
    from accounts.models import UserProfile
    return UserProfile.objects.filter(
        telegram_id=telegram_id, bot_admin=True
    ).exists()


@sync_to_async
def _create_user(username, password, role):
    from django.contrib.auth.models import User
    if User.objects.filter(username__iexact=username).exists():
        return False, 'Такой логин уже существует'
    user = User.objects.create_user(username=username, password=password)
    user.profile.role = role
    user.profile.save()
    return True, ''


@sync_to_async
def _unlink(telegram_id):
    from accounts.models import UserProfile
    updated = UserProfile.objects.filter(telegram_id=telegram_id).update(telegram_id=None)
    return updated


async def add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _is_bot_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав на добавление пользователей.")
        return ConversationHandler.END
    await update.message.reply_text(
        "➕ <b>Добавление пользователя</b>\n\nВведите логин для входа в МедКиоск:",
        parse_mode='HTML',
    )
    return ADD_USERNAME


async def add_user_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nu_username'] = update.message.text.strip()
    await update.message.reply_text("Теперь введите пароль:")
    return ADD_PASSWORD


async def add_user_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nu_password'] = update.message.text.strip()
    roles = "/".join(ROLE_CHOICES.keys())
    await update.message.reply_text(
        f"Выберите роль: <b>{roles}</b>\n(по умолчанию technician)",
        parse_mode='HTML',
    )
    return ADD_ROLE


async def add_user_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = context.user_data.get('nu_username')
    password = context.user_data.get('nu_password')
    role = (update.message.text.strip().lower() or 'technician')

    if role not in ROLE_CHOICES:
        await update.message.reply_text(
            f"❌ Неизвестная роль. Введите одну из: {'/'.join(ROLE_CHOICES.keys())}"
        )
        return ADD_ROLE

    ok, error = await _create_user(username, password, role)
    if ok:
        await update.message.reply_text(
            f"✅ Пользователь <b>{username}</b> создан.\n"
            f"Роль: <b>{ROLE_CHOICES[role]}</b>\n"
            "Данные для входа передай ему.",
            parse_mode='HTML',
        )
    else:
        await update.message.reply_text(f"❌ {error}")
    return ConversationHandler.END


async def unlink_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _unlink(update.effective_user.id):
        await update.message.reply_text("🔗 Аккаунт отвязан от Telegram.")
    else:
        await update.message.reply_text("У вас не привязан аккаунт.")