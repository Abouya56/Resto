from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from PIL import Image

from apps.core.models import SiteSettings
from apps.restaurants.models import Employee, Restaurant, RestaurantStatus
from apps.users.models import User
from apps.users.roles import Role

FORM = {
    "banner_text": "",
    "hero_kicker": "Commande depuis chez vous",
    "hero_title": "Les restaurants,\nchez vous.",
    "hero_lead": "Choisissez un restaurant et commandez.",
    "hero_button_label": "Voir les restaurants",
    "restaurants_kicker": "Près de chez vous",
    "restaurants_title": "Restaurants ouverts",
    "closing_title": "Vous tenez un resto ?",
    "closing_text": "Une demande simple.",
    "closing_button_label": "Ouvrir mon restaurant",
}


def photo(width=1600, height=900, name="couverture.jpg"):
    buffer = BytesIO()
    Image.new("RGB", (width, height), (200, 120, 40)).save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


class HomeSettingsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="root@test.local",
            password="pass12345",
            first_name="Ada",
            last_name="Min",
            role=Role.PLATFORM_ADMIN,
            is_staff=True,
        )
        self.admin_client = Client()
        self.admin_client.force_login(self.admin)
        self.url = "/admin-plateforme/accueil/"

    def test_home_works_with_default_content(self):
        page = Client().get("/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Les restaurants,<br>chez vous.")
        self.assertContains(page, "img/hero-salle.jpg")
        self.assertNotContains(page, "home-banner")

    def test_super_admin_changes_texts_and_banner(self):
        data = {**FORM, "hero_title": "Mangez bien\nà Abidjan", "banner_text": "Fermé lundi 20 octobre"}
        response = self.admin_client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        page = Client().get("/")
        self.assertContains(page, "Mangez bien<br>à Abidjan")
        self.assertContains(page, "Fermé lundi 20 octobre")
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_super_admin_uploads_then_resets_cover(self):
        response = self.admin_client.post(self.url, {**FORM, "hero_image": photo()})
        self.assertEqual(response.status_code, 302)
        site = SiteSettings.load()
        self.assertTrue(site.hero_image)
        page = Client().get("/")
        self.assertContains(page, site.hero_image.url)
        self.assertNotContains(page, "img/hero-salle.jpg")

        self.admin_client.post(self.url, {**FORM, "hero_image-clear": "on"})
        site.refresh_from_db()
        self.assertFalse(site.hero_image)
        self.assertContains(Client().get("/"), "img/hero-salle.jpg")

    def test_super_admin_sets_the_site_logo_and_name(self):
        page = Client().get("/")
        self.assertNotContains(page, "navbar-logo-site")
        self.assertContains(page, "Resto")
        logo = photo(width=300, height=300, name="logo.jpg")
        response = self.admin_client.post(self.url, {**FORM, "logo": logo, "site_name": "Mangeoir"})
        self.assertEqual(response.status_code, 302)
        site = SiteSettings.load()
        self.assertTrue(site.logo)
        page = Client().get("/")
        self.assertContains(page, "navbar-logo-site")
        self.assertContains(page, site.logo.url)  # en-tête et onglet du navigateur
        self.assertContains(page, "Mangeoir")
        self.admin_client.post(self.url, {**FORM, "logo-clear": "on", "site_name": ""})
        site.refresh_from_db()
        self.assertFalse(site.logo)
        self.assertNotContains(Client().get("/"), "navbar-logo-site")
        self.assertContains(Client().get("/"), "Resto")

    def test_only_platform_admin_reaches_the_logo_settings(self):
        manager = User.objects.create_user(email="m@test.local", password="pass12345", role=Role.MANAGER)
        client = Client()
        client.force_login(manager)
        self.assertEqual(client.get(self.url).status_code, 403)

    def test_rejects_small_or_wrong_images(self):
        small = self.admin_client.post(self.url, {**FORM, "hero_image": photo(width=600, height=400)})
        self.assertContains(small, "Image trop petite")
        fake = SimpleUploadedFile("x.jpg", b"pas une image", content_type="image/jpeg")
        self.assertContains(self.admin_client.post(self.url, {**FORM, "hero_image": fake}), "text-danger")
        self.assertFalse(SiteSettings.load().hero_image)

    def test_empty_title_is_refused(self):
        response = self.admin_client.post(self.url, {**FORM, "hero_title": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SiteSettings.load().hero_title, "Les restaurants,\nchez vous.")

    def test_only_super_admin_can_edit(self):
        restaurant = Restaurant.objects.create(name="Alpha", address="x", city="Y", status=RestaurantStatus.ACTIVE)
        manager = User.objects.create_user(
            email="g@test.local", password="pass12345", first_name="G", last_name="G", role=Role.MANAGER
        )
        Employee.objects.create(user=manager, restaurant=restaurant, role=Role.MANAGER)
        client = Client()
        client.force_login(manager)
        self.assertEqual(client.get(self.url).status_code, 403)
        self.assertEqual(client.post(self.url, {**FORM, "hero_title": "Piraté"}).status_code, 403)
        self.assertEqual(Client().get(self.url).status_code, 302)  # anonyme : page de connexion
        self.assertNotEqual(SiteSettings.load().hero_title, "Piraté")

    def test_admin_can_preview_home_as_visitor(self):
        self.assertEqual(self.admin_client.get("/").status_code, 302)  # va à son tableau de bord
        preview = self.admin_client.get("/?apercu=1")
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "Modifier la page d'accueil")
        self.assertNotContains(Client().get("/?apercu=1"), "Modifier la page d'accueil")

    def test_settings_page_and_sidebar_link(self):
        page = self.admin_client.get(self.url)
        self.assertContains(page, "Photo de couverture")
        self.assertContains(page, "Bandeau d&#x27;annonce")
        self.assertContains(self.admin_client.get("/admin-plateforme/"), self.url)


class PlatformUserEditTests(TestCase):
    """Le super admin corrige un compte et peut lui donner un nouveau mot de passe."""

    def setUp(self):
        self.admin = User.objects.create_user(
            email="boss@test.local", password="pass12345", first_name="Boss", last_name="Admin",
            role=Role.PLATFORM_ADMIN, is_staff=True,
        )
        self.person = User.objects.create_user(
            email="awa@test.local", password="ancien-mdp-1", first_name="Awa", last_name="Kone", role=Role.CUSTOMER,
        )
        self.web = Client()
        self.web.force_login(self.admin)
        self.url = f"/admin-plateforme/utilisateurs/{self.person.pk}/"

    def test_list_links_to_the_edit_page(self):
        self.assertContains(self.web.get("/admin-plateforme/utilisateurs/"), self.url)

    def test_admin_edits_the_information(self):
        response = self.web.post(
            self.url,
            {"action": "profile", "first_name": "Awa", "last_name": "Traore", "email": "NEW@test.local",
             "phone": "70112233", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.person.refresh_from_db()
        self.assertEqual((self.person.last_name, self.person.email, self.person.phone), ("Traore", "new@test.local", "70112233"))

    def test_email_must_stay_unique(self):
        response = self.web.post(
            self.url,
            {"action": "profile", "first_name": "Awa", "last_name": "Kone", "email": "boss@test.local", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.person.refresh_from_db()
        self.assertEqual(self.person.email, "awa@test.local")

    def test_admin_can_deactivate_someone_but_not_himself(self):
        self.web.post(self.url, {"action": "profile", "first_name": "Awa", "last_name": "Kone", "email": "awa@test.local"})
        self.person.refresh_from_db()
        self.assertFalse(self.person.is_active)
        own = self.web.post(
            f"/admin-plateforme/utilisateurs/{self.admin.pk}/",
            {"action": "profile", "first_name": "Boss", "last_name": "Admin", "email": "boss@test.local"},
        )
        self.assertEqual(own.status_code, 200)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_admin_sets_a_new_password(self):
        self.web.post(self.url, {"action": "password", "new_password1": "Nouveau-Mdp-2026", "new_password2": "Nouveau-Mdp-2026"})
        self.person.refresh_from_db()
        self.assertTrue(self.person.check_password("Nouveau-Mdp-2026"))
        self.assertTrue(Client().login(email="awa@test.local", password="Nouveau-Mdp-2026"))

    def test_simple_password_given_by_the_admin_works(self):
        self.web.post(self.url, {"action": "password", "new_password1": "H12340", "new_password2": "H12340"})
        self.assertTrue(Client().login(email="awa@test.local", password="H12340"))

    def test_weak_or_mismatched_password_is_refused(self):
        self.web.post(self.url, {"action": "password", "new_password1": "Abcdefgh-1", "new_password2": "autre"})
        self.web.post(self.url, {"action": "password", "new_password1": "12345", "new_password2": "12345"})
        self.person.refresh_from_db()
        self.assertTrue(self.person.check_password("ancien-mdp-1"))

    def test_only_the_platform_admin_reaches_it(self):
        self.assertEqual(Client().get(self.url).status_code, 302)
        other = Client()
        other.force_login(self.person)
        self.assertEqual(other.get(self.url).status_code, 403)
        self.assertEqual(other.post(self.url, {"action": "password", "new_password1": "x", "new_password2": "x"}).status_code, 403)


class PlatformActivityTests(TestCase):
    """Le super admin suit l'activité de chaque restaurant, pas les commandes des clients."""

    def test_activity_is_grouped_by_restaurant_without_customer_details(self):
        from decimal import Decimal

        from apps.menus.models import Category, Product
        from apps.orders.models import Cart, OrderType
        from apps.orders.services import add_to_cart, checkout_cart

        resto = Restaurant.objects.create(name="Chez Activite", address="x", city="Bobo", status=RestaurantStatus.ACTIVE)
        product = Product.objects.create(
            restaurant=resto, category=Category.objects.create(restaurant=resto, name="P"), name="Riz", price=Decimal("2000")
        )
        cart = Cart.objects.create(restaurant=resto, order_type=OrderType.TAKEAWAY, session_key="s")
        add_to_cart(cart, product)
        checkout_cart(cart, contact={"first_name": "Moussa", "phone": "70998877"})
        admin = User.objects.create_user(
            email="adm@test.local", password="pass12345", first_name="A", last_name="D", role=Role.PLATFORM_ADMIN, is_staff=True
        )
        web = Client()
        web.force_login(admin)
        page = web.get("/admin-plateforme/commandes/")
        self.assertEqual(page.status_code, 200)
        row = next(r for r in page.context["rows"] if r["restaurant"] == resto)
        self.assertEqual((row["total"], row["today"], row["open"]), (1, 1, 1))
        self.assertNotContains(page, "Moussa")
        self.assertNotContains(page, "70998877")
        self.assertNotContains(web.get("/admin-plateforme/"), "Moussa")


class AdminGivenPasswordTests(TestCase):
    def test_person_must_choose_their_own_after_the_admin_sets_one(self):
        admin = User.objects.create_user(
            email="boss@test.local", password="pass12345", first_name="B", last_name="A", role=Role.PLATFORM_ADMIN, is_staff=True
        )
        person = User.objects.create_user(email="awa@test.local", password="x", first_name="A", last_name="K", role=Role.MANAGER)
        web = Client()
        web.force_login(admin)
        web.post(f"/admin-plateforme/utilisateurs/{person.pk}/", {"action": "password", "new_password1": "H12340", "new_password2": "H12340"})
        person.refresh_from_db()
        self.assertTrue(person.must_change_password)
        web.post(f"/admin-plateforme/utilisateurs/{admin.pk}/", {"action": "password", "new_password1": "Boss-2026", "new_password2": "Boss-2026"})
        admin.refresh_from_db()
        self.assertFalse(admin.must_change_password)  # son propre compte : pas de détour
