from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from io import BytesIO
from openpyxl import load_workbook

from devices.models import Device
from .models import Trip


class TripViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tech', password='p')
        self.device = Device.objects.create(hostname='123')

    def test_list_requires_login(self):
        self.assertEqual(self.client.get(reverse('trips_list')).status_code, 302)

    def test_create_requires_login(self):
        self.assertEqual(self.client.post(reverse('trip_create'), {}).status_code, 302)

    def test_create_trip(self):
        self.client.force_login(self.user)
        self.client.post(reverse('trip_create'), {
            'date': '2026-09-06',
            'description': 'Замена термобумаги',
            'device_ids': [str(self.device.id)],
        })
        trip = Trip.objects.get()
        self.assertEqual(trip.description, 'Замена термобумаги')
        self.assertIn(self.device, trip.devices.all())

    def test_delete_trip(self):
        trip = Trip.objects.create(date='2026-09-06', description='x')
        self.client.force_login(self.user)
        resp = self.client.post(reverse('trip_delete', args=[trip.pk]))
        self.assertRedirects(resp, reverse('trips_list'), fetch_redirect_response=False)
        self.assertFalse(Trip.objects.filter(pk=trip.pk).exists())

    def test_delete_missing_trip_returns_404(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse('trip_delete', args=[99999]))
        self.assertEqual(resp.status_code, 404)

    def test_export_xlsx(self):
        Trip.objects.create(date='2026-09-06', description='Поездка')
        self.client.force_login(self.user)
        resp = self.client.get(reverse('export_trips'))
        self.assertEqual(resp.status_code, 200)
        wb = load_workbook(BytesIO(resp.content))
        self.assertIn('Поездка', wb.active['B2'].value)
