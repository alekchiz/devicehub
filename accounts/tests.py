from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

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
