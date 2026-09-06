from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from io import BytesIO
from openpyxl import load_workbook

from devices.models import Device
from .models import Shipment, ShipmentItem


class ShipmentViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tech', password='p')
        self.device = Device.objects.create(hostname='123')

    def test_list_requires_login(self):
        self.assertEqual(self.client.get(reverse('shipments_list')).status_code, 302)

    def test_create_requires_login(self):
        self.assertEqual(self.client.post(reverse('shipment_create'), {}).status_code, 302)

    def test_create_shipment_with_items(self):
        self.client.force_login(self.user)
        self.client.post(reverse('shipment_create'), {
            'receiver_name': 'Иван',
            'receiver_contact': '+70000000000',
            'transport_company': 'СДЭК',
            'tracking_number': '999',
            'device_id': self.device.id,
            'equipment_type[]': ['thermal_paper', 'batteries'],
            'quantity[]': ['10', '4'],
            'item_description[]': ['', ''],
            'item_name[]': ['', ''],
        })
        shipment = Shipment.objects.get()
        self.assertEqual(shipment.device, self.device)
        self.assertEqual(shipment.items.count(), 2)

    def test_change_status_sets_dates(self):
        shipment = Shipment.objects.create(
            receiver_name='Иван',
            receiver_contact='+7',
            transport_company='Почта',
        )
        self.client.force_login(self.user)
        self.client.post(reverse('shipment_change_status', args=[shipment.pk]), {
            'status': 'sent',
            'sent_date': '2026-09-01',
        })
        shipment.refresh_from_db()
        self.assertEqual(shipment.status, 'sent')
        self.assertEqual(shipment.sent_date.isoformat(), '2026-09-01')

    def test_export_xlsx(self):
        Shipment.objects.create(
            receiver_name='Иван',
            receiver_contact='+7',
            transport_company='СДЭК',
            device=self.device,
        )
        self.client.force_login(self.user)
        resp = self.client.get(reverse('export_shipments'))
        self.assertEqual(resp.status_code, 200)
        wb = load_workbook(BytesIO(resp.content))
        self.assertIn('СДЭК', str(wb.active['E2'].value))
