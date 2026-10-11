from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from PIL import Image
from rest_framework.test import APIClient

from apps.restaurants.models import Employee, Restaurant, RestaurantStatus
from apps.users.models import User
from apps.users.roles import Role


def identity_file(name="cni.png"):
    return SimpleUploadedFile(name, b"\x89PNG\r\n\x1a\n" + b"0" * 32, content_type="image/png")


def logo_file(name="logo.png"):
    buffer = BytesIO()
    Image.new("RGB", (32, 32), (224, 161, 6)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


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
    def test_manager_request_stays_pending_until_admin_validates(self):
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
                "identity_type": "cni",
                "identity_document": identity_file(),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/demande-en-attente/", response.url)
        user = User.objects.get(email="nouveau.gerant@test.local")
        self.assertEqual(user.role, Role.MANAGER)
        restaurant = Restaurant.objects.get(name="Chez Fatou")
        self.assertEqual(restaurant.owner, user)
        self.assertEqual(restaurant.status, RestaurantStatus.PENDING)
        self.assertFalse(restaurant.is_accepting_orders)
        self.assertTrue(Employee.objects.filter(user=user, restaurant=restaurant, role=Role.MANAGER).exists())
        blocked = self.client.get("/gerant/")
        self.assertEqual(blocked.status_code, 302)
        self.assertIn("/demande-en-attente/", blocked.url)
        public = Client().get("/restaurants/")
        self.assertNotContains(public, "Chez Fatou")

    def test_admin_validation_unlocks_restaurant_profile(self):
        self.client.post(
            "/ouvrir-un-restaurant/",
            {
                "first_name": "Fatou",
                "last_name": "Diop",
                "email": "nouveau.gerant@test.local",
                "phone": "07000000",
                "password1": "Motdepasse123!",
                "password2": "Motdepasse123!",
                "restaurant_name": "Chez Fatou",
                "identity_type": "cni",
                "identity_document": identity_file(),
            },
        )
        restaurant = Restaurant.objects.get(name="Chez Fatou")
        admin = User.objects.create_user(
            email="admin@test.local",
            password="pass12345",
            first_name="Ada",
            last_name="Min",
            role=Role.PLATFORM_ADMIN,
            is_staff=True,
        )
        admin_client = Client()
        admin_client.force_login(admin)
        approve = admin_client.post(f"/admin-plateforme/restaurants/{restaurant.pk}/valider/")
        self.assertEqual(approve.status_code, 302)
        restaurant.refresh_from_db()
        self.assertEqual(restaurant.status, RestaurantStatus.ACTIVE)

        manager_client = Client()
        manager_client.force_login(User.objects.get(email="nouveau.gerant@test.local"))
        session = manager_client.session
        session["current_restaurant_id"] = restaurant.pk
        session.save()
        dashboard = manager_client.get("/gerant/")
        self.assertEqual(dashboard.status_code, 302)
        self.assertIn("/gerant/etablissement/", dashboard.url)
        profile = manager_client.post(
            "/gerant/etablissement/",
            {
                "name": "Chez Fatou",
                "phone": "07000000",
                "email": "nouveau.gerant@test.local",
                "address": "Rue 12",
                "city": "Abidjan",
                "delivery_fee": "0",
                "min_delivery_amount": "0",
                "estimated_prep_minutes": "25",
            },
        )
        self.assertEqual(profile.status_code, 302)
        restaurant.refresh_from_db()
        self.assertTrue(restaurant.is_profile_complete)
        opened = manager_client.get("/gerant/")
        self.assertEqual(opened.status_code, 200)

    def test_home_explains_both_paths(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Voir les restaurants")
        self.assertContains(response, "Ouvrir un restaurant")
        self.assertContains(response, 'href="/ouvrir-un-restaurant/"')
        self.assertNotContains(response, 'href="/gerant/"')
        self.assertNotContains(response, "QR")
        self.assertNotContains(response, "Scanner la table")
        self.assertNotContains(response, "Inscription")

    def test_validated_restaurant_appears_on_home(self):
        Restaurant.objects.create(
            name="Chez Validé",
            address="Rue 9",
            city="Abidjan",
            status=RestaurantStatus.ACTIVE,
            is_accepting_orders=False,
        )
        home = self.client.get("/")
        self.assertContains(home, "Chez Validé")
        listing = self.client.get("/restaurants/")
        self.assertContains(listing, "Chez Validé")

    def test_restaurant_page_explains_home_ordering(self):
        restaurant = Restaurant.objects.create(
            name="Chez Test",
            address="Rue 1",
            city="Abidjan",
            is_accepting_orders=True,
        )
        response = self.client.get(f"/restaurants/{restaurant.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "À emporter")
        self.assertContains(response, "Livraison")
        self.assertContains(response, "Vos plats")
        self.assertContains(response, "Votre panier est vide")
        self.assertNotContains(response, "QR")

    def test_restaurant_logo_appears_in_header(self):
        restaurant = Restaurant.objects.create(
            name="Chez Logo",
            address="Rue 1",
            city="Abidjan",
            phone="07000000",
            status=RestaurantStatus.ACTIVE,
            is_accepting_orders=True,
            logo=logo_file("logo.png"),
        )
        page = self.client.get(f"/restaurants/{restaurant.slug}/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, restaurant.logo.url)
        self.assertContains(page, "navbar-logo")
        self.assertContains(page, "resto-head-logo")
        manager = User.objects.create_user(
            email="logo.gerant@test.local",
            password="pass12345",
            first_name="Lo",
            last_name="Go",
            role=Role.MANAGER,
        )
        Employee.objects.create(user=manager, restaurant=restaurant, role=Role.MANAGER)
        self.client.force_login(manager)
        session = self.client.session
        session["current_restaurant_id"] = restaurant.pk
        session.save()
        dashboard = self.client.get("/gerant/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "navbar-logo")
        self.assertContains(dashboard, "sidebar-logo")

    def test_manager_home_redirects_to_dashboard(self):
        manager = User.objects.create_user(
            email="fatou@test.local",
            password="pass12345",
            first_name="Fatou",
            last_name="Diop",
            role=Role.MANAGER,
        )
        restaurant = Restaurant.objects.create(name="Chez Fatou", address="Rue 1", city="Abidjan")
        Employee.objects.create(user=manager, restaurant=restaurant, role=Role.MANAGER)
        self.client.force_login(manager)
        session = self.client.session
        session["current_restaurant_id"] = restaurant.pk
        session.save()
        response = self.client.get("/", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/gerant/", response.url)

    def test_platform_admin_has_workspace(self):
        admin = User.objects.create_user(
            email="admin@test.local",
            password="pass12345",
            first_name="Ada",
            last_name="Min",
            role=Role.PLATFORM_ADMIN,
            is_staff=True,
        )
        self.client.force_login(admin)
        dashboard = self.client.get("/admin-plateforme/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Tableau de bord plateforme")
        self.assertContains(dashboard, "Demandes à valider")
        restaurants = self.client.get("/admin-plateforme/restaurants/")
        self.assertEqual(restaurants.status_code, 200)
        self.assertContains(restaurants, "Super-admin")
        self.assertContains(restaurants, "En attente")
        users = self.client.get("/admin-plateforme/utilisateurs/")
        self.assertEqual(users.status_code, 200)
        orders = self.client.get("/admin-plateforme/commandes/")
        self.assertEqual(orders.status_code, 200)
