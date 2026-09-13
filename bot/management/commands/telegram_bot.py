from django.core.management.base import BaseCommand
from django.conf import settings
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from telegram import BotCommand
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bot.handlers.start import start, menu_command
from bot.handlers.stats import stats_handler
from bot.formatting import panel
from bot.nav import main_menu
from bot.handlers.register import (register_start, register_phone, register_password,
                                   link_account, link_confirm, cancel,
                                   PHONE_WAIT, PASSWORD_WAIT, LINK_PASSWORD_WAIT)
from bot.handlers.tickets import (
    ticket_create_start, ticket_pak_handler, ticket_problem_handler,
    ticket_name_handler, ticket_phone_handler, my_tickets_handler, all_tickets_handler,
    ticket_detail_handler, search_start, search_result,
    edit_ticket_start, edit_ticket_select, edit_field_handler,
    edit_problem_handler, edit_name_handler, edit_phone_handler,
    edit_back,
    status_start, status_result,
    TICKET_PAK, TICKET_PROBLEM, TICKET_NAME, TICKET_PHONE, SEARCH_QUERY,
    EDIT_TICKET_SELECT, EDIT_TICKET_FIELD, EDIT_TICKET_PROBLEM, EDIT_TICKET_NAME, EDIT_TICKET_PHONE,
    STATUS_HOSTNAME
)
from bot.handlers.start import start, menu_command, health_command
from bot.handlers.tickets_list import my_tickets_message
from bot.handlers.users import (
    add_user_start, add_user_username, add_user_password, add_user_role,
    unlink_command, ADD_USERNAME, ADD_PASSWORD, ADD_ROLE,
)
from bot.handlers.password import (
    password_start, password_current, password_new, password_confirm,
    CURRENT_PW, NEW_PW, CONFIRM_PW,
)
from bot.handlers.kiosk_ctl import (
    tools_start, tools_hostname, tools_button, TOOLS_HOSTNAME,
)
from telegram import Update
from telegram.ext import ContextTypes
import asyncio

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "📚 <b>МедКиоск — справка</b>\n"
            "<code>────────────────────────────</code>\n\n"
            "🗂 <b>Меню (кнопки):</b>\n"
            "🔍 Статус киоска · 📊 Статистика\n"
            "✍️ Новая заявка · 📋 Мои заявки\n"
            "🛠 Киоск-инструменты (админ)\n"
            "🚑 Сервер · ❓ Помощь\n\n"
            "📜 <b>Команды:</b>\n"
            "🔍 /status — статус киоска\n"
            "📊 /stats — статистика по устройствам\n"
            "🛠 /tools — управление киоском (админ)\n"
            "🚑 /health — состояние сервера\n"
            "📱 /menu — главное меню\n"
            "📝 /create — новая заявка\n"
            "📝 /edit — редактировать заявку\n"
            "📝 /register — регистрация\n"
            "🔗 /link — привязать аккаунт\n"
            "🔐 /password — сменить пароль\n"
            "➕ /adduser — добавить пользователя (админ)\n"
            "🔗 /unlink — отвязать Telegram",
            parse_mode='HTML'
        )


async def help_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = panel(
        'МедКиоск — справка',
        '\n'.join([
            '🗂 Меню (кнопки): Статус · Статистика ·',
            'Новая заявка · Мои заявки · Киоск-инструменты',
            '· Сервер · Помощь',
            '',
            '🔍 /status — статус киоска',
            '🛠 /tools — управление киоском (админ)',
            '🚑 /health — состояние сервера',
            '📝 /create — новая заявка',
            '📝 /edit — редактировать заявку',
            '📝 /register — регистрация',
            '🔗 /link — привязать аккаунт',
            '🔐 /password — сменить пароль',
        ])
    )
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_menu(False))


async def reply_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия reply-кнопок (текстовые метки)."""
    text = (update.message.text or '').strip()
    if text == '📊 Статистика':
        return await stats_handler(update, context)
    if text == '❓ Помощь':
        return await help_message(update, context)
    if text == '🚑 Сервер':
        return await health_command(update, context)
    if text == '📋 Мои заявки':
        return await my_tickets_message(update, context)
    return

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await menu_command(update, context)

async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data == 'ticket_create':
        return await ticket_create_start(update, context)
    elif data == 'my_tickets':
        return await my_tickets_handler(update, context)
    elif data == 'all_tickets':
        return await all_tickets_handler(update, context)
    elif data == 'edit_ticket':
        return await edit_ticket_start(update, context)
    elif data == 'edit_back':
        return await edit_back(update, context)
    elif data in ('field_problem', 'field_name', 'field_phone', 'edit_save'):
        return await edit_field_handler(update, context)
    elif data.startswith('edit_'):
        return await edit_ticket_select(update, context)
    elif data.startswith('ticket_'):
        return await ticket_detail_handler(update, context)
    elif data.startswith('tst_'):
        return await tools_button(update, context)
    elif data == 'menu_stats':
        return await stats_handler(update, context)
    elif data == 'menu_my':
        return await my_tickets_handler(update, context)
    elif data == 'menu_health':
        return await health_command(update, context)
    elif data == 'menu_help':
        return await help_handler(update, context)
    elif data in ('search_my', 'search_all'):
        return await search_start(update, context)
    elif data == 'help':
        return await help_handler(update, context)
    elif data == 'menu':
        return await menu_callback(update, context)
    elif data == 'kiosk_status':
        await query.answer()
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 В главное меню", callback_data='menu')]
        ])
        await query.edit_message_text(
            "🏥 <b>Статус киоска</b>\n"
            "<code>────────────────────────────</code>\n\n"
            "Введите команду с номером киоска, например:\n"
            "<code>/status 123</code>\n"
            "Или /menu для возврата в меню",
            parse_mode='HTML',
            reply_markup=markup
        )
    elif data == 'stats':
        return await stats_handler(update, context)
    elif data == 'cancel':
        await query.answer()
        await query.edit_message_text("❌ Отменено")
        return ConversationHandler.END

class Command(BaseCommand):
    help = 'Запуск Telegram бота'

    def handle(self, *args, **options):
        token = settings.TELEGRAM_BOT_TOKEN
        if not token or token == 'ВАШ_ТОКЕН_БОТА':
            self.stdout.write(self.style.ERROR('❌ Укажите TELEGRAM_BOT_TOKEN в settings.py'))
            return
        
        app = Application.builder().token(token).build()
        
        reg_handler = ConversationHandler(
            entry_points=[CommandHandler('register', register_start)],
            states={
                PHONE_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_phone)],
                PASSWORD_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_password)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        link_handler = ConversationHandler(
            entry_points=[CommandHandler('link', link_account)],
            states={
                PASSWORD_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, link_confirm)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        ticket_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(ticket_create_start, pattern='^ticket_create$'),
                CallbackQueryHandler(ticket_create_start, pattern='^menu_create$'),
                CommandHandler('create', ticket_create_start),
                MessageHandler(filters.Text('✍️ Новая заявка'), ticket_create_start),
            ],
            states={
                TICKET_PAK: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_pak_handler)],
                TICKET_PROBLEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_problem_handler)],
                TICKET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_name_handler)],
                TICKET_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_phone_handler)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        search_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(search_start, pattern='^(search_my|search_all)$')],
            states={
                SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_result)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        edit_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(edit_ticket_start, pattern='^edit_ticket$'),
                CommandHandler('edit', edit_ticket_start),
            ],
            states={
                EDIT_TICKET_SELECT: [CallbackQueryHandler(edit_ticket_select, pattern='^edit_')],
                EDIT_TICKET_FIELD: [
                    CallbackQueryHandler(edit_field_handler, pattern='^(field_problem|field_name|field_phone|edit_save|menu)$'),
                ],
                EDIT_TICKET_PROBLEM: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, edit_problem_handler),
                    CallbackQueryHandler(edit_back, pattern='^edit_back$'),
                ],
                EDIT_TICKET_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, edit_name_handler),
                    CallbackQueryHandler(edit_back, pattern='^edit_back$'),
                ],
                EDIT_TICKET_PHONE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, edit_phone_handler),
                    CallbackQueryHandler(edit_back, pattern='^edit_back$'),
                ],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        status_handler = ConversationHandler(
            entry_points=[
                CommandHandler('status', status_start),
                CallbackQueryHandler(status_start, pattern='^menu_status$'),
                MessageHandler(filters.Text('🔍 Статус киоска'), status_start),
            ],
            states={
                STATUS_HOSTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, status_result)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )

        tools_handler = ConversationHandler(
            entry_points=[
                CommandHandler('tools', tools_start),
                CallbackQueryHandler(tools_start, pattern='^menu_tools$'),
                MessageHandler(filters.Text('🛠 Киоск-инструменты'), tools_start),
            ],
            states={
                TOOLS_HOSTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, tools_hostname)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )

        adduser_handler = ConversationHandler(
            entry_points=[CommandHandler('adduser', add_user_start)],
            states={
                ADD_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_username)],
                ADD_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_password)],
                ADD_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_role)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )

        password_handler = ConversationHandler(
            entry_points=[CommandHandler('password', password_start)],
            states={
                CURRENT_PW: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_current)],
                NEW_PW: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_new)],
                CONFIRM_PW: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_confirm)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        callback_handler = CallbackQueryHandler(button_router)
        
        app.add_handler(CommandHandler('start', start))
        app.add_handler(CommandHandler('menu', menu_command))
        app.add_handler(reg_handler)
        app.add_handler(link_handler)
        app.add_handler(ticket_handler)
        app.add_handler(search_handler)
        app.add_handler(edit_handler)
        app.add_handler(status_handler)
        app.add_handler(tools_handler)
        app.add_handler(adduser_handler)
        app.add_handler(password_handler)
        app.add_handler(CommandHandler('unlink', unlink_command))
        app.add_handler(CommandHandler('stats', stats_handler))
        app.add_handler(callback_handler)
        app.add_handler(CommandHandler('health', health_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_router))
        
        async def set_commands():
            await app.bot.set_my_commands([
                BotCommand('start', '🚀 Начать работу'),
                BotCommand('menu', '📱 Главное меню'),
                BotCommand('status', '🔍 Статус Киоска'),
                BotCommand('edit', '📝 Редактировать заявку'),
                BotCommand('stats', '📊 Статистика по устройствам'),
                BotCommand('tools', '🛠 Управление киоском (для админов)'),
                BotCommand('register', '📝 Регистрация'),
                BotCommand('link', '🔗 Привязать аккаунт'),
                BotCommand('password', '🔐 Сменить пароль'),
                BotCommand('adduser', '➕ Добавить пользователя (для админов)'),
                BotCommand('unlink', '🔗 Отвязать Telegram'),
            ])
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(set_commands())
        
        self.stdout.write(self.style.SUCCESS('🤖 Бот запущен'))
        app.run_polling()
