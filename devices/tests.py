import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from .models import Device, Repair, Client, DeviceEvent


class DeviceModelTests(TestCase):
    def setUp(self):
        self.device = Device.objects.create(hostname='123')

    def test_offline_duration_none_when_online(self):
        self.device.is_online = True
        self.device.save()
        self.assertIsNone(self.device.offline_duration)

    def test_offline_duration_minutes(self):
        self.device.is_online = False
        self.device.offline_since = timezone.now() - timedelta(minutes=5)
        self.device.save()
        self.assertEqual(self.device.offline_duration, '5м')

    def test_offline_duration_hours_days(self):
        self.device.is_online = False
        self.device.offline_since = timezone.now() - timedelta(days=2, hours=3, minutes=10)
        self.device.save()
        self.assertEqual(self.device.offline_duration, '2д 3ч 10м')


class RepairModelTests(TestCase):
    def setUp(self):
        self.device = Device.objects.create(hostname='123')

    def test_created_sets_device_in_repair(self):
        Repair.objects.create(device=self.device, problem='Профилактика')
        self.device.refresh_from_db()
        self.assertTrue(self.device.in_repair)
        self.assertIsNone(Repair.objects.get(device=self.device).in_progress_at)

    def test_in_progress_sets_flag_and_date(self):
        repair = Repair.objects.create(device=self.device, problem='Не грузится')
        repair.status = 'in_progress'
        repair.save()

        self.device.refresh_from_db()
        self.assertTrue(self.device.in_repair)
        self.assertIsNotNone(repair.in_progress_at)
        self.assertIsNone(repair.ready_at)

    def test_ready_clears_flag_and_sets_date(self):
        repair = Repair.objects.create(device=self.device, problem='Не грузится')
        repair.status = 'in_progress'
        repair.save()

        repair.status = 'ready'
        repair.save()

        self.device.refresh_from_db()
        self.assertFalse(self.device.in_repair)
        self.assertIsNotNone(repair.ready_at)
        self.assertIsNotNone(repair.in_progress_at)

    def test_repair_logs_audit_events(self):
        repair = Repair.objects.create(device=self.device, problem='Поломка')
        # создание ремонта -> одно событие "В ремонт"
        self.assertEqual(
            DeviceEvent.objects.filter(device=self.device, event='repair_in').count(), 1
        )
        # переход created -> in_progress не дублирует "В ремонт"
        repair.status = 'in_progress'
        repair.save()
        self.assertEqual(
            DeviceEvent.objects.filter(device=self.device, event='repair_in').count(), 1
        )
        # завершение -> "Из ремонта"
        repair.status = 'ready'
        repair.save()
        self.assertTrue(
            DeviceEvent.objects.filter(device=self.device, event='repair_out').exists()
        )

    def test_log_device_event_helper(self):
        from .models import log_device_event
        log_device_event(self.device, 'online', 'Связь восстановлена')
        self.assertTrue(
            DeviceEvent.objects.filter(device=self.device, event='online').exists()
        )


def _admin():
    user = User.objects.create_user(username='admin', password='pass')
    user.profile.role = 'admin'
    user.profile.save()
    return user


def _technician():
    return User.objects.create_user(username='tech', password='pass')


class DeviceViewsTests(TestCase):
    def setUp(self):
        Device.objects.create(hostname='123', vpn_ip='10.0.0.1')

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

    def test_dashboard_allows_authenticated_user(self):
        self.client.force_login(_technician())
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_bulk_action_admin_only(self):
        self.client.force_login(_technician())
        resp = self.client.post(reverse('bulk_action'), {'device_ids': ['1'], 'action': 'reboot'})
        # В Django 6.x непрошедший тест пользователь перенаправляется на логин,
        # главное — сама view не выполняется (SSH не вызывается).
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

    def test_export_devices_requires_login(self):
        resp = self.client.get(reverse('export_devices'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

    def test_export_devices_returns_xlsx(self):
        self.client.force_login(_technician())
        resp = self.client.get(reverse('export_devices'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])
        self.assertIn('.xlsx', resp['Content-Disposition'])

    def test_dashboard_components(self):
        self.client.force_login(_admin())
        resp = self.client.get(reverse('dashboard') + '?q=123')
        self.assertContains(resp, 'Киосков')
        self.assertContains(resp, 'Киоски')
        self.assertContains(resp, 'В ремонте')
        self.assertContains(resp, 'status-chip')
        self.assertContains(resp, 'Найдено')
        self.assertContains(resp, '123')

    def test_dashboard_ignores_page_param(self):
        self.client.force_login(_admin())
        resp = self.client.get(reverse('dashboard') + '?page=99')
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'page=2')

    def test_dashboard_renders_device_metrics(self):
        self.client.force_login(_technician())
        Device.objects.all().update(
            cpu_load=12.3, hdd_percent=95.0, memory_percent=50.0
        )
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'device-metrics')
        self.assertContains(resp, 'is-bad')   # диск 95% — красная полоса
        self.assertContains(resp, '12%')      # CPU floatformat
        self.assertContains(resp, 'page-head accent-')
        self.assertContains(resp, 'status-pill')
        self.assertContains(resp, 'device-detail')

    def test_status_feed_requires_login(self):
        resp = self.client.get(reverse('device_status_feed'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

    def test_status_feed_json(self):
        self.client.force_login(_technician())
        Device.objects.all().update(is_online=True)
        resp = self.client.get(reverse('device_status_feed'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['online'], 1)
        self.assertIn('devices', data)

    def test_status_feed_marks_offline(self):
        self.client.force_login(_technician())
        Device.objects.all().update(is_online=False, offline_since=timezone.now() - timedelta(minutes=3))
        data = self.client.get(reverse('device_status_feed')).json()
        self.assertEqual(data['page_status'], 'warn')
        dev = next(iter(data['devices'].values()))
        self.assertFalse(dev['online'])
        self.assertEqual(dev['offline_duration'], '3м')

    def test_default_all_on_one_page(self):
        self.client.force_login(_technician())
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Всего')
        self.assertNotContains(resp, 'Найдено')
        self.assertNotContains(resp, 'page=2')

    def test_default_lists_all_devices(self):
        self.client.force_login(_technician())
        for i in range(60):
            Device.objects.create(hostname=f'{3000+i}')
        resp = self.client.get(reverse('dashboard'))
        # 60 новых + 1 из setUp = 61 — все на одной странице, без пагинации.
        self.assertContains(resp, 'Всего: <b>61</b>')
        self.assertNotContains(resp, 'page=2')

    def test_search_shows_all_matching(self):
        self.client.force_login(_technician())
        for i in range(60):
            Device.objects.create(hostname=f'{200+i}')
        resp = self.client.get(reverse('dashboard') + '?q=2')
        self.assertContains(resp, 'Найдено: <b>61</b>')  # 60 новых + '123' из setUp
        self.assertNotContains(resp, 'page=2')

    def test_status_chip_filters(self):
        self.client.force_login(_technician())
        resp = self.client.get(reverse('dashboard') + '?status=online')
        self.assertContains(resp, 'status-chip')
        self.assertContains(resp, 'Всего')
        self.assertNotContains(resp, 'Найдено')

    def test_med_and_distribution_blocks(self):
        self.client.force_login(_technician())
        Device.objects.all().update(alco='✅', tonometer='✅', temperature='36.6', is_online=True)
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'Средства готовы')
        self.assertContains(resp, 'dist-bar')
        self.assertContains(resp, 'Распределение')
        self.assertContains(resp, 'Проблемные')

    def test_problems_filter(self):
        self.client.force_login(_technician())
        Device.objects.all().update(alco='✅', tonometer='✅', temperature='36.6', is_online=True)
        Device.objects.create(hostname='777', is_online=False)
        resp = self.client.get(reverse('dashboard') + '?problems=1')
        # '777' оффлайн -> в проблемных; '123' полностью готов -> нет
        self.assertContains(resp, '777')
        self.assertNotContains(resp, '>123<')

    def test_active_sort(self):
        self.client.force_login(_technician())
        # Смешанные данные: у одного нет last_mqtt_message (None).
        Device.objects.all().update(
            last_mqtt_message=None
        )
        Device.objects.create(
            hostname='999', is_online=True,
            last_mqtt_message=timezone.now(),
        )
        resp = self.client.get(reverse('dashboard') + '?sort=active')
        self.assertEqual(resp.status_code, 200)

    def test_reports_page_requires_login(self):
        resp = self.client.get(reverse('reports'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

    def test_reports_page_renders(self):
        self.client.force_login(_technician())
        resp = self.client.get(reverse('reports'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Отчёты')
        self.assertContains(resp, 'Мед.средства')

    def test_history_requires_login(self):
        resp = self.client.get(reverse('device_history'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

    def test_history_renders(self):
        self.client.force_login(_technician())
        device = Device.objects.get(hostname='123')
        DeviceEvent.objects.create(device=device, event='offline', message='Нет связи')
        resp = self.client.get(reverse('device_history'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'История киосков')
        self.assertContains(resp, 'Нет связи')
        self.assertContains(resp, 'ev-offline')

    def test_history_filters_by_hostname(self):
        self.client.force_login(_technician())
        device = Device.objects.get(hostname='123')
        other = Device.objects.create(hostname='777')
        DeviceEvent.objects.create(device=device, event='online')
        DeviceEvent.objects.create(device=other, event='offline')
        resp = self.client.get(reverse('device_history') + '?q=777')
        self.assertContains(resp, '777')
        self.assertNotContains(resp, '>123<')

    def test_history_filters_by_date(self):
        self.client.force_login(_technician())
        device = Device.objects.get(hostname='123')
        ev_new = DeviceEvent.objects.create(device=device, event='online', message='НОВОЕ')
        ev_old = DeviceEvent.objects.create(device=device, event='offline', message='СТАРОЕ')
        DeviceEvent.objects.filter(pk=ev_old.pk).update(
            created_at=timezone.now() - timedelta(days=3)
        )
        today = timezone.localdate().isoformat()
        resp = self.client.get(reverse('device_history') + f'?date_from={today}')
        self.assertContains(resp, 'НОВОЕ')
        self.assertNotContains(resp, 'СТАРОЕ')


    def test_repair_progress_renders_on_card(self):
        self.client.force_login(_technician())
        device = Device.objects.get(hostname='123')
        repair = Repair.objects.create(device=device, problem='Тест')
        repair.status = 'in_progress'
        repair.save()

        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'repair-progress')
        self.assertContains(resp, 'В ремонте')

    def test_dashboard_shows_client_chip(self):
        self.client.force_login(_technician())
        client = Client.objects.create(name='ООО Тест')
        Device.objects.all().update(client=client)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'client-chip')
        self.assertContains(resp, 'ООО Тест')

    def test_clients_page_requires_login(self):
        resp = self.client.get(reverse('clients_list'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

    def test_clients_page_renders(self):
        self.client.force_login(_technician())
        client = Client.objects.create(name='ООО Тест')
        Device.objects.all().update(client=client, is_online=True)
        resp = self.client.get(reverse('clients_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ООО Тест')
        self.assertContains(resp, '123')
        self.assertContains(resp, 'cd-dot online')

class NotificationTests(TestCase):
    def setUp(self):
        self.device = Device.objects.create(hostname='123')
        self.offline_sub = User.objects.create_user('off_user')
        self.offline_sub.profile.notify_device_offline = True
        self.offline_sub.profile.telegram_id = 111
        self.offline_sub.profile.save()

        self.plain = User.objects.create_user('plain')
        self.plain.profile.telegram_id = 222
        self.plain.profile.save()

        self.online_sub = User.objects.create_user('on_user')
        self.online_sub.profile.notify_device_online = True
        self.online_sub.profile.telegram_id = 333
        self.online_sub.profile.save()

    def _sent_chat_ids(self, mock_urlopen):
        return [
            json.loads(call[0][0].data)['chat_id']
            for call in mock_urlopen.call_args_list
        ]

    @patch('devices.notifications.urllib.request.urlopen')
    def test_offline_sent_only_to_offline_subscribers(self, mock_urlopen):
        from devices.notifications import notify_device_status
        notify_device_status(self.device, 'offline', 'Нет связи')
        self.assertEqual(self._sent_chat_ids(mock_urlopen), [111])

    @patch('devices.notifications.urllib.request.urlopen')
    def test_online_sent_only_to_online_subscribers(self, mock_urlopen):
        from devices.notifications import notify_device_status
        notify_device_status(self.device, 'online', 'Связь есть')
        self.assertEqual(self._sent_chat_ids(mock_urlopen), [333])

    @patch('devices.notifications.urllib.request.urlopen', return_value='ok')
    def test_send_telegram_returns_success(self, mock_urlopen):
        from devices.notifications import send_telegram
        self.assertTrue(send_telegram(123, 'тест'))

    @patch('devices.notifications.urllib.request.urlopen', side_effect=Exception('down'))
    def test_send_telegram_returns_failure(self, mock_urlopen):
        from devices.notifications import send_telegram
        self.assertFalse(send_telegram(123, 'тест'))

class DeviceMedIndicatorTests(TestCase):
    def setUp(self):
        self.device = Device.objects.create(hostname='123', alco='✅', tonometer='✅', temperature='36.6')

    def test_indicators(self):
        self.assertTrue(self.device.alco_ok)
        self.assertTrue(self.device.tono_ok)
        self.assertTrue(self.device.temp_ok)

        self.device.alco = 'ошибка'
        self.device.temperature = ''
        self.device.save()
        self.device.refresh_from_db()
        self.assertFalse(self.device.alco_ok)
        self.assertFalse(self.device.temp_ok)

    def test_dashboard_shows_med_indicators(self):
        Device.objects.all().update(alco='✅', tonometer='✅', temperature='36.6')
        self.client.force_login(_technician())
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'med-indicators')
        self.assertContains(resp, 'mi ok')


class VerificationTests(TestCase):
    def setUp(self):
        self.device = Device.objects.create(hostname='123')

    def _verified(self, days_left):
        from .models import Verification
        return Verification.objects.create(
            device=self.device,
            equipment_type='alco', equipment_name='AC-02',
            sent_date=timezone.localdate() - timedelta(days=30),
            status='verified',
            verification_date=timezone.localdate() - timedelta(days=30),
            valid_until=timezone.localdate() + timedelta(days=days_left),
        )

    def test_expiry_states(self):
        from .models import Verification
        self.assertEqual(self._verified(60).expiry_state, 'ok')
        self.assertEqual(self._verified(10).expiry_state, 'soon')
        self.assertEqual(self._verified(-1).expiry_state, 'expired')
        v = Verification.objects.get(pk=self._verified(60).pk)
        v.status = 'sent'
        v.save()
        self.assertEqual(v.expiry_state, 'none')

    def test_verify_sets_valid_until(self):
        from .models import Verification
        v = Verification.objects.create(
            device=self.device, equipment_type='alco', equipment_name='x',
            sent_date=timezone.localdate(),
        )
        self.client.force_login(_technician())
        resp = self.client.post(
            reverse('verification_verify', args=[v.pk]),
            {'verification_date': '2026-01-01', 'valid_until': '2027-01-01'},
        )
        self.assertEqual(resp.status_code, 302)
        v.refresh_from_db()
        self.assertEqual(v.status, 'verified')
        self.assertEqual(v.valid_until.isoformat(), '2027-01-01')
        self.assertEqual(v.reminded_for, 'none')

    def test_med_devices_export(self):
        self.client.force_login(_technician())
        resp = self.client.get(reverse('export_med_devices'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])

    @patch('devices.notifications.urllib.request.urlopen')
    def test_reminder_sent_once(self, mock_urlopen):
        from devices.notifications import run_verification_reminders
        sub = User.objects.create_user('medic')
        sub.profile.notify_verification_expiry = True
        sub.profile.telegram_id = 999
        sub.profile.save()
        self._verified(5)

        self.assertEqual(run_verification_reminders(), 1)
        calls = mock_urlopen.call_args_list
        self.assertEqual(len(calls), 1)
        body = json.loads(calls[0][0][0].data)
        self.assertEqual(body['chat_id'], 999)

        self.assertEqual(run_verification_reminders(), 0)  # повторно не шлём
        self.assertEqual(mock_urlopen.call_count, 1)


class UptimeTests(TestCase):
    def setUp(self):
        self.device = Device.objects.create(hostname='123')
        self.now = timezone.now()

    def _event(self, kind, timestamp):
        ev = DeviceEvent.objects.create(device=self.device, event=kind)
        DeviceEvent.objects.filter(pk=ev.pk).update(created_at=timestamp)
        return ev

    def test_no_events_is_zero(self):
        from devices.analytics import device_uptime
        start = self.now - timedelta(days=7)
        self.assertEqual(device_uptime(self.device, start, self.now), 0.0)

    def test_online_before_start_full_period(self):
        from devices.analytics import device_uptime
        start = self.now - timedelta(days=7)
        self._event('online', start)
        self.assertEqual(device_uptime(self.device, start, self.now), 1.0)

    def test_half_online_half_offline(self):
        from devices.analytics import device_uptime
        start = self.now - timedelta(days=7)
        half = start + timedelta(days=3.5)
        self._event('offline', start)
        self._event('online', half)
        result = device_uptime(self.device, start, self.now)
        self.assertAlmostEqual(result, 0.5, places=3)

    def test_state_before_period_used(self):
        from devices.analytics import device_uptime
        start = self.now - timedelta(days=7)
        # киоск был онлайн до периода, оффлайн только в середине периода
        self._event('online', start - timedelta(days=1))
        self._event('offline', start + timedelta(days=3.5))
        result = device_uptime(self.device, start, self.now)
        self.assertAlmostEqual(result, 0.5, places=3)

    def test_analytics_page_requires_login(self):
        resp = self.client.get(reverse('analytics'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

    def test_analytics_page_renders(self):
        self.client.force_login(_technician())
        self._event('online', self.now - timedelta(minutes=1))
        resp = self.client.get(reverse('analytics'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Доступность киосков')
        self.assertContains(resp, '123')
        self.assertContains(resp, 'Неделя')

    def test_analytics_page_month_period(self):
        self.client.force_login(_technician())
        resp = self.client.get(reverse('analytics') + '?period=month')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '30 дней')
