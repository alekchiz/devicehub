from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from .views import _client_ip

from .models import UserProfile


class UserProfileModelTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_profile_auto_created_on_user(self):
        user = User.objects.create_user(username='user1')
        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertEqual(user.profile.role, 'technician')

    def test_role_update_persists(self):
        user = User.objects.create_user(username='user2')
        user.profile.role = 'admin'
        user.profile.save()
        user.refresh_from_db()
        self.assertEqual(user.profile.role, 'admin')

    def test_telegram_id_is_unique(self):
        user1 = User.objects.create_user(username='a')
        user2 = User.objects.create_user(username='b')

        user1.profile.telegram_id = 111
        user1.profile.save()

        user2.profile.telegram_id = 111
        with self.assertRaises(Exception):
            user2.profile.save()


class LoginRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_many_failures_trigger_lock_message(self):
        for _ in range(5):
            self.client.post('/accounts/login/', {'username': 'hacker', 'password': 'wrong'})

        resp = self.client.post('/accounts/login/', {'username': 'hacker', 'password': 'wrong'})
        self.assertContains(resp, 'Слишком много неудачных попыток')

    def test_successful_login_clears_failures(self):
        User.objects.create_user(username='alice', password='secret')
        self.client.post('/accounts/login/', {'username': 'alice', 'password': 'bad'})

        resp = self.client.post('/accounts/login/', {'username': 'alice', 'password': 'secret'})
        self.assertRedirects(resp, '/dashboard/', fetch_redirect_response=False)

    def test_admin_login_rate_limited(self):
        # У входа в админку тот же лимит по IP, что и у /accounts/login/.
        for _ in range(5):
            self.client.post('/admin/login/', {'username': 'bob', 'password': 'wrong'})

        resp = self.client.post('/admin/login/', {'username': 'bob', 'password': 'wrong'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Слишком много неудачных попыток')

    def test_client_ip_trusts_x_real_ip_not_xff(self):
        class Req:
            META = {
                'HTTP_X_FORWARDED_FOR': '1.2.3.4',   # подделка клиентом
                'HTTP_X_REAL_IP': '5.6.7.8',         # ставит nginx $remote_addr
                'REMOTE_ADDR': '127.0.0.1',
            }
        self.assertEqual(_client_ip(Req()), '5.6.7.8')

    def test_client_ip_falls_back_to_remote_addr(self):
        class Req:
            META = {'REMOTE_ADDR': '192.168.1.10'}
        self.assertEqual(_client_ip(Req()), '192.168.1.10')
