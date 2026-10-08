from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
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
            email="c@test.local", password="pass12345", first_name="C", last_name="C", role=Role.CUSTOMER
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
        order = checkout_cart(cart, customer=self.customer, address_text="Cocody")
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
        order = checkout_cart(cart, customer=self.customer)
        other_manager = User.objects.create_user(
            email="other@test.local", password="pass12345", first_name="O", last_name="O", role=Role.MANAGER
        )
        Employee.objects.create(user=other_manager, restaurant=self.other, role=Role.MANAGER)
        self.client.force_authenticate(other_manager)
        response = self.client.get(f"/api/orders/{order.id}/")
        self.assertIn(response.status_code, (403, 404))
