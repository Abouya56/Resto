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

    def test_no_customer_space(self):
        # Commande sans compte : ni historique, ni adresses enregistrées.
        for url in ("/commandes/", "/profil/adresses/", "/api/auth/addresses/"):
            self.assertEqual(self.client.get(url).status_code, 404, url)


class LoginBrandTests(TestCase):
    def test_login_page_shows_the_site_name_not_the_domain(self):
        page = self.client.get("/connexion/")
        self.assertContains(page, "navbar-brand")
        self.assertNotContains(page, "testserver")


class CreatePlatformAdminCommandTests(TestCase):
    def run_command(self, **kwargs):
        from io import StringIO

        from django.core.management import call_command

        call_command("create_platform_admin", stdout=StringIO(), **kwargs)

    def test_creates_a_super_admin_with_a_strong_password(self):
        self.run_command(email="Boss@Exemple.com", first_name="Awa", last_name="Kone", password="Un-bon-mdp-2026!")
        user = User.objects.get(email="boss@exemple.com")
        self.assertEqual(user.role, Role.PLATFORM_ADMIN)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password("Un-bon-mdp-2026!"))

    def test_refuses_a_weak_password_and_a_duplicate(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self.run_command(email="a@exemple.com", first_name="A", last_name="B", password="12345678")
        self.assertFalse(User.objects.filter(email="a@exemple.com").exists())
        self.run_command(email="a@exemple.com", first_name="A", last_name="B", password="Un-bon-mdp-2026!")
        with self.assertRaises(CommandError):
            self.run_command(email="a@exemple.com", first_name="A", last_name="B", password="Un-bon-mdp-2026!")


class EmailCaseLoginTests(TestCase):
    def test_login_ignores_capital_letters_in_the_email(self):
        User.objects.create_user(email="gerant@gmail.com", password="Mot2passe!", first_name="G", last_name="R", role=Role.MANAGER)
        response = self.client.post(reverse("users:login"), {"username": " Gerant@Gmail.com ", "password": "Mot2passe!"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)
