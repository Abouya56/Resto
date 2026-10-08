from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.menus.models import Category, Product
from apps.restaurants.models import Employee, Restaurant
from apps.users.models import User
from apps.users.roles import Role


class ProductIsolationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.resto_a = Restaurant.objects.create(name="A", address="a", city="X")
        self.resto_b = Restaurant.objects.create(name="B", address="b", city="Y")
        self.manager_a = User.objects.create_user(
            email="ma@test.local", password="pass12345", first_name="M", last_name="A", role=Role.MANAGER
        )
        Employee.objects.create(user=self.manager_a, restaurant=self.resto_a, role=Role.MANAGER)
        self.cat_a = Category.objects.create(restaurant=self.resto_a, name="Entrées")
        self.cat_b = Category.objects.create(restaurant=self.resto_b, name="Entrées B")
        self.product_b = Product.objects.create(
            restaurant=self.resto_b, category=self.cat_b, name="Secret", price=Decimal("10")
        )

    def test_create_product_scoped(self):
        self.client.force_authenticate(self.manager_a)
        response = self.client.post(
            "/api/menus/products/",
            {"category": self.cat_a.id, "name": "Salade", "price": "1500"},
            format="json",
            HTTP_X_RESTAURANT_ID=str(self.resto_a.id),
        )
        self.assertEqual(response.status_code, 201)
        product = Product.objects.get(name="Salade")
        self.assertEqual(product.restaurant_id, self.resto_a.id)

    def test_cannot_read_other_restaurant_product(self):
        self.client.force_authenticate(self.manager_a)
        response = self.client.get(f"/api/menus/products/{self.product_b.id}/")
        self.assertIn(response.status_code, (403, 404))
