import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.core.files.uploadedfile import SimpleUploadedFile

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
        resp = self.client.get(reverse('device_history'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/devices/deviceevent/', resp.url)


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
        resp = self.client.get(reverse('clients_list'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/devices/client/', resp.url)

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
        self.device = Device.objects.create(hostname='123', alco='✅', tonometer='✅')

    def test_indicators(self):
        self.assertTrue(self.device.alco_ok)
        self.assertTrue(self.device.tono_ok)

        self.device.alco = 'ошибка'
        self.device.save()
        self.device.refresh_from_db()
        self.assertFalse(self.device.alco_ok)
        self.assertTrue(self.device.tono_ok)

    def test_tonometer_bad(self):
        self.device.tonometer = '❌'
        self.device.save()
        self.device.refresh_from_db()
        self.assertFalse(self.device.tono_ok)

    def test_dashboard_shows_med_indicators(self):
        Device.objects.all().update(alco='✅', tonometer='✅')
        self.client.force_login(_technician())
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'med-indicators')
        self.assertContains(resp, 'mi ok')
        self.assertNotContains(resp, 'bi-thermometer-half')


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
        resp = self.client.get(reverse('analytics'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/devices/device/analytics/', resp.url)

    def test_analytics_page_month_period(self):
        self.client.force_login(_technician())
        resp = self.client.get(reverse('analytics') + '?period=month')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/devices/device/analytics/', resp.url)


class MoveTemperatureMigrationTests(TransactionTestCase):
    """Проверка data-миграции 0011: старая CPU-температура уходит в cpu_temperature,
    а поле temperature очищается (чтобы не срабатывал индикатор термометра)."""
    migrate_from = [('devices', '0010_device_cpu_temperature')]
    migrate_to = [('devices', '0011_move_temperature_to_cpu')]

    def test_moves_temperature_to_cpu(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        OldDevice = old_apps.get_model('devices', 'Device')
        OldDevice.objects.create(hostname='321', temperature='27.8°C')

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)

        new_apps = executor.loader.project_state(self.migrate_to).apps
        NewDevice = new_apps.get_model('devices', 'Device')
        d = NewDevice.objects.get(hostname='321')
        self.assertEqual(d.cpu_temperature, '27.8°C')
        self.assertEqual(d.temperature, '')


class ImportExamsTests(TestCase):
    def setUp(self):
        self.device = Device.objects.create(hostname='123', sn='SN-0001')

    def _xlsx(self):
        import io
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(['SN клиента', 'расположение', 'количество осмотров'])
        ws.append(['SN-0001', 'Автопарк №3', 512])
        ws.append(['ZZZ-99', 'Улица', 10])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return SimpleUploadedFile('results.xlsx', buf.read())

    def test_import_requires_admin(self):
        self.client.force_login(_technician())
        resp = self.client.post(reverse('import_exams'), {'file': self._xlsx()})
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

    def test_import_updates_device(self):
        self.client.force_login(_admin())
        resp = self.client.post(reverse('import_exams'), {'file': self._xlsx()})
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/devices/device/import/', resp.url)

    def test_dashboard_shows_exam_count(self):
        from devices.models import DailyExam
        self.client.force_login(_technician())
        DailyExam.objects.create(
            device=Device.objects.get(hostname='123'),
            date=timezone.localdate(),
            exams=512,
        )
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'всего 512')
        self.assertContains(resp, 'за день 512')

    def test_dashboard_shows_zero_day_when_no_data(self):
        self.client.force_login(_technician())
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'за день 0')

    def test_dashboard_shows_today_exam_aggregates(self):
        from devices.models import DailyExam
        self.client.force_login(_technician())
        today = timezone.localdate()
        d1 = Device.objects.get(hostname='123')
        d2 = Device.objects.create(hostname='456')
        DailyExam.objects.create(device=d1, date=today, exams=10, cancelled=2)
        DailyExam.objects.create(device=d2, date=today, exams=5, cancelled=1)
        # Вчерашний снимок не должен попадать в «сегодня».
        DailyExam.objects.create(
            device=d1, date=today - timedelta(days=1), exams=999, cancelled=999
        )
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'Осмотров сегодня')
        self.assertContains(resp, 'Отменено сегодня')
        self.assertContains(resp, 'id="examsToday">15')      # 10 + 5 осмотров
        self.assertContains(resp, 'id="cancelledToday">3')   # 2 + 1 отменено
        self.assertNotContains(resp, 'id="paksToday"')


class DashboardNonstandardTests(TestCase):
    def test_nonstandard_device_is_marked(self):
        Device.objects.create(hostname='PC-FIELD-1', is_online=True)
        self.client.force_login(_technician())
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'PC-FIELD-1')
        self.assertContains(resp, 'nonstandard')
        self.assertContains(resp, 'Новый')

    def test_migrated_password_badge_on_card(self):
        Device.objects.create(hostname='666', is_online=True, password_migrated=True)
        self.client.force_login(_technician())
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'title="Пароль обновлён"')


class AdminPagesTests(TestCase):
    def setUp(self):
        self.device = Device.objects.create(hostname='123', sn='SN-0001')

    def _staff(self):
        return User.objects.create_user(
            'staff', password='pass', is_staff=True, is_superuser=True
        )

    def test_analytics_page_in_admin(self):
        self.client.force_login(self._staff())
        resp = self.client.get('/admin/devices/device/analytics/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Аптайм')
        self.assertContains(resp, '123')

    def test_analytics_requires_staff(self):
        self.client.force_login(_technician())
        resp = self.client.get('/admin/devices/device/analytics/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/login/', resp.url)

    def test_import_updates_device_in_admin(self):
        self.client.force_login(self._staff())
        resp = self.client.post(
            '/admin/devices/device/import/',
            {'file': SimpleUploadedFile('r.xlsx', self._xlsx_bytes())},
        )
        self.assertEqual(resp.status_code, 200)
        self.device.refresh_from_db()
        self.assertEqual(self.device.exam_count, 512)
        self.assertEqual(self.device.location.name, 'Автопарк №3')
        self.assertContains(resp, 'Киосков найдено: 1')
        self.assertContains(resp, 'Обновлено: 1')

    def _xlsx_bytes(self):
        import io
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(['SN клиента', 'расположение', 'количество осмотров'])
        ws.append(['SN-0001', 'Автопарк №3', 512])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()


class ExamIngestTests(TestCase):
    def setUp(self):
        self.device = Device.objects.create(hostname='123')

    def test_extract_day_date(self):
        from devices.exam_ingest import extract_day_date
        self.assertEqual(extract_day_date('pak/day/2026-09-05'), '2026-09-05')
        self.assertEqual(extract_day_date('client/day/2026-09-05'), '2026-09-05')
        self.assertIsNone(extract_day_date('client/status'))

    def test_ingest_updates_existing_device(self):
        from devices.exam_ingest import ingest_day_snapshot
        payload = {
            'date': '2026-09-05',
            'items': [{
                'sn': '123',
                'exams': 12,
                'cancelled': 1,
                'client': 'РТК - ДВ',
                'orgunit': 'с. Хороль, ул. Ленинская, 50 б',
                'last_exam': '2026-09-05T13:04:00+03:00',
            }],
        }
        count = ingest_day_snapshot(payload, 'pak/day/2026-09-05')
        self.assertEqual(count, 1)
        self.device.refresh_from_db()
        self.assertIsNone(self.device.exam_count)
        self.assertIsNotNone(self.device.client)
        self.assertEqual(self.device.client.name, 'РТК - ДВ')
        self.assertEqual(self.device.location.name, 'с. Хороль, ул. Ленинская, 50 б')
        daily = self.device.daily_exams.get()
        self.assertEqual(daily.exams, 12)
        self.assertEqual(daily.cancelled, 1)

    def test_ingest_creates_unknown_device(self):
        from devices.exam_ingest import ingest_day_snapshot
        payload = {'date': '2026-09-05', 'items': [{'sn': '99999', 'exams': 7}]}
        count = ingest_day_snapshot(payload)
        self.assertEqual(count, 1)
        dev = Device.objects.get(hostname='99999')
        self.assertIsNone(dev.exam_count)
        self.assertEqual(dev.daily_exams.get().exams, 7)

    def test_ingest_ignores_bad_payload(self):
        from devices.exam_ingest import ingest_day_snapshot
        self.assertEqual(ingest_day_snapshot({}), 0)
        self.assertEqual(ingest_day_snapshot({'date': 'not-a-date', 'items': []}), 0)
        self.assertEqual(ingest_day_snapshot(None), 0)


@override_settings(DEVICE_SSH_PASSWORD='global-pass', DEVICE_SSH_PASSWORDS=['backup-pass'])
class SshHelperTests(TestCase):
    def setUp(self):
        self.device = Device.objects.create(hostname='900', vpn_ip='10.0.0.9')

    def _auth_fail(self, pwd):
        return SimpleNamespace(returncode=5, stdout='', stderr='Permission denied (publickey,password).')

    @patch('devices.views.subprocess.run')
    def test_uses_device_password_first(self, m):
        self.device.ssh_password = 'device-pass'
        self.device.save()

        def fake(args, capture_output=True, text=True, timeout=15):
            pwd = args[2]
            if pwd == 'device-pass':
                return SimpleNamespace(returncode=0, stdout='ok', stderr='')
            return self._auth_fail(pwd)

        m.side_effect = fake
        from devices.views import ssh_execute
        res = ssh_execute(self.device, 'uptime')
        self.assertEqual(res.returncode, 0)
        self.assertEqual(m.call_count, 1)

    @patch('devices.views.subprocess.run')
    def test_falls_back_to_global_password(self, m):
        self.device.ssh_password = 'wrong-pass'
        self.device.save()

        def fake(args, capture_output=True, text=True, timeout=15):
            pwd = args[2]
            if pwd == 'global-pass':
                return SimpleNamespace(returncode=0, stdout='ok', stderr='')
            return self._auth_fail(pwd)

        m.side_effect = fake
        from devices.views import ssh_execute
        res = ssh_execute(self.device, 'uptime')
        self.assertEqual(res.returncode, 0)
        self.assertEqual(m.call_count, 2)  # устройство → глобальный → успех

    @override_settings(DEVICE_SSH_PASSWORD='login-pass',
                       DEVICE_SSH_SUDO_PASSWORD='sudo-pass')
    @patch('devices.views.subprocess.run')
    def test_sudo_uses_separate_sudo_password(self, m):
        """sudo-команды используют sudo-пароль, а вход — отдельный пароль."""
        self.device.ssh_password = ''
        self.device.save()

        def fake(args, capture_output=True, text=True, timeout=10):
            login_pwd = args[2]           # sshpass -p <пароль входа>
            remote = args[-1]             # удалённая команда
            self.assertEqual(login_pwd, 'login-pass')
            self.assertIn('sudo-pass', remote)  # в sudo передаётся свой пароль
            return SimpleNamespace(returncode=0, stdout='', stderr='')

        m.side_effect = fake
        from devices.views import ssh_reboot
        res = ssh_reboot(self.device)
        self.assertEqual(res.returncode, 0)

    def test_upload_requires_admin(self):
        self.client.force_login(_technician())
        resp = self.client.post(reverse('device_upload', args=[self.device.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

    @patch('devices.views.subprocess.run')
    def test_change_password_uses_working_password_and_sets_new(self, m):
        self.device.ssh_password = 'old-device-pass'
        self.device.save()

        def fake(args, capture_output=True, text=True, timeout=20):
            pwd = args[2]
            remote = args[-1]
            if pwd == 'old-device-pass':
                self.assertIn('terminal:Pochta@medQaZ', remote)
                return SimpleNamespace(returncode=0, stdout='', stderr='')
            return self._auth_fail(pwd)

        m.side_effect = fake
        from devices.views import ssh_change_password
        ok, msg = ssh_change_password(self.device, 'Pochta@medQaZ')
        self.assertTrue(ok)
        self.assertEqual(m.call_count, 1)  # рабочий пароль — с первого раза

    @patch('devices.views.subprocess.run')
    def test_change_password_falls_back_when_first_wrong(self, m):
        self.device.ssh_password = ''
        self.device.save()

        def fake(args, capture_output=True, text=True, timeout=20):
            pwd = args[2]
            if pwd == 'backup-pass':
                return SimpleNamespace(returncode=0, stdout='', stderr='')
            return self._auth_fail(pwd)

        m.side_effect = fake
        from devices.views import ssh_change_password
        ok, msg = ssh_change_password(self.device, 'Pochta@medQaZ')
        self.assertTrue(ok)
        self.assertEqual(m.call_count, 2)  # глобальный после неудачных

    @override_settings(
        DEVICE_SSH_PUBLIC_KEYS=['ssh-ed25519 AAAAFakeKey server@host',
                                'ssh-ed25519 AAAAMacKey user@mac'])
    @patch('devices.views.subprocess.run')
    def test_change_password_installs_authorized_keys(self, m):
        self.device.ssh_password = 'dev-pass'
        self.device.save()

        def fake(args, capture_output=True, text=True, timeout=20):
            pwd = args[2]
            remote = args[-1]
            if pwd == 'dev-pass':
                self.assertIn('chpasswd', remote)
                self.assertIn('AAAFakeKey', remote)   # ключ сервера
                self.assertIn('AAAMacKey', remote)    # личный ключ Мака
                self.assertIn('authorized_keys', remote)
                return SimpleNamespace(returncode=0, stdout='', stderr='')
            return self._auth_fail(pwd)

        m.side_effect = fake
        from devices.views import ssh_change_password
        ok, msg = ssh_change_password(self.device, 'NewPass123')
        self.assertTrue(ok)


@override_settings(DEVICE_SSH_PASSWORD='Pochta@medQaZ',
                   DEVICE_SSH_PASSWORDS=['Pochta@medQaZ', 'MC$Termina1'])
class ProbeSshPasswordsCommandTests(TestCase):
    @patch('devices.management.commands.probe_ssh_passwords.subprocess.run')
    def test_probe_finds_and_saves_password(self, m):
        from django.core.management import call_command
        device = Device.objects.create(hostname='111', vpn_ip='10.0.0.1')

        def fake(args, capture_output=True, text=True, timeout=8):
            pwd = args[2]
            if pwd == 'MC$Termina1':
                return SimpleNamespace(returncode=0, stdout='111\n', stderr='')
            return SimpleNamespace(returncode=5, stdout='', stderr='Permission denied.')

        m.side_effect = fake
        call_command('probe_ssh_passwords', save=True)

        device.refresh_from_db()
        self.assertEqual(device.ssh_password, 'MC$Termina1')

    @patch('devices.management.commands.probe_ssh_passwords.subprocess.run')
    def test_probe_reports_unreachable(self, m):
        from django.core.management import call_command
        Device.objects.create(hostname='222', vpn_ip='10.0.0.2')
        m.side_effect = lambda args, capture_output=True, text=True, timeout=8: (
            SimpleNamespace(returncode=5, stdout='', stderr='Permission denied.')
        )
        call_command('probe_ssh_passwords')


class MigrateSshPasswordsCommandTests(TestCase):
    @override_settings(DEVICE_SSH_PASSWORD='Pochta@medQaZ')
    @patch('devices.views.subprocess.run')
    def test_migrates_and_marks_device(self, m):
        from django.core.management import call_command
        device = Device.objects.create(hostname='900', vpn_ip='10.0.0.9')

        m.side_effect = lambda args, capture_output=True, text=True, timeout=10: (
            SimpleNamespace(returncode=0, stdout='', stderr='')
            if args[2] == 'Pochta@medQaZ'
            else SimpleNamespace(returncode=5, stdout='', stderr='Permission denied.')
        )

        call_command('migrate_ssh_passwords', hostname='900')
        device.refresh_from_db()
        self.assertTrue(device.password_migrated)
        self.assertEqual(device.ssh_password, 'Pochta@medQaZ')
