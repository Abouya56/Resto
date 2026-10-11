"""Tests de sécurité transverses : rôles, isolation entre restaurants, QR code, paiement espèces, KYC."""
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.finance.services import dashboard_metrics
from apps.inventory.models import StockItem
from apps.menus.models import Category, Product
from apps.orders.models import Order, OrderStatus, OrderType
from apps.orders.services import add_to_cart, checkout_cart, transition_order
from apps.payments.models import PaymentStatus
from apps.payments.providers import CashPaymentProvider
from apps.restaurants.forms import EmployeeForm
from apps.restaurants.models import Employee, Restaurant, RestaurantStatus
from apps.tables.models import DiningTable
from apps.tables.services import ensure_qrcode
from apps.users.models import User
from apps.users.roles import Role


def make_user(email, role=Role.CUSTOMER, **extra):
    return User.objects.create_user(
        email=email, password="pass12345", first_name="Test", last_name=role, role=role, **extra
    )


class BaseTenantCase(TestCase):
    def setUp(self):
        self.resto_a = Restaurant.objects.create(name="Alpha", address="1 rue A", city="Abidjan")
        self.resto_b = Restaurant.objects.create(name="Beta", address="2 rue B", city="Abidjan")
        self.manager_a = make_user("ma@test.local", Role.MANAGER)
        self.manager_b = make_user("mb@test.local", Role.MANAGER)
        self.cook_a = make_user("ca@test.local", Role.COOK)
        self.waiter_a = make_user("wa@test.local", Role.WAITER)
        self.driver_a = make_user("da@test.local", Role.DRIVER)
        Employee.objects.create(user=self.manager_a, restaurant=self.resto_a, role=Role.MANAGER)
        Employee.objects.create(user=self.manager_b, restaurant=self.resto_b, role=Role.MANAGER)
        Employee.objects.create(user=self.cook_a, restaurant=self.resto_a, role=Role.COOK)
        Employee.objects.create(user=self.waiter_a, restaurant=self.resto_a, role=Role.WAITER)
        Employee.objects.create(user=self.driver_a, restaurant=self.resto_a, role=Role.DRIVER)
        self.category = Category.objects.create(restaurant=self.resto_a, name="Plats")
        self.product = Product.objects.create(
            restaurant=self.resto_a, category=self.category, name="Riz", price=Decimal("2000")
        )
        self.table = DiningTable.objects.create(restaurant=self.resto_a, number="1")

    def login(self, user):
        client = Client()
        client.force_login(user)
        return client

    def new_order(self, order_type=OrderType.TAKEAWAY, table=None):
        from apps.orders.models import Cart

        cart = Cart.objects.create(restaurant=self.resto_a, order_type=order_type, table=table, session_key="s")
        add_to_cart(cart, self.product, 1)
        order = checkout_cart(
            cart,
            contact={
                "first_name": "Awa",
                "last_name": "K",
                "phone": "0700000000",
                "city": "Abidjan",
                "district": "Cocody",
            },
            address_text="Rue 1",
        )
        CashPaymentProvider().charge(order, method="cash_on_site")
        return order


class EmployeeIsolationTests(BaseTenantCase):
    def test_api_cannot_create_employee_in_other_restaurant(self):
        client = APIClient()
        client.force_authenticate(self.manager_a)
        newcomer = make_user("new@test.local")
        response = client.post(
            "/api/restaurants/employees/",
            {"user": newcomer.pk, "role": Role.COOK, "restaurant": self.resto_b.pk},
            format="json",
        )
        self.assertIn(response.status_code, (201, 400, 403))
        self.assertFalse(Employee.objects.filter(user=newcomer, restaurant=self.resto_b).exists())

    def test_form_does_not_overwrite_existing_account(self):
        victim = make_user("victim@test.local", Role.MANAGER)
        victim.first_name = "Original"
        victim.save()
        Employee.objects.create(user=victim, restaurant=self.resto_b, role=Role.MANAGER)
        form = EmployeeForm(
            {
                "email": "victim@test.local",
                "first_name": "Pirate",
                "last_name": "Pirate",
                "role": Role.COOK,
                "status": "active",
            },
            restaurant=self.resto_a,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        victim.refresh_from_db()
        self.assertEqual(victim.first_name, "Original")

    def test_form_rejects_duplicate_and_platform_admin(self):
        form = EmployeeForm(
            {"email": "ca@test.local", "first_name": "x", "last_name": "y", "role": Role.COOK, "status": "active"},
            restaurant=self.resto_a,
        )
        self.assertFalse(form.is_valid())
        admin = make_user("root@test.local", Role.PLATFORM_ADMIN)
        form = EmployeeForm(
            {"email": admin.email, "first_name": "x", "last_name": "y", "role": Role.COOK, "status": "active"},
            restaurant=self.resto_a,
        )
        self.assertFalse(form.is_valid())

    def test_form_edit_cannot_change_email(self):
        employee = Employee.objects.get(user=self.cook_a)
        form = EmployeeForm(
            {
                "email": "manager-b@evil.test",
                "first_name": "Test",
                "last_name": "cook",
                "role": Role.COOK,
                "status": "active",
            },
            instance=employee,
            restaurant=self.resto_a,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        employee.refresh_from_db()
        self.assertEqual(employee.user.email, "ca@test.local")


class RoleChecksTests(BaseTenantCase):
    def test_product_toggle_is_post_only_and_manager_only(self):
        url = reverse("menus:product_toggle", args=[self.product.pk])
        self.assertEqual(self.login(self.manager_a).get(url).status_code, 405)
        self.assertEqual(self.login(self.cook_a).post(url).status_code, 403)
        self.assertEqual(self.login(self.manager_b).post(url).status_code, 403)
        self.login(self.manager_a).post(url)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_available)

    def test_qr_regeneration_requires_post_and_manager(self):
        ensure_qrcode(self.table)
        url = reverse("tables:regenerate", args=[self.table.pk])
        self.assertEqual(self.login(self.manager_a).get(url).status_code, 405)
        self.assertEqual(self.login(self.waiter_a).post(url).status_code, 403)

    def test_stock_move_requires_post_and_manager(self):
        item = StockItem.objects.create(restaurant=self.resto_a, name="Farine", quantity=Decimal("5"))
        url = reverse("inventory:move", args=[item.pk])
        self.assertEqual(self.login(self.manager_a).get(url).status_code, 405)
        self.assertEqual(self.login(self.cook_a).post(url, {}).status_code, 403)

    def test_change_status_requires_matching_role(self):
        order = self.new_order()
        url = reverse("orders:change_status", args=[order.pk])
        self.assertEqual(self.login(self.driver_a).post(url, {"status": OrderStatus.ACCEPTED}).status_code, 403)
        self.assertEqual(self.login(self.waiter_a).post(url, {"status": OrderStatus.ACCEPTED}).status_code, 403)
        self.assertEqual(self.login(self.manager_b).post(url, {"status": OrderStatus.ACCEPTED}).status_code, 403)
        self.login(self.cook_a).post(url, {"status": OrderStatus.ACCEPTED})
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.ACCEPTED)

    def test_change_status_ignores_external_redirect(self):
        order = self.new_order()
        response = self.login(self.cook_a).post(
            reverse("orders:change_status", args=[order.pk]),
            {"status": OrderStatus.ACCEPTED, "next": "https://evil.example/phishing"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(response["Location"].startswith("https://evil.example"))


class TableTokenTests(BaseTenantCase):
    def test_table_page_requires_valid_qr_token(self):
        qr = ensure_qrcode(self.table)
        url = reverse("orders:table_menu", args=[self.resto_a.slug, self.table.pk])
        client = Client()
        self.assertEqual(client.get(url).status_code, 403)
        self.assertEqual(client.get(url, {"token": "faux"}).status_code, 403)
        self.assertEqual(client.get(url, {"token": qr.token}).status_code, 200)
        # le jeton est mémorisé pour la suite de la visite
        self.assertEqual(client.get(url).status_code, 200)

    def test_regenerated_qr_invalidates_old_link(self):
        qr = ensure_qrcode(self.table)
        old_token = qr.token
        qr.regenerate()
        url = reverse("orders:table_menu", args=[self.resto_a.slug, self.table.pk])
        self.assertEqual(Client().get(url, {"token": old_token}).status_code, 403)
        qr.refresh_from_db()
        self.assertEqual(Client().get(url, {"token": qr.token}).status_code, 200)


class CashPaymentTests(BaseTenantCase):
    def test_cash_payment_settled_when_order_completed(self):
        order = self.new_order()
        payment = order.payments.get()
        self.assertEqual(payment.status, PaymentStatus.PENDING)
        for status in (OrderStatus.ACCEPTED, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.PICKED_UP):
            transition_order(order, status)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.PAID)
        self.assertIsNotNone(payment.paid_at)

    def test_manual_mark_paid_by_waiter_only(self):
        order = self.new_order()
        url = reverse("orders:mark_paid", args=[order.pk])
        self.assertEqual(self.login(self.cook_a).post(url).status_code, 403)
        self.login(self.waiter_a).post(url)
        self.assertEqual(order.payments.get().status, PaymentStatus.PAID)

    def test_revenue_counts_cash_after_collection(self):
        order = self.new_order()
        before = dashboard_metrics(self.resto_a, "today")["revenue"]
        for status in (OrderStatus.ACCEPTED, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.PICKED_UP):
            transition_order(order, status)
        after = dashboard_metrics(self.resto_a, "today")["revenue"]
        self.assertEqual(Decimal(str(before)), Decimal("0"))
        self.assertEqual(Decimal(str(after)), order.total)

    def test_cancellation_reason_is_kept(self):
        order = self.new_order()
        transition_order(order, OrderStatus.CANCELLED, reason="Rupture de stock")
        order.refresh_from_db()
        self.assertEqual(order.cancellation_reason, "Rupture de stock")

    def test_suspended_restaurant_cannot_receive_orders(self):
        from django.core.exceptions import ValidationError
        from apps.orders.models import Cart

        cart = Cart.objects.create(restaurant=self.resto_a, order_type=OrderType.TAKEAWAY, session_key="s2")
        add_to_cart(cart, self.product, 1)
        self.resto_a.status = RestaurantStatus.SUSPENDED
        self.resto_a.save()
        with self.assertRaises(ValidationError):
            checkout_cart(
                cart,
                contact={"first_name": "A", "last_name": "B", "phone": "0700000000"},
            )


class KycDocumentTests(BaseTenantCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user("admin@test.local", Role.PLATFORM_ADMIN)
        self.resto_a.identity_document = SimpleUploadedFile("cni.png", b"\x89PNG\r\n\x1a\n" + b"0" * 16)
        self.resto_a.save()

    def test_document_has_no_public_url(self):
        with self.assertRaises(ValueError):
            self.resto_a.identity_document.url  # noqa: B018

    def test_only_platform_admin_can_read_document(self):
        url = reverse("notifications:admin_restaurant_document", args=[self.resto_a.pk, "identite"])
        self.assertEqual(Client().get(url).status_code, 302)
        self.assertEqual(self.login(self.manager_a).get(url).status_code, 403)
        response = self.login(self.admin).get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        response.close()


class DemoLoginsTests(TestCase):
    @override_settings(DEMO_LOGINS=False)
    def test_demo_accounts_hidden_when_disabled(self):
        response = self.client.get(reverse("users:login"))
        self.assertNotContains(response, "Admin1234!")

    @override_settings(DEMO_LOGINS=True)
    def test_demo_accounts_shown_when_enabled(self):
        response = self.client.get(reverse("users:login"))
        self.assertContains(response, "Comptes de démonstration")
