"""Tests de sécurité transverses : rôles, isolation entre restaurants, QR code, paiement espèces, KYC."""

from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.finance.services import dashboard_metrics
from apps.inventory.models import StockItem
from apps.menus.models import Category, Product
from apps.orders.models import OrderStatus, OrderType
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
        url = reverse("backoffice:restaurant_document", args=[self.resto_a.pk, "identite"])
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


class MultiRestaurantRoleTests(BaseTenantCase):
    def test_role_is_checked_in_the_restaurant_being_viewed(self):
        # gérant chez A, simple cuisinier chez B : pas d'accès gérant chez B
        Employee.objects.create(user=self.manager_a, restaurant=self.resto_b, role=Role.COOK)
        client = self.login(self.manager_a)
        url = reverse("menus:products")
        self.assertEqual(client.get(url, {"restaurant": self.resto_b.pk}).status_code, 403)
        self.assertEqual(client.get(url, {"restaurant": self.resto_a.pk}).status_code, 200)

    def test_without_explicit_choice_user_lands_where_role_matches(self):
        Employee.objects.create(user=self.manager_a, restaurant=self.resto_b, role=Role.COOK)
        client = self.login(self.manager_a)
        session = client.session
        session["current_restaurant_id"] = self.resto_b.pk
        session.save()
        response = client.get(reverse("menus:products"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["restaurant"], self.resto_a)


class PriceFormatTests(TestCase):
    def test_prices_are_whole_francs(self):
        from apps.core.templatetags.resto import prix

        self.assertEqual(prix(Decimal("3333.3333")), "3\u202f333\u00a0FCFA")
        self.assertEqual(prix(Decimal("10000.00")), "10\u202f000\u00a0FCFA")
        self.assertEqual(prix(None), "0\u00a0FCFA")


class SuspensionTests(BaseTenantCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user("root@test.local", Role.PLATFORM_ADMIN)

    def test_admin_suspends_and_reactivates(self):
        admin = self.login(self.admin)
        suspend = reverse("backoffice:restaurant_suspend", args=[self.resto_a.pk])
        admin.post(suspend, {"note": ""})
        self.resto_a.refresh_from_db()
        self.assertEqual(self.resto_a.status, RestaurantStatus.ACTIVE)  # motif obligatoire
        admin.post(suspend, {"note": "Impayés"})
        self.resto_a.refresh_from_db()
        self.assertEqual(self.resto_a.status, RestaurantStatus.SUSPENDED)
        self.assertFalse(self.resto_a.is_accepting_orders)
        self.assertEqual(Client().get(reverse("restaurants:detail", args=[self.resto_a.slug])).status_code, 404)
        manager_page = self.login(self.manager_a).get(reverse("menus:products"))
        self.assertRedirects(manager_page, reverse("restaurants:pending"), fetch_redirect_response=False)
        admin.post(reverse("backoffice:restaurant_reactivate", args=[self.resto_a.pk]))
        self.resto_a.refresh_from_db()
        self.assertEqual(self.resto_a.status, RestaurantStatus.ACTIVE)
        self.assertTrue(self.resto_a.is_accepting_orders)

    def test_only_platform_admin_can_suspend(self):
        response = self.login(self.manager_a).post(
            reverse("backoffice:restaurant_suspend", args=[self.resto_b.pk]), {"note": "x"}
        )
        self.assertEqual(response.status_code, 403)


class WaiterTakeawayTests(BaseTenantCase):
    def test_waiter_hands_over_ready_takeaway(self):
        order = self.new_order(OrderType.TAKEAWAY)
        for status in (OrderStatus.ACCEPTED, OrderStatus.PREPARING, OrderStatus.READY):
            transition_order(order, status)
        waiter = self.login(self.waiter_a)
        board = waiter.get(reverse("orders:waiter"))
        self.assertContains(board, order.number)
        waiter.post(reverse("orders:change_status", args=[order.pk]), {"status": OrderStatus.PICKED_UP})
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PICKED_UP)
        self.assertEqual(order.payments.get().status, PaymentStatus.PAID)


class OrderTrackingTests(BaseTenantCase):
    def setUp(self):
        super().setUp()
        from django.core.cache import cache

        cache.clear()
        self.order = self.new_order()  # téléphone 0700000000
        self.url = reverse("orders:track")

    def test_customer_finds_order_from_another_device(self):
        stranger = Client()
        detail = reverse("orders:detail", args=[self.order.pk])
        self.assertEqual(stranger.get(detail).status_code, 403)
        response = stranger.post(self.url, {"number": self.order.number.lower(), "phone": "07 00 00 00 00"})
        self.assertRedirects(response, detail)
        self.assertContains(stranger.get(detail), self.order.number)

    def test_number_with_spaces_and_hash_is_accepted(self):
        spaced = "# " + " ".join(self.order.number)
        response = Client().post(self.url, {"number": spaced, "phone": "0700000000"})
        self.assertEqual(response.status_code, 302)

    def test_wrong_phone_reveals_nothing(self):
        response = Client().post(self.url, {"number": self.order.number, "phone": "0711111111"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aucune commande ne correspond")
        self.assertNotContains(response, "Awa")

    def test_dine_in_order_without_phone_needs_only_number(self):
        from apps.orders.models import Cart

        cart = Cart.objects.create(
            restaurant=self.resto_a, order_type=OrderType.DINE_IN, table=self.table, session_key="t"
        )
        add_to_cart(cart, self.product, 1)
        order = checkout_cart(cart, contact={"first_name": "Moussa"})
        response = Client().post(self.url, {"number": order.number, "phone": ""})
        self.assertRedirects(response, reverse("orders:detail", args=[order.pk]))

    def test_too_many_failures_are_blocked(self):
        client = Client()
        for _ in range(10):
            client.post(self.url, {"number": "R000000AAAAAA", "phone": "0700000000"})
        response = client.post(self.url, {"number": self.order.number, "phone": "0700000000"})
        self.assertContains(response, "Réessayez dans quelques minutes")


class KitchenBoardTests(BaseTenantCase):
    def test_board_shows_clear_actions_per_step(self):
        order = self.new_order()
        cook = self.login(self.cook_a)
        self.assertContains(cook.get(reverse("orders:kitchen")), "Accepter")
        transition_order(order, OrderStatus.ACCEPTED)
        self.assertContains(cook.get(reverse("orders:kitchen")), "Commencer la préparation")
        transition_order(order, OrderStatus.PREPARING)
        self.assertContains(cook.get(reverse("orders:kitchen")), "prêt")
        transition_order(order, OrderStatus.READY)
        self.assertContains(cook.get(reverse("orders:kitchen")), "Le client vient la chercher")
