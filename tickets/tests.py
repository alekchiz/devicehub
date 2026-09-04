from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from devices.models import Device
from .models import Ticket


class TicketExportTests(TestCase):
    def setUp(self):
        self.device = Device.objects.create(hostname='123')
        self.tech1 = User.objects.create_user(username='t1', password='p')
        self.tech2 = User.objects.create_user(username='t2', password='p')
        self.admin = User.objects.create_user(username='admin', password='p')
        self.admin.profile.role = 'admin'
        self.admin.profile.save()

    def _ticket(self, created_by, assigned_to=None):
        return Ticket.objects.create(
            device=self.device,
            problem='Проблема',
            contact_name='Иван',
            contact_phone='+70000000000',
            created_by=created_by,
            assigned_to=assigned_to,
        )

    def _excel_ids(self, username):
        self.client.force_login(User.objects.get(username=username))
        resp = self.client.get(reverse('export_tickets'))
        self.assertEqual(resp.status_code, 200)
        wb = load_workbook(BytesIO(resp.content))
        return [r[0] for r in wb.active.iter_rows(min_row=2, values_only=True) if r[0]]

    def test_technician_sees_own_created_and_assigned(self):
        own = self._ticket(self.tech1)
        foreign = self._ticket(self.tech2)
        assigned = self._ticket(self.tech1, assigned_to=self.tech2)

        ids = self._excel_ids('t1')
        self.assertIn(own.id, ids)
        self.assertIn(assigned.id, ids)   # автором предложенного, но назначен на tech2
        self.assertNotIn(foreign.id, ids)

    def test_technician_assigned_sees_ticket(self):
        own = self._ticket(self.tech1, assigned_to=self.tech2)
        ids = self._excel_ids('t2')
        self.assertIn(own.id, ids)

    def test_admin_sees_all(self):
        a = self._ticket(self.tech1)
        b = self._ticket(self.tech2)
        ids = self._excel_ids('admin')
        self.assertIn(a.id, ids)
        self.assertIn(b.id, ids)

    def test_export_requires_login(self):
        resp = self.client.get(reverse('export_tickets'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)