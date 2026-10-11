from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.users.models import User
from apps.users.roles import Role


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_api_login_returns_tokens(self):
        User.objects.create_user(
            email="gerant@test.local",
            password="Motdepasse123!",
            first_name="Nia",
            last_name="Kone",
            role=Role.MANAGER,
        )
        login = self.client.post(
            reverse("api-login"),
            {"email": "gerant@test.local", "password": "Motdepasse123!"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("access", login.data)

    def test_api_register_does_not_exist(self):
        response = self.client.post("/api/auth/register/", {"email": "x@test.local"}, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(User.objects.filter(email="x@test.local").exists())

    def test_web_register_is_closed(self):
        response = self.client.post(reverse("users:register"), {"email": "leo@test.local"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/connexion/", response.url)
        self.assertFalse(User.objects.filter(email="leo@test.local").exists())
