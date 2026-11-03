from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.menus.models import Category, Product
from apps.orders.models import Cart, Order, OrderStatus, OrderType
from apps.orders.services import add_to_cart, checkout_cart, transition_order
from apps.restaurants.models import Employee, Restaurant
from apps.tables.models import DiningTable
from apps.users.models import User
from apps.users.roles import Role


class OrderTests(TestCase):
    def setUp(self):
        self.resto = Restaurant.objects.create(name="Commandes", address="x", city="Y", delivery_fee=Decimal("500"))
        self.other = Restaurant.objects.create(name="Autre", address="z", city="Y")
        self.customer = User.objects.create_user(
            email="c@test.local",
            password="pass12345",
            first_name="C",
            last_name="C",
            phone="0700000000",
            role=Role.CUSTOMER,
        )
        self.manager = User.objects.create_user(
            email="om@test.local", password="pass12345", first_name="M", last_name="M", role=Role.MANAGER
        )
        Employee.objects.create(user=self.manager, restaurant=self.resto, role=Role.MANAGER)
        self.category = Category.objects.create(restaurant=self.resto, name="Plats")
        self.product = Product.objects.create(
            restaurant=self.resto, category=self.category, name="Riz", price=Decimal("2000")
        )
        self.foreign = Product.objects.create(
            restaurant=self.other,
            category=Category.objects.create(restaurant=self.other, name="X"),
            name="Interdit",
            price=Decimal("100"),
        )
        self.table = DiningTable.objects.create(restaurant=self.resto, number="1")
        self.client = APIClient()

    def test_cart_rejects_foreign_product(self):
        cart = Cart.objects.create(restaurant=self.resto, user=self.customer, order_type=OrderType.TAKEAWAY)
        with self.assertRaises(ValidationError):
            add_to_cart(cart, self.foreign)

    def test_checkout_totals(self):
        cart = Cart.objects.create(restaurant=self.resto, user=self.customer, order_type=OrderType.DELIVERY)
        add_to_cart(cart, self.product, 2)
        order = checkout_cart(
            cart,
            customer=self.customer,
            address_text="Rue des Jardins",
            contact={"city": "Abidjan", "district": "Cocody"},
        )
        self.assertEqual(order.subtotal, Decimal("4000"))
        self.assertEqual(order.delivery_fee, Decimal("500"))
        self.assertEqual(order.total, Decimal("4500"))
        self.assertEqual(order.items.count(), 1)
        self.assertFalse(cart.items.exists())

    def test_dine_in_requires_table(self):
        cart = Cart.objects.create(restaurant=self.resto, user=self.customer, order_type=OrderType.DINE_IN)
        add_to_cart(cart, self.product)
        with self.assertRaises(ValidationError):
            checkout_cart(cart, customer=self.customer)

    def test_status_flow_dine_in(self):
        cart = Cart.objects.create(
            restaurant=self.resto, user=self.customer, order_type=OrderType.DINE_IN, table=self.table
        )
        add_to_cart(cart, self.product)
        order = checkout_cart(cart, customer=self.customer)
        transition_order(order, OrderStatus.ACCEPTED)
        transition_order(order, OrderStatus.PREPARING)
        transition_order(order, OrderStatus.READY)
        transition_order(order, OrderStatus.SERVED)
        transition_order(order, OrderStatus.COMPLETED)
        self.assertEqual(order.status, OrderStatus.COMPLETED)
        with self.assertRaises(ValidationError):
            transition_order(order, OrderStatus.READY)

    def test_api_isolation_orders(self):
        cart = Cart.objects.create(restaurant=self.resto, user=self.customer, order_type=OrderType.TAKEAWAY)
        add_to_cart(cart, self.product)
        order = checkout_cart(cart, customer=self.customer, contact={"city": "Abidjan"})
        other_manager = User.objects.create_user(
            email="other@test.local", password="pass12345", first_name="O", last_name="O", role=Role.MANAGER
        )
        Employee.objects.create(user=other_manager, restaurant=self.other, role=Role.MANAGER)
        self.client.force_authenticate(other_manager)
        response = self.client.get(f"/api/orders/{order.id}/")
        self.assertIn(response.status_code, (403, 404))

    def test_manager_dashboard_is_operational(self):
        web = Client()
        web.force_login(self.manager)
        session = web.session
        session["current_restaurant_id"] = self.resto.pk
        session.save()
        response = web.get("/gerant/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Espace gérant")
        self.assertContains(response, "Service en cours")
        self.assertNotContains(response, "Dernières commandes")  # la liste est dans Commandes
        self.assertContains(response, "Plats les plus vendus")
        self.assertNotContains(response, "Actions rapides")  # le tableau de bord ne garde que les chiffres
        self.assertContains(response, "Fermer le restaurant")  # l'interrupteur ouvert / fermé
        self.assertContains(response, "Mise en service")

    def test_guest_must_give_contact_to_order(self):
        cart = Cart.objects.create(restaurant=self.resto, order_type=OrderType.TAKEAWAY)
        add_to_cart(cart, self.product)
        with self.assertRaises(ValidationError):
            checkout_cart(cart)
        order = checkout_cart(
            cart,
            contact={
                "first_name": "Awa",
                "last_name": "Kone",
                "phone": "0700112233",
                "city": "Abidjan",
            },
        )
        self.assertEqual(order.customer_phone, "0700112233")
        self.assertEqual(order.contact_name, "Awa Kone")
        self.assertEqual(order.delivery_city, "Abidjan")

    def _guest_with_cart(self, order_type):
        web = Client()
        page = web.get(f"/restaurants/{self.resto.slug}/?type={order_type}")
        self.assertEqual(page.status_code, 200)
        added = web.post(
            "/panier/ajouter/",
            {
                "restaurant": self.resto.pk,
                "product": self.product.pk,
                "order_type": order_type,
                "next": f"/restaurants/{self.resto.slug}/?type={order_type}",
            },
        )
        self.assertEqual(added.status_code, 302)
        return web

    def test_restaurant_page_is_the_order_page(self):
        web = self._guest_with_cart("takeaway")
        page = web.get(f"/restaurants/{self.resto.slug}/")
        self.assertContains(page, "Ajouter")
        self.assertContains(page, "Votre commande")
        self.assertContains(page, "1 dans le panier")
        self.assertContains(page, "2\u202f000\u00a0FCFA")
        self.assertContains(page, "Continuer")
        old_menu = web.get(f"/restaurant/{self.resto.slug}/menu/?type=delivery")
        self.assertRedirects(old_menu, f"/restaurants/{self.resto.slug}/?type=delivery", fetch_redirect_response=False)

    def test_takeaway_checkout_asks_for_the_name_only(self):
        web = self._guest_with_cart("takeaway")
        page = web.get(f"/commander/?restaurant={self.resto.pk}")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Qui commande ?")
        self.assertContains(page, "À récupérer au restaurant")
        self.assertNotContains(page, "Où livrer ?")
        self.assertNotContains(page, "simulé")
        self.assertContains(page, "Téléphone (facultatif)")  # pour retrouver sa commande avec le numéro
        self.assertNotContains(page, "E-mail")
        refused = web.post("/commander/", {})
        self.assertEqual(refused.status_code, 200)
        self.assertContains(refused, "Il manque des informations")
        self.assertFalse(Order.objects.exists())
        placed = web.post(
            "/commander/",
            {"first_name": "Awa"},
        )
        order = Order.objects.get()
        self.assertRedirects(placed, f"/commandes/{order.pk}/?nouvelle=1", fetch_redirect_response=False)
        self.assertEqual(order.order_type, OrderType.TAKEAWAY)
        self.assertEqual(order.payments.get().method, "cash_on_site")
        tracking = web.get(f"/commandes/{order.pk}/?nouvelle=1")
        self.assertContains(tracking, "En attente de réponse")  # tant que le restaurant n'a pas accepté
        self.assertNotContains(tracking, "Commande acceptée")
        transition_order(order, OrderStatus.ACCEPTED)
        self.assertContains(web.get(f"/commandes/{order.pk}/"), "Commande acceptée")
        self.assertContains(tracking, order.reference)

    def test_delivery_checkout_requires_where_to_deliver(self):
        self.resto.min_delivery_amount = Decimal("0")
        self.resto.save()
        web = self._guest_with_cart("delivery")
        page = web.get(f"/commander/?restaurant={self.resto.pk}")
        self.assertContains(page, "Où livrer ?")
        refused = web.post(
            "/commander/",
            {"first_name": "Awa", "last_name": "Kone", "phone": "0700112233"},
        )
        self.assertContains(refused, "Indiquez votre secteur.")
        self.assertFalse(Order.objects.exists())
        web.post(
            "/commander/",
            {
                "first_name": "Awa",
                "last_name": "Kone",
                "phone": "0700112233",
                "district": "Cocody",
                "address_text": "Rue des Jardins",
                "delivery_day": "tomorrow",
                "latitude": "5.359952",
                "longitude": "-3.996647",
            },
        )
        order = Order.objects.get()
        self.assertEqual(order.order_type, OrderType.DELIVERY)
        self.assertEqual(order.delivery_district, "Cocody")
        self.assertEqual(order.delivery.address_text, "Rue des Jardins, Cocody")
        self.assertTrue(order.is_for_later)
        self.assertEqual(order.day_label, "Demain")
        self.assertEqual(order.payments.get().method, "cash_on_delivery")

    def test_cannot_change_someone_else_cart(self):
        owner = self._guest_with_cart("takeaway")
        item = Cart.objects.get(session_key=owner.session.session_key).items.get()
        stranger = Client()
        stranger.get("/")
        response = stranger.post(f"/panier/ligne/{item.pk}/supprimer/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(type(item).objects.filter(pk=item.pk).exists())


class OrderReceiptTests(TestCase):
    setUp = OrderTests.setUp
    _guest_with_cart = OrderTests._guest_with_cart

    def _place(self, web, **extra):
        data = {"first_name": "Awa", **extra}
        web.post("/commander/", data)
        return Order.objects.order_by("-pk").first()

    def test_daily_number_is_short_and_per_restaurant(self):
        first = self._place(self._guest_with_cart("takeaway"))
        second = self._place(self._guest_with_cart("takeaway"))
        self.assertEqual((first.short_number, second.short_number), ("001", "002"))
        other_cart = Cart.objects.create(restaurant=self.other, order_type=OrderType.TAKEAWAY, session_key="o")
        add_to_cart(other_cart, self.foreign, 1)
        other = checkout_cart(other_cart, contact={"first_name": "B", "last_name": "B", "phone": "0700000001"})
        self.assertEqual(other.short_number, "001")
        self.assertNotEqual(first.reference, first.short_number)
        self.assertRegex(first.reference, r"^R\d{6}-[0-9A-F]{6}$")

    def test_customer_gets_receipt_on_screen(self):
        self.resto.min_delivery_amount = Decimal("0")
        self.resto.save()
        web = self._guest_with_cart("delivery")
        order = self._place(
            web,
            last_name="Kone",
            phone="0700112233",
            district="Cocody",
            address_text="Rue des Jardins",
        )
        page = web.get(f"/commandes/{order.pk}/?nouvelle=1")
        self.assertContains(page, order.short_number)
        self.assertContains(page, order.reference)
        printable = web.get(f"/commandes/{order.pk}/recu/")
        self.assertEqual(printable.status_code, 200)
        self.assertContains(printable, "Reçu de commande")
        self.assertContains(printable, "Riz")
        self.assertEqual(Client().get(f"/commandes/{order.pk}/recu/").status_code, 403)

    def test_no_email_no_receipt_mail(self):
        from django.core import mail

        self._place(self._guest_with_cart("takeaway"))
        self.assertEqual(len(mail.outbox), 0)

    def test_tracking_with_short_number_and_phone(self):
        order = self._place(self._guest_with_cart("takeaway"))
        Order.objects.filter(pk=order.pk).update(customer_phone="0701122334")
        stranger = Client()
        # le numéro seul ne suffit pas : il faut aussi le téléphone
        no_phone = stranger.post("/suivi/", {"number": order.short_number, "phone": ""})
        self.assertContains(no_phone, "Indiquez le téléphone")
        wrong = stranger.post("/suivi/", {"number": order.short_number, "phone": "0799999999"})
        self.assertContains(wrong, "Aucune commande ne correspond")
        found = stranger.post("/suivi/", {"number": f"N° {order.short_number}", "phone": "07 01 12 23 34"})
        self.assertRedirects(found, f"/commandes/{order.pk}/", fetch_redirect_response=False)

    def test_tracking_with_the_full_reference_still_works(self):
        order = self._place(self._guest_with_cart("takeaway"))
        found = Client().post("/suivi/", {"number": order.reference.lower(), "phone": ""})
        self.assertRedirects(found, f"/commandes/{order.pk}/", fetch_redirect_response=False)

    def test_old_short_numbers_are_not_trackable(self):
        from datetime import timedelta

        from django.utils import timezone

        order = self._place(self._guest_with_cart("takeaway"))
        Order.objects.filter(pk=order.pk).update(
            customer_phone="0701122334", service_date=timezone.localdate() - timedelta(days=10)
        )
        refused = Client().post("/suivi/", {"number": order.short_number, "phone": "0701122334"})
        self.assertContains(refused, "Aucune commande ne correspond")


class ManagerOrderListTests(TestCase):
    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        OrderTests.setUp(self)
        self.web = Client()
        self.web.force_login(self.manager)
        session = self.web.session
        session["current_restaurant_id"] = self.resto.pk
        session.save()
        self.pending = self._order("Awa", "70111111")
        self.done = self._order("Moussa", "70222222")
        for status in (
            OrderStatus.ACCEPTED,
            OrderStatus.PREPARING,
            OrderStatus.READY,
            OrderStatus.PICKED_UP,
            OrderStatus.COMPLETED,
        ):
            transition_order(self.done, status)
        self.old = self._order("Fatim", "70333333")
        Order.objects.filter(pk=self.old.pk).update(created_at=timezone.now() - timedelta(days=3))

    def _order(self, name, phone):
        cart = Cart.objects.create(restaurant=self.resto, order_type=OrderType.TAKEAWAY, session_key=phone)
        add_to_cart(cart, self.product, 1)
        return checkout_cart(cart, contact={"first_name": name, "last_name": "K", "phone": phone})

    def ids(self, response):
        return {order.pk for group in response.context["groups"] for order in group["orders"]}

    def test_default_tab_shows_orders_to_handle(self):
        page = self.web.get("/gerant/commandes/")
        self.assertEqual(page.context["filters"]["tab"], "a-traiter")
        self.assertEqual(self.ids(page), {self.pending.pk, self.old.pk})
        tabs = {tab["key"]: tab["count"] for tab in page.context["tabs"]}
        self.assertEqual(tabs["a-traiter"], 2)
        self.assertEqual(tabs["aujourdhui"], 2)

    def test_today_tab_and_day_groups(self):
        page = self.web.get("/gerant/commandes/?vue=aujourdhui")
        self.assertEqual(self.ids(page), {self.pending.pk, self.done.pk})
        self.assertEqual(len(page.context["groups"]), 1)
        self.assertContains(page, "Aujourd&#x27;hui")
        everything = self.web.get("/gerant/commandes/?vue=toutes")
        self.assertEqual(len(everything.context["groups"]), 2)  # aujourd'hui + il y a 3 jours
        self.assertEqual(everything.context["groups"][0]["count"], 2)

    def test_search_by_name_phone_reference_and_short_number(self):
        by_name = self.web.get("/gerant/commandes/?vue=toutes&q=fatim")
        self.assertEqual(self.ids(by_name), {self.old.pk})
        by_phone = self.web.get("/gerant/commandes/?vue=toutes&q=70 22 22 22")
        self.assertEqual(self.ids(by_phone), {self.done.pk})
        by_ref = self.web.get(f"/gerant/commandes/?vue=toutes&q={self.done.reference.lower()}")
        self.assertEqual(self.ids(by_ref), {self.done.pk})
        by_number = self.web.get(f"/gerant/commandes/?vue=aujourdhui&q={self.pending.short_number}")
        self.assertIn(self.pending.pk, self.ids(by_number))

    def test_dashboard_status_link_still_works(self):
        page = self.web.get("/gerant/commandes/?status=completed")
        self.assertEqual(page.context["filters"]["tab"], "toutes")
        self.assertEqual(self.ids(page), {self.done.pk})
        self.assertContains(page, "Effacer les filtres")

    def test_pagination_keeps_filters(self):
        for i in range(41):
            self._order(f"Client{i}", f"7040{i:04d}")
        page = self.web.get("/gerant/commandes/?vue=toutes&type=takeaway")
        self.assertTrue(page.context["is_paginated"])
        self.assertContains(page, "type=takeaway")
        self.assertContains(page, "page=2")
        self.assertNotContains(page, "??")  # l adresse ne doit avoir qu un seul point d interrogation

    def test_other_restaurant_orders_never_listed(self):
        other_cart = Cart.objects.create(restaurant=self.other, order_type=OrderType.TAKEAWAY, session_key="x")
        add_to_cart(other_cart, self.foreign, 1)
        foreign = checkout_cart(other_cart, contact={"first_name": "Z", "last_name": "Z", "phone": "70999999"})
        page = self.web.get("/gerant/commandes/?vue=toutes")
        self.assertNotIn(foreign.pk, self.ids(page))


class OrderDateFilterTests(TestCase):
    """Réutilise les 3 commandes de ManagerOrderListTests : 2 d'aujourd'hui, 1 d'il y a 3 jours."""

    setUp = ManagerOrderListTests.setUp
    _order = ManagerOrderListTests._order
    ids = ManagerOrderListTests.ids

    def test_one_day(self):
        from datetime import timedelta

        from django.utils import timezone

        day = (timezone.localdate() - timedelta(days=3)).isoformat()
        page = self.web.get(f"/gerant/commandes/?jour={day}")
        self.assertEqual(
            page.context["filters"]["tab"], "toutes"
        )  # un filtre de date affiche tout, pas seulement « à traiter »
        self.assertEqual(self.ids(page), {self.old.pk})
        self.assertEqual(page.context["range_summary"]["count"], 1)
        self.assertContains(page, "sur cette période")
        self.assertContains(page, 'name="jour"')  # conservé quand on cherche ou filtre ensuite

    def test_range_and_presets(self):
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        span = self.web.get(f"/gerant/commandes/?du={today - timedelta(days=5)}&au={today - timedelta(days=2)}")
        self.assertEqual(self.ids(span), {self.old.pk})
        todays = self.web.get("/gerant/commandes/?periode=aujourdhui")
        self.assertEqual(self.ids(todays), {self.pending.pk, self.done.pk})
        self.assertEqual(todays.context["range_summary"]["count"], 2)
        yesterday = self.web.get("/gerant/commandes/?periode=hier")
        self.assertEqual(self.ids(yesterday), set())
        self.assertContains(yesterday, "Aucune commande ne correspond")
        week = self.web.get("/gerant/commandes/?periode=7j")
        self.assertEqual(self.ids(week), {self.pending.pk, self.done.pk, self.old.pk})

    def test_date_combines_with_search_and_status(self):
        page = self.web.get("/gerant/commandes/?periode=aujourdhui&status=completed")
        self.assertEqual(self.ids(page), {self.done.pk})
        page = self.web.get("/gerant/commandes/?periode=7j&q=fatim")
        self.assertEqual(self.ids(page), {self.old.pk})


class StatusFeedbackTests(TestCase):
    """Après un clic en cuisine ou au service, le personnel comprend où est passée la commande."""

    _order = ManagerOrderListTests._order

    def setUp(self):
        ManagerOrderListTests.setUp(self)
        reception = User.objects.create_user(
            email="rec@test.local", password="pass12345", first_name="R", last_name="R", role=Role.RECEPTION
        )
        Employee.objects.create(user=reception, restaurant=self.resto, role=Role.RECEPTION)
        self.manager_web = self.web
        self.web = Client()  # à partir d'ici, « web » est la réception : seule elle traite les commandes
        self.web.force_login(reception)
        session = self.web.session
        session["current_restaurant_id"] = self.resto.pk
        session.save()

    def test_manager_only_watches_he_cannot_change_a_status(self):
        for status in (OrderStatus.ACCEPTED, OrderStatus.CANCELLED):
            response = self.manager_web.post(f"/gerant/commandes/{self.pending.pk}/statut/", {"status": status})
            self.assertEqual(response.status_code, 403, status)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, OrderStatus.PENDING)
        page = self.manager_web.get(f"/gerant/commandes/{self.pending.pk}/")
        self.assertNotContains(page, "Refuser")

    def test_clear_message_and_return_to_the_moved_card(self):
        response = self.web.post(
            f"/gerant/commandes/{self.pending.pk}/statut/",
            {"status": OrderStatus.ACCEPTED, "next": "/reception/"},
            follow=False,
        )
        self.assertEqual(response.url, f"/reception/#commande-{self.pending.pk}")
        page = self.web.get("/reception/", {"q": self.pending.short_number})
        text = " ".join(m.message for m in page.context["messages"])
        self.assertIn(f"N° {self.pending.short_number} : Acceptée", text)
        self.assertContains(page, f'id="commande-{self.pending.pk}"')

    def test_each_step_says_what_comes_next(self):
        from apps.orders.views import status_message

        order = self.pending
        for status, expected in (
            (OrderStatus.PREPARING, "préparation"),
            (OrderStatus.SERVED, "encaisser"),
            (OrderStatus.PICKED_UP, "payée"),
        ):
            order.status = status
            self.assertIn(expected, status_message(order).lower())

    def test_without_next_the_manager_goes_back_to_the_order_page(self):
        response = self.web.post(f"/gerant/commandes/{self.pending.pk}/statut/", {"status": OrderStatus.ACCEPTED})
        self.assertEqual(response.url, f"/gerant/commandes/{self.pending.pk}/")
        evil = self.web.post(
            f"/gerant/commandes/{self.pending.pk}/statut/",
            {"status": OrderStatus.PREPARING, "next": "https://pirate.example/"},
        )
        self.assertTrue(evil.url.startswith("/gerant/commandes/"))


class DineInCheckoutFormTests(TestCase):
    def test_qr_code_order_only_asks_for_a_name(self):
        from apps.orders.forms import CheckoutForm

        form = CheckoutForm({"first_name": "Moussa"}, order_type=OrderType.DINE_IN)
        self.assertEqual(list(form.fields)[:1], ["first_name"])
        for hidden in ("last_name", "email", "note"):
            self.assertNotIn(hidden, form.fields)
        self.assertFalse(form.fields["phone"].required)  # le téléphone reste facultatif à table et à emporter
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(CheckoutForm({}, order_type=OrderType.DINE_IN).is_valid())

    def test_delivery_still_needs_full_contact(self):
        from apps.orders.forms import CheckoutForm

        self.assertFalse(CheckoutForm({"first_name": "Awa"}, order_type=OrderType.DELIVERY).is_valid())


class DeliveryFormTests(TestCase):
    def test_delivery_only_asks_the_essentials(self):
        from apps.orders.forms import CheckoutForm

        form = CheckoutForm(order_type=OrderType.DELIVERY)
        self.assertEqual(
            list(form.fields),
            ["first_name", "last_name", "phone", "district", "address_text", "latitude", "longitude", "delivery_day"],
        )

    def test_delivery_day_defaults_to_today_and_can_be_tomorrow(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.orders.forms import CheckoutForm

        base = {"first_name": "Awa", "last_name": "K", "phone": "0700112233", "district": "S22", "address_text": "x"}
        today = CheckoutForm(base, order_type=OrderType.DELIVERY)
        self.assertTrue(today.is_valid(), today.errors)
        self.assertEqual(today.scheduled_for, timezone.localdate())
        tomorrow = CheckoutForm({**base, "delivery_day": "tomorrow"}, order_type=OrderType.DELIVERY)
        self.assertTrue(tomorrow.is_valid(), tomorrow.errors)
        self.assertEqual(tomorrow.scheduled_for, timezone.localdate() + timedelta(days=1))


class PreorderTests(TestCase):
    """Commande à l'avance : commandée de chez soi, mangée au restaurant à l'heure d'arrivée choisie."""

    def setUp(self):
        self.resto = Restaurant.objects.create(name="Sur commande", address="x", city="Y", estimated_prep_minutes=40)
        category = Category.objects.create(restaurant=self.resto, name="Plats")
        self.product = Product.objects.create(
            restaurant=self.resto, category=category, name="Riz", price=Decimal("2000")
        )

    def test_form_asks_name_phone_and_arrival_and_hides_short_delays(self):
        from apps.orders.forms import CheckoutForm

        form = CheckoutForm(order_type=OrderType.PREORDER, restaurant=self.resto)
        self.assertEqual(list(form.fields), ["first_name", "phone", "latitude", "longitude", "arrival_delay"])
        # Préparation de 40 min : le premier délai proposé est 45 min.
        self.assertEqual([value for value, _ in form.fields["arrival_delay"].choices][0], "45")
        self.assertNotIn("30", [value for value, _ in form.fields["arrival_delay"].choices])
        self.assertFalse(CheckoutForm({"first_name": "Awa"}, order_type=OrderType.PREORDER, restaurant=self.resto).is_valid())
        ok = CheckoutForm(
            {"first_name": "Awa", "phone": "0700112233", "arrival_delay": "60"},
            order_type=OrderType.PREORDER,
            restaurant=self.resto,
        )
        self.assertTrue(ok.is_valid(), ok.errors)
        self.assertGreater(ok.arrival_at, timezone.now() + timedelta(minutes=59))

    def test_full_order_from_the_restaurant_page(self):
        web = Client()
        page = web.get(f"/restaurants/{self.resto.slug}/?type=preorder")
        self.assertContains(page, "À l'avance")
        web.post(
            "/panier/ajouter/",
            {"restaurant": self.resto.pk, "product": self.product.pk, "order_type": "preorder"},
        )
        sent = web.post(
            "/commander/", {"first_name": "Awa", "phone": "0700112233", "arrival_delay": "60"}
        )
        order = Order.objects.get()
        self.assertEqual(order.order_type, OrderType.PREORDER)
        self.assertIsNotNone(order.arrival_at)
        self.assertEqual(order.payments.get().method, "cash_on_site")
        self.assertEqual(sent.status_code, 302)
        self.assertContains(web.get(sent["Location"]), order.arrival_label)

    def test_arrival_time_is_required(self):
        cart = Cart.objects.create(restaurant=self.resto, order_type=OrderType.PREORDER, session_key="s")
        add_to_cart(cart, self.product)
        with self.assertRaises(ValidationError):
            checkout_cart(cart, contact={"first_name": "Awa", "phone": "0700112233"})


class CounterSaleTests(TestCase):
    """La réception vend à un client qui n'a pas commandé sur le site."""

    def setUp(self):
        self.resto = Restaurant.objects.create(name="Comptoir", address="x", city="Bobo")
        category = Category.objects.create(restaurant=self.resto, name="Plats")
        self.riz = Product.objects.create(restaurant=self.resto, category=category, name="Riz", price=Decimal("2000"))
        self.jus = Product.objects.create(restaurant=self.resto, category=category, name="Jus", price=Decimal("500"))
        self.reception = User.objects.create_user(
            email="cs@test.local", password="pass12345", first_name="R", last_name="R", role=Role.RECEPTION
        )
        Employee.objects.create(user=self.reception, restaurant=self.resto, role=Role.RECEPTION)
        self.manager = User.objects.create_user(
            email="cm@test.local", password="pass12345", first_name="M", last_name="M", role=Role.MANAGER
        )
        Employee.objects.create(user=self.manager, restaurant=self.resto, role=Role.MANAGER)

    def _web(self, user):
        web = Client()
        web.force_login(user)
        session = web.session
        session["current_restaurant_id"] = self.resto.pk
        session.save()
        return web

    def test_sale_is_recorded_as_completed_and_paid(self):
        web = self._web(self.reception)
        response = web.post(
            "/reception/vente/",
            {f"qty_{self.riz.pk}": "2", f"qty_{self.jus.pk}": "1", "payment": "mobile", "name": "Moussa"},
        )
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.order_type, OrderType.COUNTER)
        self.assertEqual(order.status, OrderStatus.COMPLETED)
        self.assertEqual(order.total, Decimal("4500"))
        self.assertEqual(order.items.count(), 2)
        payment = order.payments.get()
        self.assertEqual((payment.status, payment.method), ("paid", "mobile_money"))
        # la vente compte dans l'argent encaissé du jour, et ne reste pas dans les commandes à traiter
        page = web.get("/reception/")
        self.assertEqual(page.context["today"]["mobile"], Decimal("4500"))
        self.assertEqual(page.context["queue"], [])

    def test_empty_or_unknown_sales_are_refused(self):
        web = self._web(self.reception)
        web.post("/reception/vente/", {"payment": "cash"})
        web.post("/reception/vente/", {f"qty_{self.riz.pk}": "1"})  # pas de moyen de paiement
        web.post("/reception/vente/", {"qty_9999": "1", "payment": "cash"})
        self.assertEqual(Order.objects.count(), 0)

    def test_unavailable_dish_cannot_be_sold(self):
        Product.objects.filter(pk=self.jus.pk).update(is_available=False)
        self._web(self.reception).post("/reception/vente/", {f"qty_{self.jus.pk}": "1", "payment": "cash"})
        self.assertEqual(Order.objects.count(), 0)

    def test_manager_only_watches(self):
        web = self._web(self.manager)
        self.assertEqual(web.post("/reception/vente/", {f"qty_{self.riz.pk}": "1", "payment": "cash"}).status_code, 403)
        self.assertEqual(Order.objects.count(), 0)

    def test_sale_page_lists_the_menu(self):
        page = self._web(self.reception).get("/reception/vente/")
        self.assertContains(page, "Riz")
        self.assertContains(page, "Jus")


class OptionalPhoneTests(TestCase):
    def setUp(self):
        OrderTests.setUp(self)

    def test_takeaway_phone_is_saved_and_lets_the_customer_track_from_another_device(self):
        web = Client()
        web.post("/panier/ajouter/", {"restaurant": self.resto.pk, "product": self.product.pk, "order_type": "takeaway"})
        web.post("/commander/", {"first_name": "Awa", "phone": "07 01 12 23 34"})
        order = Order.objects.get()
        self.assertEqual(order.customer_phone, "07 01 12 23 34")
        found = Client().post("/suivi/", {"number": order.short_number, "phone": "0701122334"})
        self.assertRedirects(found, f"/commandes/{order.pk}/", fetch_redirect_response=False)

    def test_a_bad_phone_is_refused_but_an_empty_one_is_fine(self):
        web = Client()
        web.post("/panier/ajouter/", {"restaurant": self.resto.pk, "product": self.product.pk, "order_type": "takeaway"})
        bad = web.post("/commander/", {"first_name": "Awa", "phone": "123"})
        self.assertEqual(bad.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        ok = web.post("/commander/", {"first_name": "Awa", "phone": ""})
        self.assertEqual(ok.status_code, 302)
