from django.core.management.base import BaseCommand
from django.conf import settings
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from telegram import BotCommand
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bot.handlers.start import start, menu_command
from bot.handlers.register import register_start, register_phone, register_password, link_account, link_confirm, cancel, PHONE_WAIT, PASSWORD_WAIT
from bot.handlers.tickets import (
    ticket_create_start, ticket_pak_handler, ticket_problem_handler,
    ticket_name_handler, ticket_phone_handler, my_tickets_handler, all_tickets_handler,
    ticket_detail_handler, search_start, search_result,
    edit_ticket_start, edit_ticket_select, edit_field_handler,
    edit_problem_handler, edit_name_handler, edit_phone_handler,
    status_start, status_result,
    TICKET_PAK, TICKET_PROBLEM, TICKET_NAME, TICKET_PHONE, SEARCH_QUERY,
    EDIT_TICKET_SELECT, EDIT_TICKET_FIELD, EDIT_TICKET_PROBLEM, EDIT_TICKET_NAME, EDIT_TICKET_PHONE,
    STATUS_HOSTNAME
)
from bot.handlers.start import start, menu_command, health_command
from bot.handlers.users import (
    add_user_start, add_user_username, add_user_password, add_user_role,
    unlink_command, ADD_USERNAME, ADD_PASSWORD, ADD_ROLE,
)
from telegram import Update
from telegram.ext import ContextTypes
from asgiref.sync import sync_to_async
from bot.services import get_profile_sync
import asyncio

@sync_to_async
def get_profile(telegram_id):
    return get_profile_sync(telegram_id)

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "📚 <b>Справка МедКиоск</b>\n\n"
            "/start - Начало работы\n"
            "/menu - Главное меню\n"
            "/status - Статус Киоска\n"
            "/edit - Редактировать заявку\n"
            "/register - Регистрация\n"
            "/link - Привязать аккаунт\n"
            "/adduser - Добавить пользователя (при наличии права)\n"
            "/unlink - Отвязать аккаунт от Telegram",
            parse_mode='HTML'
        )

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
    elif data.startswith('edit_'):
        return await edit_ticket_select(update, context)
    elif data in ('field_problem', 'field_name', 'field_phone', 'edit_save'):
        return await edit_field_handler(update, context)
    elif data.startswith('ticket_'):
        return await ticket_detail_handler(update, context)
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
            "🔍 <b>Статус киоска</b>\n\n"
            "Введите команду с номером киоска, например:\n"
            "<code>/status 123</code>",
            parse_mode='HTML',
            reply_markup=markup
        )
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
            entry_points=[CallbackQueryHandler(ticket_create_start, pattern='^ticket_create$')],
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
                EDIT_TICKET_PROBLEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_problem_handler)],
                EDIT_TICKET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_name_handler)],
                EDIT_TICKET_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_phone_handler)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        status_handler = ConversationHandler(
            entry_points=[CommandHandler('status', status_start)],
            states={
                STATUS_HOSTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, status_result)],
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
        
        callback_handler = CallbackQueryHandler(button_router)
        
        app.add_handler(CommandHandler('start', start))
        app.add_handler(CommandHandler('menu', menu_command))
        app.add_handler(reg_handler)
        app.add_handler(link_handler)
        app.add_handler(ticket_handler)
        app.add_handler(search_handler)
        app.add_handler(edit_handler)
        app.add_handler(status_handler)
        app.add_handler(adduser_handler)
        app.add_handler(CommandHandler('unlink', unlink_command))
        app.add_handler(callback_handler)
        app.add_handler(CommandHandler('health', health_command))
        
        async def set_commands():
            await app.bot.set_my_commands([
                BotCommand('start', '🚀 Начать работу'),
                BotCommand('menu', '📱 Главное меню'),
                BotCommand('status', '🔍 Статус Киоска'),
                BotCommand('edit', '📝 Редактировать заявку'),
                BotCommand('register', '📝 Регистрация'),
                BotCommand('link', '🔗 Привязать аккаунт'),
                BotCommand('adduser', '➕ Добавить пользователя (для админов)'),
                BotCommand('unlink', '🔗 Отвязать Telegram'),
            ])
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(set_commands())
        
        self.stdout.write(self.style.SUCCESS('🤖 Бот запущен'))
        app.run_polling()
