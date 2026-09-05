from django.contrib.auth.models import User
from django.test import TestCase

from accounts.models import WhitelistPhone
from devices.models import Device
from tickets.models import Ticket
from bot.services import (
    create_user_sync, is_phone_allowed, get_device_by_hostname,
    create_ticket_sync, get_my_tickets_sync, update_ticket_sync, can_edit_ticket_sync,
    get_menu_stats_sync, change_password_sync,
)


class BotServicesTests(TestCase):
    def setUp(self):
        self.device = Device.objects.create(hostname='123')

    def test_create_user_sync_hashes_password_and_sets_profile(self):
        result = create_user_sync('ivan', 'secret-pass', 999, '+79990000000')
        user = User.objects.get(username='ivan')
        self.assertTrue(user.check_password('secret-pass'))
        self.assertNotEqual(user.password, 'secret-pass')
        self.assertEqual(user.profile.role, 'technician')
        self.assertEqual(user.profile.telegram_id, 999)
        self.assertEqual(user.profile.phone, '+79990000000')

    def test_change_password_sync(self):
        create_user_sync('pasha', 'old-pass', 777, '+79991112233')

        ok, err = change_password_sync(777, 'wrong-old', 'new-pass-123')
        self.assertFalse(ok)
        self.assertIn('текущий пароль', err.lower())

        ok, err = change_password_sync(777, 'old-pass', 'short')
        self.assertFalse(ok)
        self.assertIn('6 символов', err.lower())

        ok, err = change_password_sync(777, 'old-pass', 'new-pass-123')
        self.assertTrue(ok)
        self.assertEqual(err, '')
        user = User.objects.get(profile__telegram_id=777)
        self.assertTrue(user.check_password('new-pass-123'))
        self.assertFalse(user.check_password('old-pass'))

    def test_change_password_sync_unlinked(self):
        ok, err = change_password_sync(424242, 'x', 'new-pass-123')
        self.assertFalse(ok)
        self.assertIn('не привязан', err.lower())

    def test_phone_whitelist(self):
        WhitelistPhone.objects.create(phone='+71111111111', is_active=True)
        WhitelistPhone.objects.create(phone='+72222222222', is_active=False)
        self.assertTrue(is_phone_allowed('+71111111111'))
        self.assertFalse(is_phone_allowed('+72222222222'))
        self.assertFalse(is_phone_allowed('+73333333333'))

    def test_get_device_by_hostname_case_insensitive(self):
        dev = get_device_by_hostname('123')
        self.assertEqual(dev, self.device)
        self.assertIsNone(get_device_by_hostname('nope'))

    def test_create_and_list_my_tickets(self):
        user = User.objects.create_user('tech', password='p')
        ticket = create_ticket_sync('123', 'Не включается', 'Иван', '+7111', user)
        self.assertEqual(ticket.device, self.device)
        self.assertEqual(ticket.created_by, user)
        self.assertIn(ticket, get_my_tickets_sync(user.id))

    def test_update_ticket_permission(self):
        owner = User.objects.create_user('owner', password='p')
        other = User.objects.create_user('other', password='p')
        admin = User.objects.create_user('admin', password='p')
        admin.profile.role = 'admin'
        admin.profile.save()

        ticket = create_ticket_sync('123', 'Old', 'Иван', '+7111', owner)

        # Чужой техник не может редактировать
        self.assertIsNone(update_ticket_sync(ticket.id, 'Hack', '', '', other))
        # Владелец может
        updated = update_ticket_sync(ticket.id, 'New', 'Иван', '+7111', owner)
        self.assertIsNotNone(updated)
        ticket.refresh_from_db()
        self.assertEqual(ticket.problem, 'New')

    def test_can_edit_ticket_rules(self):
        owner = User.objects.create_user('owner', password='p')
        admin = User.objects.create_user('admin', password='p')
        admin.profile.role = 'admin'
        admin.profile.save()

        ticket = create_ticket_sync('123', 'Old', 'Иван', '+7111', owner)
        self.assertTrue(can_edit_ticket_sync(ticket.id, admin))
        self.assertTrue(can_edit_ticket_sync(ticket.id, owner))

        other = User.objects.create_user('other', password='p')
        self.assertFalse(can_edit_ticket_sync(ticket.id, other))
        self.assertFalse(can_edit_ticket_sync(999999, admin))

    def test_tickets_module_reexports(self):
        import bot.handlers.tickets as tickets
        required = [
            'ticket_create_start', 'ticket_pak_handler', 'ticket_problem_handler',
            'ticket_name_handler', 'ticket_phone_handler',
            'my_tickets_handler', 'all_tickets_handler', 'ticket_detail_handler',
            'search_start', 'search_result',
            'edit_ticket_start', 'edit_ticket_select', 'edit_field_handler',
            'edit_problem_handler', 'edit_name_handler', 'edit_phone_handler',
            'status_start', 'status_result',
            'TICKET_PAK', 'TICKET_PROBLEM', 'TICKET_NAME', 'TICKET_PHONE',
            'SEARCH_QUERY', 'EDIT_TICKET_SELECT', 'EDIT_TICKET_FIELD',
            'EDIT_TICKET_PROBLEM', 'EDIT_TICKET_NAME', 'EDIT_TICKET_PHONE',
            'STATUS_HOSTNAME',
        ]
        for name in required:
            self.assertTrue(hasattr(tickets, name), f'missing {name}')

    def test_menu_stats_sync(self):
        stats = get_menu_stats_sync()
        for key in ('online', 'offline', 'repair', 'open'):
            self.assertIsInstance(stats[key], int)
