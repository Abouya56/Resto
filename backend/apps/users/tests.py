from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.users.models import User
from apps.users.roles import Role


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_and_login(self):
        response = self.client.post(
            reverse("api-register"),
            {
                "email": "nouveau@test.local",
                "first_name": "Nia",
                "last_name": "Kone",
                "phone": "0700",
                "password": "Motdepasse123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="nouveau@test.local")
        self.assertEqual(user.role, Role.CUSTOMER)
        self.assertTrue(user.check_password("Motdepasse123!"))

        login = self.client.post(
            reverse("api-login"),
            {"email": "nouveau@test.local", "password": "Motdepasse123!"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("access", login.data)

    def test_web_register(self):
        response = self.client.post(
            reverse("users:register"),
            {
                "first_name": "Leo",
                "last_name": "Mensah",
                "email": "leo@test.local",
                "phone": "01",
                "password1": "Motdepasse123!",
                "password2": "Motdepasse123!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email="leo@test.local").exists())
