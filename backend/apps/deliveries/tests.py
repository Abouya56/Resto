from decimal import Decimal

from django.test import TestCase

from apps.deliveries.models import DeliveryStatus
from apps.deliveries.services import assign_driver, driver_transition, ensure_delivery
from apps.menus.models import Category, Product
from apps.orders.models import Cart, OrderStatus, OrderType
from apps.orders.services import add_to_cart, checkout_cart, transition_order
from apps.restaurants.models import Employee, Restaurant
from apps.users.models import User
from apps.users.roles import Role


class DeliveryTests(TestCase):
    def setUp(self):
        self.resto = Restaurant.objects.create(name="Liv", address="x", city="Y", delivery_fee=Decimal("800"))
        self.customer = User.objects.create_user(
            email="dlc@test.local", password="pass12345", first_name="C", last_name="C"
        )
        self.driver = User.objects.create_user(
            email="drv@test.local", password="pass12345", first_name="D", last_name="D", role=Role.DRIVER
        )
        Employee.objects.create(user=self.driver, restaurant=self.resto, role=Role.DRIVER)
        category = Category.objects.create(restaurant=self.resto, name="P")
        self.product = Product.objects.create(
            restaurant=self.resto, category=category, name="Pizza", price=Decimal("5000")
        )

    def test_delivery_assignment_and_status(self):
        cart = Cart.objects.create(restaurant=self.resto, user=self.customer, order_type=OrderType.DELIVERY)
        add_to_cart(cart, self.product)
        order = checkout_cart(cart, customer=self.customer, address_text="Plateau")
        for status in (OrderStatus.ACCEPTED, OrderStatus.PREPARING, OrderStatus.READY):
            transition_order(order, status)
        delivery = ensure_delivery(order)
        assign_driver(delivery, self.driver)
        self.assertEqual(delivery.status, DeliveryStatus.ASSIGNED)
        driver_transition(delivery, DeliveryStatus.ACCEPTED, self.driver)
        driver_transition(delivery, DeliveryStatus.PICKED_UP, self.driver)
        driver_transition(delivery, DeliveryStatus.IN_TRANSIT, self.driver)
        driver_transition(delivery, DeliveryStatus.DELIVERED, self.driver)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.DELIVERED)
