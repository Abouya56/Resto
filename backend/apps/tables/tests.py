from django.test import TestCase
from rest_framework.test import APIClient

from apps.restaurants.models import Employee, Restaurant
from apps.tables.models import DiningTable, QRCode
from apps.tables.services import ensure_qrcode
from apps.users.models import User
from apps.users.roles import Role


class TableQRTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.resto = Restaurant.objects.create(name="QR Resto", address="x", city="Y")
        self.manager = User.objects.create_user(
            email="qr@test.local", password="pass12345", first_name="Q", last_name="R", role=Role.MANAGER
        )
        Employee.objects.create(user=self.manager, restaurant=self.resto, role=Role.MANAGER)

    def test_create_table_and_qr(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(
            "/api/tables/",
            {"number": "12", "capacity": 4},
            format="json",
            HTTP_X_RESTAURANT_ID=str(self.resto.id),
        )
        self.assertEqual(response.status_code, 201)
        table = DiningTable.objects.get(number="12", restaurant=self.resto)
        self.assertTrue(QRCode.objects.filter(table=table).exists())
        qr = ensure_qrcode(table)
        self.assertIn(self.resto.slug, qr.public_url)
        self.assertIn(str(table.pk), qr.public_url)
