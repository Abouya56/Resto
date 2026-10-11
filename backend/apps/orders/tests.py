from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import Client, TestCase
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
        cart = Cart.objects.create(
            restaurant=self.resto, user=self.customer, order_type=OrderType.TAKEAWAY
        )
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
        self.assertContains(response, "Commandes récentes")
        self.assertContains(response, "Actions rapides")
        self.assertContains(response, "Ouvert aux commandes")
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

    def test_takeaway_checkout_asks_name_and_phone_only(self):
        web = self._guest_with_cart("takeaway")
        page = web.get(f"/commander/?restaurant={self.resto.pk}")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Qui commande ?")
        self.assertContains(page, "À récupérer au restaurant")
        self.assertNotContains(page, "Où livrer ?")
        self.assertNotContains(page, "simulé")
        refused = web.post("/commander/", {})
        self.assertEqual(refused.status_code, 200)
        self.assertContains(refused, "Il manque des informations")
        self.assertFalse(Order.objects.exists())
        placed = web.post(
            "/commander/",
            {"first_name": "Awa", "last_name": "Kone", "phone": "07 00 11 22 33"},
        )
        order = Order.objects.get(customer_phone="07 00 11 22 33")
        self.assertRedirects(placed, f"/commandes/{order.pk}/?nouvelle=1", fetch_redirect_response=False)
        self.assertEqual(order.order_type, OrderType.TAKEAWAY)
        self.assertEqual(order.payments.get().method, "cash_on_site")
        tracking = web.get(f"/commandes/{order.pk}/?nouvelle=1")
        self.assertContains(tracking, "Merci Awa")
        self.assertContains(tracking, "Prête à retirer")
        self.assertContains(tracking, order.number)

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
        self.assertContains(refused, "Indiquez le quartier.")
        self.assertFalse(Order.objects.exists())
        web.post(
            "/commander/",
            {
                "first_name": "Awa",
                "last_name": "Kone",
                "phone": "0700112233",
                "city": "Abidjan",
                "district": "Cocody",
                "address_text": "Rue des Jardins",
                "landmark": "Pharmacie",
                "latitude": "5.359952",
                "longitude": "-3.996647",
            },
        )
        order = Order.objects.get()
        self.assertEqual(order.order_type, OrderType.DELIVERY)
        self.assertEqual(order.delivery_district, "Cocody")
        self.assertEqual(order.delivery.address_text, "Rue des Jardins, Cocody, Abidjan")
        self.assertEqual(order.payments.get().method, "cash_on_delivery")

    def test_cannot_change_someone_else_cart(self):
        owner = self._guest_with_cart("takeaway")
        item = Cart.objects.get(session_key=owner.session.session_key).items.get()
        stranger = Client()
        stranger.get("/")
        response = stranger.post(f"/panier/ligne/{item.pk}/supprimer/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(type(item).objects.filter(pk=item.pk).exists())
