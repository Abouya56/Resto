from decimal import Decimal

from django.test import Client, TestCase

from apps.deliveries.models import Delivery
from apps.deliveries.services import ensure_delivery
from apps.menus.models import Category, Product
from apps.orders.models import Cart, OrderType
from apps.orders.services import add_to_cart, checkout_cart
from apps.restaurants.models import Employee, Restaurant
from apps.users.models import User
from apps.users.roles import Role


class DeliveryTests(TestCase):
    def setUp(self):
        self.resto = Restaurant.objects.create(name="Liv", address="x", city="Y", delivery_fee=Decimal("800"))
        category = Category.objects.create(restaurant=self.resto, name="P")
        self.product = Product.objects.create(
            restaurant=self.resto, category=category, name="Pizza", price=Decimal("5000")
        )

    def _order(self, order_type, name):
        cart = Cart.objects.create(restaurant=self.resto, order_type=order_type, session_key=name)
        add_to_cart(cart, self.product)
        return checkout_cart(
            cart,
            address_text="Secteur 22",
            contact={"first_name": name, "last_name": "K", "phone": "70111111", "city": "Bobo", "district": "Koko"},
        )

    def test_delivery_record_keeps_the_address_and_is_created_once(self):
        order = self._order(OrderType.DELIVERY, "Awa")
        delivery = ensure_delivery(order)
        self.assertEqual(ensure_delivery(order).pk, delivery.pk)
        self.assertEqual(Delivery.objects.filter(order=order).count(), 1)
        self.assertIn("Secteur 22", delivery.address_text)

    def test_manager_finds_deliveries_with_the_order_type_filter(self):
        delivery_order = self._order(OrderType.DELIVERY, "Awa")
        takeaway_order = self._order(OrderType.TAKEAWAY, "Moussa")
        manager = User.objects.create_user(
            email="dm@test.local", password="pass12345", first_name="M", last_name="M", role=Role.MANAGER
        )
        Employee.objects.create(user=manager, restaurant=self.resto, role=Role.MANAGER)
        web = Client()
        web.force_login(manager)
        session = web.session
        session["current_restaurant_id"] = self.resto.pk
        session.save()
        page = web.get("/gerant/commandes/?type=delivery")
        listed = {o.pk for g in page.context["groups"] for o in g["orders"]}
        self.assertEqual(listed, {delivery_order.pk})
        self.assertNotIn(takeaway_order.pk, listed)
        self.assertEqual(web.get("/gerant/livraisons/").status_code, 404)  # plus de page dédiée
