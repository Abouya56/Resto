from django.test import TestCase
from rest_framework.test import APIClient

from apps.restaurants.models import Employee, Restaurant
from apps.users.models import User
from apps.users.roles import Role


class IsolationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.resto_a = Restaurant.objects.create(name="Alpha", address="1 rue A", city="Abidjan")
        self.resto_b = Restaurant.objects.create(name="Beta", address="2 rue B", city="Abidjan")
        self.manager_a = User.objects.create_user(
            email="a@test.local", password="pass12345", first_name="A", last_name="A", role=Role.MANAGER
        )
        self.manager_b = User.objects.create_user(
            email="b@test.local", password="pass12345", first_name="B", last_name="B", role=Role.MANAGER
        )
        Employee.objects.create(user=self.manager_a, restaurant=self.resto_a, role=Role.MANAGER)
        Employee.objects.create(user=self.manager_b, restaurant=self.resto_b, role=Role.MANAGER)

    def test_manager_cannot_see_other_restaurant(self):
        self.client.force_authenticate(self.manager_a)
        response = self.client.get("/api/restaurants/")
        ids = [item["id"] for item in response.data["results"]]
        self.assertIn(self.resto_a.id, ids)
        self.assertNotIn(self.resto_b.id, ids)

    def test_manager_cannot_update_other_restaurant(self):
        self.client.force_authenticate(self.manager_a)
        response = self.client.patch(
            f"/api/restaurants/{self.resto_b.id}/",
            {"name": "Hack"},
            format="json",
        )
        self.assertIn(response.status_code, (403, 404))
        self.resto_b.refresh_from_db()
        self.assertEqual(self.resto_b.name, "Beta")


class RestaurantOnboardingTests(TestCase):
    def test_manager_can_create_restaurant(self):
        response = self.client.post(
            "/ouvrir-un-restaurant/",
            {
                "first_name": "Fatou",
                "last_name": "Diop",
                "email": "nouveau.gerant@test.local",
                "phone": "07000000",
                "password1": "Motdepasse123!",
                "password2": "Motdepasse123!",
                "restaurant_name": "Chez Fatou",
                "address": "Rue 12",
                "city": "Abidjan",
                "district": "Cocody",
                "delivery_fee": "500",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="nouveau.gerant@test.local")
        self.assertEqual(user.role, Role.MANAGER)
        restaurant = Restaurant.objects.get(name="Chez Fatou")
        self.assertEqual(restaurant.owner, user)
        self.assertTrue(
            Employee.objects.filter(user=user, restaurant=restaurant, role=Role.MANAGER).exists()
        )

    def test_home_explains_both_paths(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Je veux commander")
        self.assertContains(response, "Je crée mon restaurant")
