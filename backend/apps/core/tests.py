"""Tests de sécurité transverses : rôles, isolation entre restaurants, QR code, paiement espèces, KYC."""

from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
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
        self.reception_a = make_user("ra@test.local", Role.RECEPTION)
        Employee.objects.create(user=self.manager_a, restaurant=self.resto_a, role=Role.MANAGER)
        Employee.objects.create(user=self.manager_b, restaurant=self.resto_b, role=Role.MANAGER)
        Employee.objects.create(user=self.reception_a, restaurant=self.resto_a, role=Role.RECEPTION)
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
            arrival_at=timezone.now() + timedelta(minutes=50) if order_type == OrderType.PREORDER else None,
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
            {"user": newcomer.pk, "role": Role.RECEPTION, "restaurant": self.resto_b.pk},
            format="json",
        )
        self.assertIn(response.status_code, (201, 400, 403))
        self.assertFalse(Employee.objects.filter(user=newcomer, restaurant=self.resto_b).exists())

    def test_form_does_not_overwrite_existing_account(self):
        victim = make_user("victim@test.local", Role.MANAGER)
        victim.first_name = "Original"
        victim.save()
        Employee.objects.create(user=victim, restaurant=self.resto_b, role=Role.MANAGER)
        Employee.objects.filter(restaurant=self.resto_a, role=Role.RECEPTION).delete()  # la place réception est libre
        form = EmployeeForm(
            {
                "email": "victim@test.local",
                "first_name": "Pirate",
                "last_name": "Pirate",
                "role": Role.RECEPTION,
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
            {"email": "ra@test.local", "first_name": "x", "last_name": "y", "role": Role.RECEPTION, "status": "active"},
            restaurant=self.resto_a,
        )
        self.assertFalse(form.is_valid())
        admin = make_user("root@test.local", Role.PLATFORM_ADMIN)
        form = EmployeeForm(
            {"email": admin.email, "first_name": "x", "last_name": "y", "role": Role.RECEPTION, "status": "active"},
            restaurant=self.resto_a,
        )
        self.assertFalse(form.is_valid())

    def test_form_edit_cannot_change_email(self):
        employee = Employee.objects.get(user=self.reception_a)
        form = EmployeeForm(
            {
                "email": "manager-b@evil.test",
                "first_name": "Test",
                "last_name": "cook",
                "role": Role.RECEPTION,
                "status": "active",
            },
            instance=employee,
            restaurant=self.resto_a,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        employee.refresh_from_db()
        self.assertEqual(employee.user.email, "ra@test.local")


class RoleChecksTests(BaseTenantCase):
    def test_product_toggle_is_post_only_and_manager_only(self):
        url = reverse("menus:product_toggle", args=[self.product.pk])
        self.assertEqual(self.login(self.manager_a).get(url).status_code, 405)
        self.assertEqual(self.login(self.reception_a).post(url).status_code, 403)
        self.assertEqual(self.login(self.manager_b).post(url).status_code, 403)
        self.login(self.manager_a).post(url)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_available)

    def test_qr_regeneration_requires_post_and_manager(self):
        ensure_qrcode(self.table)
        url = reverse("tables:regenerate", args=[self.table.pk])
        self.assertEqual(self.login(self.manager_a).get(url).status_code, 405)
        self.assertEqual(self.login(self.reception_a).post(url).status_code, 403)

    def test_stock_move_requires_post_and_manager(self):
        item = StockItem.objects.create(restaurant=self.resto_a, name="Farine", quantity=Decimal("5"))
        url = reverse("inventory:move", args=[item.pk])
        self.assertEqual(self.login(self.manager_a).get(url).status_code, 405)
        self.assertEqual(self.login(self.reception_a).post(url, {}).status_code, 403)

    def test_change_status_requires_matching_role(self):
        order = self.new_order()
        url = reverse("orders:change_status", args=[order.pk])
        self.assertEqual(self.login(self.manager_b).post(url, {"status": OrderStatus.ACCEPTED}).status_code, 403)
        self.login(self.reception_a).post(url, {"status": OrderStatus.ACCEPTED})
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.ACCEPTED)

    def test_change_status_ignores_external_redirect(self):
        order = self.new_order()
        response = self.login(self.reception_a).post(
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
        self.assertEqual(self.login(self.manager_b).post(url).status_code, 403)
        self.login(self.reception_a).post(url)
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
        Employee.objects.create(user=self.manager_a, restaurant=self.resto_b, role=Role.RECEPTION)
        client = self.login(self.manager_a)
        url = reverse("menus:products")
        self.assertEqual(client.get(url, {"restaurant": self.resto_b.pk}).status_code, 403)
        self.assertEqual(client.get(url, {"restaurant": self.resto_a.pk}).status_code, 200)

    def test_without_explicit_choice_user_lands_where_role_matches(self):
        Employee.objects.create(user=self.manager_a, restaurant=self.resto_b, role=Role.RECEPTION)
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
        waiter = self.login(self.reception_a)
        board = waiter.get(reverse("orders:reception_type", args=["emporter"]))
        self.assertContains(board, f"N° {order.short_number}")
        waiter.post(reverse("orders:change_status", args=[order.pk]), {"status": OrderStatus.PICKED_UP})
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PICKED_UP)
        self.assertEqual(order.payments.get().status, PaymentStatus.PAID)


class ReceptionBoardTests(BaseTenantCase):
    def test_dashboard_counts_and_each_type_has_its_own_page(self):
        dine = self.new_order(OrderType.DINE_IN, table=self.table)
        takeaway = self.new_order(OrderType.TAKEAWAY)
        delivery = self.new_order(OrderType.DELIVERY)
        ahead = self.new_order(OrderType.PREORDER)
        reception = self.login(self.reception_a)
        board = reception.get(reverse("orders:reception"))
        counts = {g["key"]: len(g["orders"]) for g in board.context["groups"]}
        self.assertEqual(counts, {"table": 1, "emporter": 1, "avance": 1, "livraison": 1})
        self.assertEqual(board.context["new_total"], 4)
        self.assertEqual(board.context["today"]["received"], 4)
        for key, order in (("table", dine), ("emporter", takeaway), ("avance", ahead), ("livraison", delivery)):
            page = reception.get(reverse("orders:reception_type", args=[key]))
            self.assertEqual([o.pk for o in page.context["current"]["orders"]], [order.pk], key)
        table_page = reception.get(reverse("orders:reception_type", args=["table"]))
        self.assertContains(table_page, "Accepter la commande")
        self.assertNotContains(table_page, "Espèces")  # on n'encaisse qu'après avoir accepté
        transition_order(dine, OrderStatus.ACCEPTED)
        self.assertContains(reception.get(reverse("orders:reception_type", args=["table"])), "Espèces")
        self.assertContains(reception.get(reverse("orders:reception_type", args=["avance"])), "Arrive à")
        self.assertEqual(reception.get("/reception/nimporte/").status_code, 404)

    def test_cannot_collect_before_accepting(self):
        order = self.new_order(OrderType.TAKEAWAY)
        reception = self.login(self.reception_a)
        reception.post(
            reverse("orders:change_status", args=[order.pk]), {"status": OrderStatus.COMPLETED, "payment": "cash"}
        )
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PENDING)
        self.assertEqual(order.payments.get().status, PaymentStatus.PENDING)
        reception.post(reverse("orders:change_status", args=[order.pk]), {"status": OrderStatus.ACCEPTED})
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.ACCEPTED)

    def test_accepting_an_order_does_not_move_it(self):
        first = self.new_order(OrderType.TAKEAWAY)
        second = self.new_order(OrderType.TAKEAWAY)
        third = self.new_order(OrderType.TAKEAWAY)
        reception = self.login(self.reception_a)
        url = reverse("orders:reception_type", args=["emporter"])
        before = [o.pk for o in reception.get(url).context["current"]["orders"]]
        self.assertEqual(before, [first.pk, second.pk, third.pk])
        # on accepte la deuxième : elle reste à sa place, entre la première et la troisième
        reception.post(reverse("orders:change_status", args=[second.pk]), {"status": OrderStatus.ACCEPTED})
        after = reception.get(url).context["current"]["orders"]
        self.assertEqual([o.pk for o in after], [first.pk, second.pk, third.pk])
        self.assertEqual([o.status for o in after], [OrderStatus.PENDING, OrderStatus.ACCEPTED, OrderStatus.PENDING])

    def test_dashboard_shows_money_collected_today(self):
        order = self.new_order(OrderType.DINE_IN, table=self.table)
        transition_order(order, OrderStatus.ACCEPTED)
        reception = self.login(self.reception_a)
        reception.post(
            reverse("orders:change_status", args=[order.pk]), {"status": OrderStatus.COMPLETED, "payment": "mobile"}
        )
        today = reception.get(reverse("orders:reception")).context["today"]
        self.assertEqual(today["mobile"], order.total)
        self.assertEqual(today["cash"], 0)
        self.assertEqual(today["collected"], order.total)

    def test_reception_searches_by_number_name_and_phone(self):
        dine = self.new_order(OrderType.DINE_IN, table=self.table)
        takeaway = self.new_order(OrderType.TAKEAWAY)
        Order.objects.filter(pk=dine.pk).update(customer_first_name="Awa", customer_phone="70112233")
        Order.objects.filter(pk=takeaway.pk).update(customer_first_name="Moussa", customer_phone="76998877")
        reception = self.login(self.reception_a)
        url = reverse("orders:reception")
        for query, expected in (("Awa", dine), ("9988", takeaway), ("70112", dine), (dine.number, dine)):
            queue = reception.get(url, {"q": query}).context["queue"]
            self.assertEqual([o.pk for o in queue], [expected.pk], query)
        self.assertEqual(reception.get(url, {"q": "zzz"}).context["queue"], [])

    def test_short_number_search_finds_only_todays_order(self):
        from datetime import timedelta

        today_order = self.new_order(OrderType.TAKEAWAY)
        yesterday = self.new_order(OrderType.PREORDER)
        Order.objects.filter(pk=yesterday.pk).update(
            daily_number=today_order.daily_number, service_date=timezone.localdate() - timedelta(days=1)
        )
        reception = self.login(self.reception_a)
        found = reception.get(reverse("orders:reception"), {"q": today_order.short_number}).context["queue"]
        self.assertEqual([o.pk for o in found], [today_order.pk])

    def test_closing_with_cash_records_the_payment_and_leaves_the_board(self):
        order = self.new_order(OrderType.DINE_IN, table=self.table)
        transition_order(order, OrderStatus.ACCEPTED)
        reception = self.login(self.reception_a)
        reception.post(
            reverse("orders:change_status", args=[order.pk]), {"status": OrderStatus.COMPLETED, "payment": "cash"}
        )
        board = reception.get(reverse("orders:reception"))
        self.assertEqual(board.context["queue"], [])
        order.refresh_from_db()
        payment = order.payments.get()
        self.assertEqual(payment.status, PaymentStatus.PAID)
        self.assertEqual(payment.method, "cash_on_site")

    def test_delivery_is_closed_by_reception_with_mobile_money(self):
        order = self.new_order(OrderType.DELIVERY)
        transition_order(order, OrderStatus.ACCEPTED)
        self.login(self.reception_a).post(
            reverse("orders:change_status", args=[order.pk]), {"status": OrderStatus.COMPLETED, "payment": "mobile"}
        )
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.COMPLETED)
        self.assertEqual(order.payments.get().method, "mobile_money")

    def test_waiter_closes_a_fresh_order_in_one_click_with_mobile_money(self):
        """La cuisine ne clique sur rien : le serveur passe de « nouvelle » à « terminée » d'un seul geste."""
        order = self.new_order(OrderType.DINE_IN, table=self.table)
        self.assertEqual(order.status, OrderStatus.PENDING)
        transition_order(order, OrderStatus.ACCEPTED)
        waiter = self.login(self.reception_a)
        waiter.post(
            reverse("orders:change_status", args=[order.pk]), {"status": OrderStatus.COMPLETED, "payment": "mobile"}
        )
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.COMPLETED)
        self.assertIsNotNone(order.completed_at)
        payment = order.payments.get()
        self.assertEqual(payment.status, PaymentStatus.PAID)
        self.assertEqual(payment.method, "mobile_money")


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
        self.assertContains(stranger.get(detail), self.order.reference)

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


class ManagerLateAlertTests(BaseTenantCase):
    def dashboard(self):
        manager = self.login(self.manager_a)
        session = manager.session
        session["current_restaurant_id"] = self.resto_a.pk
        session.save()
        return manager.get(reverse("orders:manager_dashboard"))

    def test_alert_counts_only_todays_orders_waiting_over_15_minutes(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.orders.models import Order

        self.new_order()  # toute fraîche : pas en retard
        late = self.new_order()
        stale = self.new_order()
        Order.objects.filter(pk=late.pk).update(created_at=timezone.now() - timedelta(minutes=20))
        Order.objects.filter(pk=stale.pk).update(created_at=timezone.now() - timedelta(days=3))  # oubliée : ignorée
        page = self.dashboard()
        self.assertEqual(page.context["late_count"], 1)
        self.assertContains(page, "plus de 15 min")

    def test_no_alert_when_nothing_is_late(self):
        self.new_order()
        self.assertNotContains(self.dashboard(), "plus de 15 min")


class InstallableAppTests(TestCase):
    def test_manifest_describes_installable_app(self):
        import json

        response = Client().get("/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        self.assertIn("manifest+json", response["Content-Type"])
        data = json.loads(response.content)
        self.assertEqual(data["display"], "standalone")
        self.assertEqual(data["short_name"], "Resto")
        sizes = {icon["sizes"] for icon in data["icons"]}
        self.assertTrue({"192x192", "512x512"} <= sizes)
        self.assertTrue(any(icon["purpose"] == "maskable" for icon in data["icons"]))
        from django.contrib.staticfiles import finders

        for icon in data["icons"]:
            path = icon["src"].split("?")[0].removeprefix("/static/")
            self.assertTrue(finders.find(path), f"icône introuvable : {icon['src']}")

    def test_service_worker_is_served_from_site_root(self):
        response = Client().get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response["Content-Type"])
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertIn("no-cache", response["Cache-Control"])
        worker = b"".join(response.streaming_content).decode()
        self.assertIn("/hors-ligne/", worker)
        self.assertIn('request.method !== "GET"', worker)

    def test_pages_link_the_manifest_and_offline_page_needs_no_login(self):
        home = Client().get("/")
        self.assertContains(home, 'rel="manifest"')
        self.assertContains(home, 'name="theme-color"')
        self.assertContains(home, "data-install")
        offline = Client().get("/hors-ligne/")
        self.assertEqual(offline.status_code, 200)
        self.assertContains(offline, "Pas de connexion")


class CustomerVerdictTests(BaseTenantCase):
    def test_customer_sees_accepted_then_refused_when_the_waiter_refuses(self):
        order = self.new_order(OrderType.DINE_IN, table=self.table)
        guest = Client()
        guest.post(reverse("orders:track"), {"number": order.number, "phone": "0700000000"})
        page = guest.get(reverse("orders:detail", args=[order.pk]))
        self.assertContains(page, "En attente de réponse")  # pas encore accepté par la réception
        transition_order(order, OrderStatus.ACCEPTED)
        page = guest.get(reverse("orders:detail", args=[order.pk]))
        self.assertContains(page, "Commande acceptée")
        self.assertNotContains(page, "track-steps")

        waiter = self.login(self.reception_a)
        waiter.post(reverse("orders:change_status", args=[order.pk]), {"status": OrderStatus.CANCELLED})
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertContains(guest.get(reverse("orders:detail", args=[order.pk])), "Commande refusée")


class RefusalReasonTests(BaseTenantCase):
    def test_reception_gives_a_reason_and_the_customer_sees_it(self):
        order = self.new_order(OrderType.TAKEAWAY)
        Order.objects.filter(pk=order.pk).update(customer_phone="0700000000")
        guest = Client()
        guest.post(reverse("orders:track"), {"number": order.short_number, "phone": "0700000000"})
        waiting = guest.get(reverse("orders:detail", args=[order.pk]))
        self.assertContains(waiting, "Revenez vérifier dans quelques minutes")
        self.login(self.reception_a).post(
            reverse("orders:change_status", args=[order.pk]), {"status": OrderStatus.CANCELLED, "reason": "Plat épuisé"}
        )
        order.refresh_from_db()
        self.assertEqual(order.cancellation_reason, "Plat épuisé")
        refused = guest.get(reverse("orders:detail", args=[order.pk]))
        self.assertContains(refused, "Commande refusée")
        self.assertContains(refused, "Raison : Plat épuisé")
        self.assertNotContains(refused, "Revenez vérifier")

    def test_refuse_buttons_offer_the_reasons(self):
        self.new_order(OrderType.TAKEAWAY)
        page = self.login(self.reception_a).get(reverse("orders:reception_type", args=["emporter"]))
        for reason in ("Plat épuisé", "Restaurant complet", "Restaurant fermé", "Autre raison"):
            self.assertContains(page, f'value="{reason}"')


class ManagerLiveCountsTests(BaseTenantCase):
    def test_manager_counts_match_the_reception_screen(self):
        open_order = self.new_order(OrderType.TAKEAWAY)
        collected = self.new_order(OrderType.TAKEAWAY)
        # une ancienne commande « récupérée » (déjà encaissée) ne doit plus compter comme « à servir »
        Order.objects.filter(pk=collected.pk).update(status=OrderStatus.PICKED_UP)
        done = self.new_order(OrderType.TAKEAWAY)
        transition_order(done, OrderStatus.ACCEPTED)
        transition_order(done, OrderStatus.COMPLETED)
        manager = self.login(self.manager_a).get(reverse("orders:manager_dashboard"))
        reception = self.login(self.reception_a).get(reverse("orders:reception"))
        self.assertEqual(manager.context["live"]["to_serve"], 1)
        self.assertEqual(manager.context["live"]["to_serve"], len(reception.context["queue"]))
        self.assertEqual(reception.context["queue"][0].pk, open_order.pk)

    def test_dashboard_shows_every_order_type(self):
        self.new_order(OrderType.DINE_IN, table=self.table)
        self.new_order(OrderType.TAKEAWAY)
        self.new_order(OrderType.PREORDER)
        self.new_order(OrderType.DELIVERY)
        page = self.login(self.manager_a).get(reverse("orders:manager_dashboard"))
        counts = {item["type"]: (item["open"], item["new"]) for item in page.context["live_types"]}
        self.assertEqual(counts, {"dine_in": (1, 1), "takeaway": (1, 1), "preorder": (1, 1), "delivery": (1, 1)})
        for label in ("À table", "À emporter", "À l&#x27;avance", "Livraison"):
            self.assertContains(page, label)


class TeamLimitsTests(BaseTenantCase):
    """Un seul compte réception par restaurant ; le gérant ne crée jamais de gérant."""

    def form(self, email="neuf@test.local", role=Role.RECEPTION, restaurant=None):
        return EmployeeForm(
            {"email": email, "first_name": "N", "last_name": "N", "password": "Motdepasse-2026!", "role": role, "status": "active"},
            restaurant=restaurant or self.resto_a,
        )

    def test_second_reception_account_is_refused(self):
        form = self.form()  # resto_a a déjà reception_a
        self.assertFalse(form.is_valid())
        self.assertIn("déjà son compte réception", str(form.errors))

    def test_first_reception_account_is_created_with_the_reception_role_whatever_is_sent(self):
        Employee.objects.filter(restaurant=self.resto_a, role=Role.RECEPTION).delete()
        form = self.form(role=Role.MANAGER)  # même si on tente d'envoyer « gérant »
        self.assertTrue(form.is_valid(), form.errors)
        employee = form.save()
        self.assertEqual(employee.role, Role.RECEPTION)
        self.assertEqual(employee.user.role, Role.RECEPTION)

    def test_manager_cannot_change_a_role(self):
        reception = Employee.objects.get(restaurant=self.resto_a, role=Role.RECEPTION)
        form = EmployeeForm(
            {"email": reception.user.email, "first_name": "x", "last_name": "y", "role": Role.MANAGER, "status": "active"},
            instance=reception,
            restaurant=self.resto_a,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().role, Role.RECEPTION)

    def test_employee_page_hides_the_add_button_when_the_slot_is_taken(self):
        page = self.login(self.manager_a).get(reverse("restaurants:employees"))
        self.assertFalse(page.context["can_add"])
        self.assertNotContains(page, "Ajouter le réceptionniste")
        redirected = self.login(self.manager_a).get(reverse("restaurants:employee_create"))
        self.assertEqual(redirected.status_code, 302)
        Employee.objects.filter(restaurant=self.resto_a, role=Role.RECEPTION).delete()
        page = self.login(self.manager_a).get(reverse("restaurants:employees"))
        self.assertContains(page, "Ajouter le réceptionniste")

    def test_api_refuses_a_manager_account_and_a_second_reception(self):
        client = APIClient()
        client.force_authenticate(self.manager_a)
        newcomer = make_user("api-new@test.local", Role.CUSTOMER)
        as_manager = client.post("/api/restaurants/employees/", {"user": newcomer.pk, "role": Role.MANAGER, "status": "active"})
        self.assertEqual(as_manager.status_code, 400)
        second = client.post("/api/restaurants/employees/", {"user": newcomer.pk, "role": Role.RECEPTION, "status": "active"})
        self.assertEqual(second.status_code, 400)
        self.assertFalse(Employee.objects.filter(user=newcomer).exists())

    def test_api_manager_cannot_delete_the_receptionist(self):
        reception = Employee.objects.get(restaurant=self.resto_a, role=Role.RECEPTION)
        client = APIClient()
        client.force_authenticate(self.manager_a)
        response = client.delete(f"/api/restaurants/employees/{reception.pk}/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Employee.objects.filter(pk=reception.pk).exists())

    def test_api_manager_cannot_suspend_the_receptionist(self):
        reception = Employee.objects.get(restaurant=self.resto_a, role=Role.RECEPTION)
        client = APIClient()
        client.force_authenticate(self.manager_a)
        self.assertEqual(client.post(f"/api/restaurants/employees/{reception.pk}/deactivate/").status_code, 403)
        self.assertEqual(
            client.patch(f"/api/restaurants/employees/{reception.pk}/", {"status": "inactive"}).status_code, 400
        )
        reception.refresh_from_db()
        self.assertTrue(reception.is_active)


class NewOrderAlertTests(BaseTenantCase):
    """Le repère de l'alerte sonore suit la commande à accepter la plus récente."""

    def test_reception_and_manager_pages_carry_the_latest_pending_order(self):
        self.new_order()
        latest = self.new_order()
        for user, url in ((self.reception_a, "orders:reception"), (self.manager_a, "orders:manager_dashboard")):
            response = self.login(user).get(reverse(url))
            self.assertContains(response, f'data-pending-latest="{latest.pk}"')
            self.assertContains(response, f'data-restaurant="{self.resto_a.pk}"')

    def test_only_the_reception_hears_the_ring(self):
        reception = self.login(self.reception_a).get(reverse("orders:reception"))
        manager = self.login(self.manager_a).get(reverse("orders:manager_dashboard"))
        self.assertContains(reception, 'data-alert="sound"')
        self.assertContains(manager, 'data-alert="silent"')

    def test_accepted_orders_no_longer_count(self):
        order = self.new_order()
        transition_order(order, OrderStatus.ACCEPTED)
        response = self.login(self.reception_a).get(reverse("orders:reception"))
        self.assertContains(response, 'data-pending-latest="0"')


class SpokenAlertTests(BaseTenantCase):
    def test_reception_page_tells_the_type_of_the_newest_order(self):
        self.new_order(OrderType.TAKEAWAY)
        self.new_order(OrderType.DELIVERY)
        response = self.login(self.reception_a).get(reverse("orders:reception"))
        self.assertContains(response, 'data-latest-type="delivery"')
