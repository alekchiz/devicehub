"""Смена пароля через бота (/password). Работает только в личке и без админа."""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from asgiref.sync import sync_to_async
from bot.services import change_password_sync, get_profile_sync

CURRENT_PW, NEW_PW, CONFIRM_PW = range(3)


@sync_to_async
def _change_password(telegram_id, current, new):
    return change_password_sync(telegram_id, current, new)


@sync_to_async
def _get_profile(telegram_id):
    return get_profile_sync(telegram_id)


async def password_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        await update.message.reply_text(
            "⚠️ Команда /password работает только в личном чате с ботом."
        )
        return ConversationHandler.END

    profile = await _get_profile(update.effective_user.id)
    if not profile:
        await update.message.reply_text(
            "Сначала привяжите аккаунт: /link, затем смените пароль."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🔐 <b>Смена пароля</b>\n\nВведите текущий пароль:\n"
        "Или /cancel для отмены",
        parse_mode='HTML',
    )
    return CURRENT_PW


async def password_current(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['pw_current'] = update.message.text.strip()
    await update.message.reply_text("Введите новый пароль (минимум 6 символов):")
    return NEW_PW


async def password_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_password = update.message.text.strip()
    if len(new_password) < 6:
        await update.message.reply_text("❌ Пароль слишком короткий. Минимум 6 символов.")
        return NEW_PW
    context.user_data['pw_new'] = new_password
    await update.message.reply_text("Повторите новый пароль:")
    return CONFIRM_PW


async def password_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_password = context.user_data.get('pw_new')
    confirm = update.message.text.strip()

    if not new_password or new_password != confirm:
        await update.message.reply_text("❌ Пароли не совпадают. Введите новый пароль снова:")
        return NEW_PW

    ok, error = await _change_password(
        update.effective_user.id,
        context.user_data.get('pw_current'),
        new_password,
    )

    context.user_data.pop('pw_current', None)
    context.user_data.pop('pw_new', None)

    if ok:
        await update.message.reply_text(
            "✅ Пароль изменён. Используйте новый пароль для входа на сайт."
        )
    else:
        await update.message.reply_text(f"❌ {error}")

    return ConversationHandler.END
