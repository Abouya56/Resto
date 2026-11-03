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


class FloorPlanTests(TestCase):
    def setUp(self):
        from decimal import Decimal

        from django.test import Client

        from apps.menus.models import Category, Product

        self.resto = Restaurant.objects.create(name="Salle", address="x", city="Y")
        self.manager = User.objects.create_user(
            email="salle@test.local", password="pass12345", first_name="S", last_name="M", role=Role.MANAGER
        )
        Employee.objects.create(user=self.manager, restaurant=self.resto, role=Role.MANAGER)
        category = Category.objects.create(restaurant=self.resto, name="Plats")
        self.product = Product.objects.create(
            restaurant=self.resto, category=category, name="Riz", price=Decimal("2000")
        )
        self.t10 = DiningTable.objects.create(restaurant=self.resto, number="10", capacity=6)
        self.t2 = DiningTable.objects.create(restaurant=self.resto, number="2", capacity=4)
        self.web = Client()
        self.web.force_login(self.manager)
        session = self.web.session
        session["current_restaurant_id"] = self.resto.pk
        session.save()

    def _order_at(self, table):
        from apps.orders.models import Cart, OrderType
        from apps.orders.services import add_to_cart, checkout_cart

        cart = Cart.objects.create(restaurant=self.resto, order_type=OrderType.DINE_IN, table=table, session_key="s")
        add_to_cart(cart, self.product)
        return checkout_cart(cart, contact={"first_name": "A"})

    def test_floor_plan_shows_real_state_sorted_naturally(self):
        from apps.orders.models import OrderStatus
        from apps.orders.services import transition_order

        order = self._order_at(self.t2)
        page = self.web.get("/gerant/tables/")
        tables = page.context["tables"]
        self.assertEqual([t.number for t in tables], ["2", "10"])
        self.assertEqual(tables[0].state, "pending")
        self.assertEqual(tables[1].state, "free")
        self.assertEqual(page.context["summary"], {"tables": 2, "seats": 10, "busy": 1, "free": 1, "to_accept": 1})
        self.assertContains(page, f"N° {order.short_number}")
        transition_order(order, OrderStatus.ACCEPTED)
        page = self.web.get("/gerant/tables/")
        self.assertEqual(page.context["tables"][0].state, "busy")
        self.assertContains(page, "Occupée")

    def test_print_all_qr_codes(self):
        DiningTable.objects.create(restaurant=self.resto, number="Terrasse", is_active=False)
        page = self.web.get("/gerant/tables/qr/imprimer/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual([t.number for t in page.context["tables"]], ["2", "10"])  # tables retirées exclues
        self.assertContains(page, "Scannez pour voir la carte", count=2)
        self.assertTrue(QRCode.objects.filter(table=self.t10).exists())

    def test_table_form_no_longer_asks_for_status(self):
        page = self.web.get("/gerant/tables/nouvelle/")
        self.assertNotContains(page, 'name="status"')
        self.assertContains(page, "Nombre de places")
        response = self.web.post("/gerant/tables/nouvelle/", {"number": "5", "capacity": "2", "is_active": "on"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(QRCode.objects.filter(table__number="5", table__restaurant=self.resto).exists())

    def test_qr_page_renders_printable_card(self):
        page = self.web.get(f"/gerant/tables/{self.t2.pk}/qr/")
        self.assertContains(page, "qr-card")
        self.assertContains(page, "Créer un nouveau QR code")


class QrPhoneTests(TestCase):
    """Le QR doit pointer vers une adresse qu'un téléphone peut atteindre, et se corriger si elle change."""

    def setUp(self):
        from django.test import Client

        self.resto = Restaurant.objects.create(name="Phone", address="x", city="Y")
        self.manager = User.objects.create_user(
            email="phone@test.local", password="pass12345", first_name="P", last_name="M", role=Role.MANAGER
        )
        Employee.objects.create(user=self.manager, restaurant=self.resto, role=Role.MANAGER)
        self.table = DiningTable.objects.create(restaurant=self.resto, number="4")
        self.web = Client()
        self.web.force_login(self.manager)
        session = self.web.session
        session["current_restaurant_id"] = self.resto.pk
        session.save()

    def test_qr_follows_site_address_and_keeps_its_token(self):
        from django.test import override_settings

        with override_settings(SITE_URL="http://127.0.0.1:8000", ALLOWED_HOSTS=["*"]):
            qr = ensure_qrcode(self.table)
            token = str(qr.token)
            self.assertTrue(qr.public_url.startswith("http://127.0.0.1:8000/"))
            self.assertContains(
                self.web.get("/gerant/tables/", HTTP_HOST="127.0.0.1:8000"), "ne marcheront pas depuis un téléphone"
            )
            self.assertContains(
                self.web.get(f"/gerant/tables/{self.table.pk}/qr/", HTTP_HOST="127.0.0.1:8000"), "ne marcheront pas"
            )
        with override_settings(SITE_URL="http://192.168.11.120:8001"):
            qr = ensure_qrcode(self.table)
            self.assertTrue(qr.public_url.startswith("http://192.168.11.120:8001/"))
            self.assertEqual(str(qr.token), token)  # un QR déjà imprimé reste valable
            self.assertFalse(qr.is_stale)
            self.assertNotContains(self.web.get("/gerant/tables/"), "ne marcheront pas depuis un téléphone")

    def test_qr_uses_the_address_the_manager_opened_when_site_url_is_local(self):
        """Gérant connecté par l'adresse du PC sur le Wi-Fi : le QR contient cette adresse, pas 127.0.0.1."""
        from django.test import override_settings

        with override_settings(SITE_URL="http://127.0.0.1:8000", ALLOWED_HOSTS=["*"]):
            page = self.web.get("/gerant/tables/", HTTP_HOST="192.168.11.120:8001")
            self.assertNotContains(page, "ne marcheront pas depuis un téléphone")
            self.assertTrue(
                self.table.qrcode.__class__.objects.get(table=self.table).public_url.startswith(
                    "http://192.168.11.120:8001/"
                )
            )

    def test_scanning_the_qr_opens_the_menu_for_that_table(self):
        from django.test import Client, override_settings

        with override_settings(SITE_URL="http://192.168.11.120:8001", ALLOWED_HOSTS=["*"]):  # comme en développement
            qr = ensure_qrcode(self.table)
            path = qr.public_url.replace("http://192.168.11.120:8001", "")
            phone = Client(HTTP_HOST="192.168.11.120:8001")  # le téléphone arrive avec l'adresse du PC
            page = phone.get(path)
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, "Phone")
            wrong = phone.get(path.split("?")[0] + "?token=mauvais")
            self.assertNotEqual(wrong.status_code, 500)

    def test_refresh_command(self):
        from io import StringIO

        from django.core.management import call_command
        from django.test import override_settings

        out = StringIO()
        with override_settings(SITE_URL="http://192.168.1.50:8001"):
            call_command("refresh_qr_codes", stdout=out)
        self.assertIn("192.168.1.50:8001", out.getvalue())
        self.assertIn("1 QR code(s) à jour", out.getvalue())
