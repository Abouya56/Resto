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
    REQUEST = {
        "first_name": "Fatou",
        "last_name": "Diop",
        "email": "nouveau.gerant@test.local",
        "phone": "07000000",
        "restaurant_name": "Chez Fatou",
        "identity_type": "cni",
    }

    def _request(self):
        return self.client.post("/ouvrir-un-restaurant/", {**self.REQUEST, "identity_document": identity_file()})

    def _admin(self):
        admin = User.objects.create_user(
            email="admin@test.local", password="pass12345", first_name="Ada", last_name="Min",
            role=Role.PLATFORM_ADMIN, is_staff=True,
        )
        web = Client()
        web.force_login(admin)
        return web

    def test_request_creates_no_account_and_stays_pending(self):
        response = self._request()
        self.assertRedirects(response, "/demande-envoyee/", fetch_redirect_response=False)
        self.assertContains(self.client.get("/demande-envoyee/"), "Demande envoyée")
        # aucun compte, aucune connexion : le demandeur attend qu'on lui donne son accès
        self.assertFalse(User.objects.filter(email="nouveau.gerant@test.local").exists())
        restaurant = Restaurant.objects.get(name="Chez Fatou")
        self.assertIsNone(restaurant.owner)
        self.assertEqual(restaurant.status, RestaurantStatus.PENDING)
        self.assertEqual((restaurant.applicant_name, restaurant.applicant_email), ("Fatou Diop", "nouveau.gerant@test.local"))
        self.assertFalse(restaurant.is_accepting_orders)
        self.assertNotContains(Client().get("/restaurants/"), "Chez Fatou")
        self.assertFalse(Employee.objects.filter(restaurant=restaurant).exists())

    def test_request_form_has_no_password(self):
        page = self.client.get("/ouvrir-un-restaurant/")
        self.assertNotContains(page, "Mot de passe")
        self.assertNotContains(page, "password")

    def test_platform_gives_the_manager_account_on_validation(self):
        self._request()
        restaurant = Restaurant.objects.get(name="Chez Fatou")
        admin = self._admin()
        approve = admin.post(f"/admin-plateforme/restaurants/{restaurant.pk}/valider/", follow=True)
        restaurant.refresh_from_db()
        user = User.objects.get(email="nouveau.gerant@test.local")
        self.assertEqual((user.role, user.first_name, user.last_name), (Role.MANAGER, "Fatou", "Diop"))
        self.assertEqual(restaurant.owner, user)
        self.assertTrue(Employee.objects.filter(user=user, restaurant=restaurant, role=Role.MANAGER).exists())
        # identité validée, mais le restaurant reste fermé jusqu'au paiement de la licence
        self.assertEqual(restaurant.status, RestaurantStatus.UNPAID)
        # le mot de passe provisoire est montré une seule fois au super admin, et il marche
        text = " ".join(m.message for m in approve.context["messages"])
        self.assertIn("nouveau.gerant@test.local", text)
        password = text.split("mot de passe provisoire : ")[1].split(" ")[0]
        self.assertTrue(Client().login(email="nouveau.gerant@test.local", password=password))

    def test_manager_logs_in_after_payment_and_fills_the_profile(self):
        self._request()
        restaurant = Restaurant.objects.get(name="Chez Fatou")
        admin = self._admin()
        approve = admin.post(f"/admin-plateforme/restaurants/{restaurant.pk}/valider/", follow=True)
        text = " ".join(m.message for m in approve.context["messages"])
        password = text.split("mot de passe provisoire : ")[1].split(" ")[0]
        admin.post(f"/admin-plateforme/restaurants/{restaurant.pk}/licence/", {"months": "1"})
        restaurant.refresh_from_db()
        self.assertEqual(restaurant.status, RestaurantStatus.ACTIVE)

        manager_client = Client()
        self.assertTrue(manager_client.login(email="nouveau.gerant@test.local", password=password))
        session = manager_client.session
        session["current_restaurant_id"] = restaurant.pk
        session.save()
        dashboard = manager_client.get("/gerant/")
        self.assertEqual(dashboard.status_code, 302)
        self.assertIn("/gerant/etablissement/", dashboard.url)
        profile = manager_client.post(
            "/gerant/etablissement/",
            {
                "name": "Chez Fatou", "phone": "07000000", "email": "nouveau.gerant@test.local",
                "address": "Rue 12", "city": "Abidjan", "delivery_fee": "0", "min_delivery_amount": "0",
                "estimated_prep_minutes": "25",
            },
        )
        self.assertEqual(profile.status_code, 302)
        self.assertEqual(manager_client.get("/gerant/").status_code, 200)

    def test_unpaid_manager_sees_the_licence_page_after_validation(self):
        self._request()
        restaurant = Restaurant.objects.get(name="Chez Fatou")
        admin = self._admin()
        approve = admin.post(f"/admin-plateforme/restaurants/{restaurant.pk}/valider/", follow=True)
        password = " ".join(m.message for m in approve.context["messages"]).split("mot de passe provisoire : ")[1].split(" ")[0]
        web = Client()
        web.login(email="nouveau.gerant@test.local", password=password)
        session = web.session
        session["current_restaurant_id"] = restaurant.pk
        session.save()
        self.assertContains(web.get("/demande-en-attente/"), "Licence à payer")

    def test_email_already_used_is_refused(self):
        User.objects.create_user(email="nouveau.gerant@test.local", password="pass12345", first_name="X", last_name="Y")
        response = self._request()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Restaurant.objects.filter(name="Chez Fatou").exists())

    def test_rejected_request_creates_no_account(self):
        self._request()
        restaurant = Restaurant.objects.get(name="Chez Fatou")
        self._admin().post(f"/admin-plateforme/restaurants/{restaurant.pk}/refuser/", {"note": "Pièce illisible"})
        restaurant.refresh_from_db()
        self.assertEqual(restaurant.status, RestaurantStatus.REJECTED)
        self.assertFalse(User.objects.filter(email="nouveau.gerant@test.local").exists())

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
            is_accepting_orders=True,
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
        self.assertContains(response, "Plats")
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
        self.assertContains(dashboard, "Supervision")
        self.assertContains(dashboard, "Demandes à valider")
        restaurants = self.client.get("/admin-plateforme/restaurants/")
        self.assertEqual(restaurants.status_code, 200)
        self.assertContains(restaurants, "Espace super admin")
        self.assertContains(restaurants, "En attente")
        users = self.client.get("/admin-plateforme/utilisateurs/")
        self.assertEqual(users.status_code, 200)
        orders = self.client.get("/admin-plateforme/commandes/")
        self.assertEqual(orders.status_code, 200)


class EmployeeDeleteTests(TestCase):
    def setUp(self):
        self.restaurant = Restaurant.objects.create(name="Alpha", address="1 rue A", city="Abidjan")
        self.manager = User.objects.create_user(
            email="gerant@test.local", password="pass12345", first_name="Gé", last_name="Rant", role=Role.MANAGER
        )
        self.waiter = User.objects.create_user(
            email="serveur@test.local", password="pass12345", first_name="Ser", last_name="Veur", role=Role.RECEPTION
        )
        self.restaurant.owner = self.manager
        self.restaurant.save()
        self.manager_employee = Employee.objects.create(
            user=self.manager, restaurant=self.restaurant, role=Role.MANAGER
        )
        self.waiter_employee = Employee.objects.create(user=self.waiter, restaurant=self.restaurant, role=Role.RECEPTION)
        self.client.force_login(self.manager)
        session = self.client.session
        session["current_restaurant_id"] = self.restaurant.pk
        session.save()

    def test_manager_cannot_remove_an_employee(self):
        url = f"/gerant/employes/{self.waiter_employee.pk}/supprimer/"
        self.assertEqual(self.client.get(url).status_code, 302)  # pas de page de confirmation
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertTrue(Employee.objects.filter(pk=self.waiter_employee.pk).exists())
        page = self.client.get("/gerant/employes/")
        self.assertNotContains(page, "Retirer de l")
        self.assertNotContains(page, "Suspendre")

    def test_platform_admin_can_still_remove_an_employee(self):
        admin = User.objects.create_user(
            email="rm-admin@test.local", password="pass12345", first_name="A", last_name="D",
            role=Role.PLATFORM_ADMIN, is_staff=True,
        )
        web = Client()
        web.force_login(admin)
        session = web.session
        session["current_restaurant_id"] = self.restaurant.pk
        session.save()
        response = web.post(f"/gerant/employes/{self.waiter_employee.pk}/supprimer/")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Employee.objects.filter(pk=self.waiter_employee.pk).exists())

    def test_manager_cannot_remove_self(self):
        self.client.post(f"/gerant/employes/{self.manager_employee.pk}/supprimer/")
        self.assertTrue(Employee.objects.filter(pk=self.manager_employee.pk).exists())

    def test_manager_cannot_remove_other_restaurant_employee(self):
        other = Restaurant.objects.create(name="Beta", address="2 rue B", city="Abidjan")
        cook = User.objects.create_user(
            email="cuisto@test.local", password="pass12345", first_name="Cui", last_name="Sto", role=Role.RECEPTION
        )
        employee = Employee.objects.create(user=cook, restaurant=other, role=Role.RECEPTION)
        self.client.post(f"/gerant/employes/{employee.pk}/supprimer/")
        self.assertTrue(Employee.objects.filter(pk=employee.pk).exists())

    def test_non_manager_cannot_remove_employee(self):
        self.client.force_login(self.waiter)
        response = self.client.post(f"/gerant/employes/{self.manager_employee.pk}/supprimer/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Employee.objects.filter(pk=self.manager_employee.pk).exists())


class FormPagesRenderTests(TestCase):
    """Chaque formulaire du gérant s'affiche proprement, avec et sans image déjà enregistrée."""

    def setUp(self):
        from apps.inventory.models import StockItem
        from apps.menus.models import Category, Product
        from apps.tables.models import DiningTable

        self.restaurant = Restaurant.objects.create(
            name="Graya", address="Rue 1", city="Bobo", phone="70000000", logo=logo_file()
        )
        self.manager = User.objects.create_user(
            email="forms@test.local", password="pass12345", first_name="F", last_name="M", role=Role.MANAGER
        )
        self.employee = Employee.objects.create(user=self.manager, restaurant=self.restaurant, role=Role.MANAGER)
        self.category = Category.objects.create(restaurant=self.restaurant, name="Plats")
        self.product = Product.objects.create(
            restaurant=self.restaurant, category=self.category, name="Riz", price=2000, image=logo_file("riz.png")
        )
        self.table = DiningTable.objects.create(restaurant=self.restaurant, number="1")
        self.item = StockItem.objects.create(restaurant=self.restaurant, name="Huile", unit="L")
        self.client.force_login(self.manager)
        session = self.client.session
        session["current_restaurant_id"] = self.restaurant.pk
        session.save()

    def test_every_manager_form_renders_with_the_new_layout(self):
        urls = [
            "/gerant/etablissement/",
            "/gerant/categories/nouvelle/",
            f"/gerant/categories/{self.category.pk}/",
            "/gerant/produits/nouveau/",
            f"/gerant/produits/{self.product.pk}/",
            "/gerant/employes/nouveau/",
            f"/gerant/employes/{self.employee.pk}/",
            "/gerant/tables/nouvelle/",
            f"/gerant/tables/{self.table.pk}/",
            "/gerant/depenses/nouvelle/",
            "/gerant/stocks/nouveau/",
            f"/gerant/stocks/{self.item.pk}/",
            "/profil/",
        ]
        for url in urls:
            with self.subTest(url=url):
                page = self.client.get(url)
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, 'class="ff ')
                self.assertNotContains(page, "Actuellement")  # plus le rendu brut de Django

    def test_restaurant_form_shows_sections_previews_and_switch(self):
        page = self.client.get("/gerant/etablissement/")
        self.assertContains(page, "Contact et adresse")
        self.assertContains(page, "Commandes et livraison")
        self.assertContains(page, self.restaurant.logo.url)
        self.assertContains(page, 'name="logo-clear"')
        self.assertNotContains(page, "is_accepting_orders")  # l'interrupteur est sur le tableau de bord
        self.assertContains(page, "FCFA")
        product = self.client.get(f"/gerant/produits/{self.product.pk}/")
        self.assertContains(product, self.product.image.url)
        self.assertContains(product, "relier ce plat au stock")

    def test_restaurant_form_still_saves_and_shows_errors(self):
        data = {
            "name": "Graya",
            "phone": "70000000",
            "address": "Rue 2",
            "city": "Bobo",
            "delivery_fee": "500",
            "min_delivery_amount": "0",
            "estimated_prep_minutes": "20",
            "is_accepting_orders": "on",
        }
        self.assertEqual(self.client.post("/gerant/etablissement/", data).status_code, 302)
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.address, "Rue 2")
        self.assertTrue(self.restaurant.logo)  # logo gardé si on n'en envoie pas de nouveau
        errors = self.client.post("/gerant/etablissement/", {**data, "city": ""})
        self.assertContains(errors, "corrigez les champs en rouge")
        self.assertContains(errors, "ff-error")

    def test_password_reset_pages_render(self):
        from django.test import Client

        page = Client().get("/mot-de-passe-oublie/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'class="ff ')


class TeamPageTests(TestCase):
    def setUp(self):
        EmployeeDeleteTests.setUp(self)

    def test_team_grouped_by_role_with_missing_hints(self):
        page = self.client.get("/gerant/employes/")
        groups = {g["title"]: g for g in page.context["groups"]}
        self.assertEqual([e.user for e in groups["Réception"]["members"]], [self.waiter])
        self.assertEqual(groups["Réception"]["missing"], "")
        self.assertContains(page, "Propriétaire")

    def test_manager_cannot_suspend_anyone(self):
        url = f"/gerant/employes/{self.waiter_employee.pk}/statut/"
        self.assertEqual(self.client.post(url).status_code, 302)
        self.waiter_employee.refresh_from_db()
        self.assertTrue(self.waiter_employee.is_active)  # la réception reste au travail
        page = self.client.get("/gerant/employes/")
        self.assertNotContains(page, "Suspendre")
        self.assertNotContains(page, "bi-three-dots")

    def test_manager_cannot_suspend_through_the_edit_form(self):
        url = f"/gerant/employes/{self.waiter_employee.pk}/"
        self.client.post(url, {"email": self.waiter.email, "first_name": "Ser", "last_name": "Veur", "status": "inactive"})
        self.waiter_employee.refresh_from_db()
        self.assertTrue(self.waiter_employee.is_active)

    def test_platform_admin_can_suspend_and_reactivate(self):
        admin = User.objects.create_user(
            email="sp-admin@test.local", password="pass12345", first_name="A", last_name="D",
            role=Role.PLATFORM_ADMIN, is_staff=True,
        )
        web = Client()
        web.force_login(admin)
        session = web.session
        session["current_restaurant_id"] = self.restaurant.pk
        session.save()
        url = f"/gerant/employes/{self.waiter_employee.pk}/statut/"
        web.post(url)
        self.waiter_employee.refresh_from_db()
        self.assertFalse(self.waiter_employee.is_active)
        web.post(url)
        self.waiter_employee.refresh_from_db()
        self.assertTrue(self.waiter_employee.is_active)

    def test_cannot_suspend_self_or_owner(self):
        self.client.post(f"/gerant/employes/{self.manager_employee.pk}/statut/")
        self.manager_employee.refresh_from_db()
        self.assertTrue(self.manager_employee.is_active)


class RestaurantLogoTests(TestCase):
    def _look(self, name):
        from types import SimpleNamespace

        from apps.core.templatetags.resto import restaurant_look

        return restaurant_look(SimpleNamespace(name=name))

    def test_automatic_logo_uses_initials_and_a_stable_colour(self):
        self.assertEqual(self._look("Chez Maman")["initials"], "CM")
        self.assertEqual(self._look("Le Baobab")["initials"], "B")  # « Le » ne compte pas
        self.assertEqual(self._look("LA GRAYA")["initials"], "G")
        self.assertEqual(self._look("Chez Awa KYC")["initials"], "CA")
        self.assertEqual(self._look("Café de l'Étoile")["initials"], "CE")  # accents et apostrophes
        self.assertEqual(self._look("Chez Maman"), self._look("Chez Maman"))  # toujours la même couleur
        self.assertEqual(self._look("")["initials"], "R")

    def test_every_restaurant_shows_a_logo_everywhere(self):
        plain = Restaurant.objects.create(
            name="Chez Maman", address="x", city="Y", status=RestaurantStatus.ACTIVE, is_accepting_orders=True
        )
        with_logo = Restaurant.objects.create(
            name="Avec Logo", address="x", city="Y", status=RestaurantStatus.ACTIVE, logo=logo_file("avec.png")
        )
        listing = self.client.get("/restaurants/")
        self.assertContains(listing, "rl rl-", count=1)  # un logo automatique : celui de Chez Maman
        self.assertContains(listing, with_logo.logo.url)
        page = self.client.get(f"/restaurants/{plain.slug}/")
        self.assertContains(page, "resto-head-logo")
        self.assertContains(page, ">CM<")
        self.assertContains(page, "navbar-logo")  # même dans l'en-tête du site
        manager = User.objects.create_user(
            email="logo2@test.local", password="pass12345", first_name="L", last_name="M", role=Role.MANAGER
        )
        Employee.objects.create(user=manager, restaurant=plain, role=Role.MANAGER)
        self.client.force_login(manager)
        session = self.client.session
        session["current_restaurant_id"] = plain.pk
        session.save()
        dashboard = self.client.get("/gerant/")
        self.assertContains(dashboard, "sidebar-logo")
        self.assertContains(dashboard, ">CM<")
        form = self.client.get("/gerant/etablissement/")
        self.assertContains(form, "ff-logo-fb")
        self.assertContains(form, "Sans logo, un logo avec vos initiales")


class RestaurantSearchTests(TestCase):
    def setUp(self):
        for name in ("Café du Coin", "Chez Awa", "La Graya", "La Grande Table"):
            Restaurant.objects.create(name=name, address="x", city="Bobo", status=RestaurantStatus.ACTIVE)

    def names(self, **params):
        page = Client().get("/restaurants/", params)
        return [r.name for r in page.context["restaurants"]], [r.name for r in page.context["suggestions"]]

    def test_search_ignores_case_and_accents(self):
        for query in ("CAFE", "café DU", "cafÉ"):
            self.assertEqual(self.names(q=query)[0], ["Café du Coin"], query)

    def test_similar_names_are_proposed(self):
        found, suggestions = self.names(q="Graya")
        self.assertEqual(found, ["La Graya"])
        found, suggestions = self.names(q="grayya")  # faute de frappe : rien ne contient ce mot
        self.assertEqual(found, [])
        self.assertEqual(suggestions[0], "La Graya")

    def test_unrelated_search_proposes_nothing(self):
        self.assertEqual(self.names(q="zzzzzz"), ([], []))

    def test_city_search_accepts_a_longer_or_shorter_name(self):
        for city in ("bobo", "BOBO Dioulasso"):
            found, _ = self.names(q="graya", city=city)
            self.assertEqual(found, ["La Graya"], city)
        self.assertEqual(self.names(q="graya", city="Ouaga")[0], [])


class OpenCloseTests(TestCase):
    """Le gérant ouvre et ferme son restaurant : fermé, il disparaît pour les clients."""

    def setUp(self):
        self.resto = Restaurant.objects.create(
            name="Chez Ouvert", address="x", city="Bobo", status=RestaurantStatus.ACTIVE
        )
        self.manager = User.objects.create_user(
            email="open@test.local", password="pass12345", first_name="G", last_name="G", role=Role.MANAGER
        )
        Employee.objects.create(user=self.manager, restaurant=self.resto, role=Role.MANAGER)
        self.web = Client()
        self.web.force_login(self.manager)
        session = self.web.session
        session["current_restaurant_id"] = self.resto.pk
        session.save()

    def test_manager_closes_then_reopens(self):
        self.assertContains(Client().get("/restaurants/"), "Chez Ouvert")
        self.web.post("/gerant/ouverture/")
        self.resto.refresh_from_db()
        self.assertFalse(self.resto.is_accepting_orders)
        self.assertNotContains(Client().get("/restaurants/"), "Chez Ouvert")
        self.assertNotContains(Client().get("/"), "Chez Ouvert")
        closed = Client().get(f"/restaurants/{self.resto.slug}/")
        self.assertContains(closed, "Fermé pour le moment")
        self.assertNotContains(closed, "Ajouter")
        self.assertContains(self.web.get("/gerant/"), "Ouvrir le restaurant")
        self.web.post("/gerant/ouverture/")
        self.assertContains(Client().get("/restaurants/"), "Chez Ouvert")

    def test_only_the_manager_can_switch_it(self):
        reception = User.objects.create_user(
            email="rr@test.local", password="pass12345", first_name="R", last_name="R", role=Role.RECEPTION
        )
        Employee.objects.create(user=reception, restaurant=self.resto, role=Role.RECEPTION)
        web = Client()
        web.force_login(reception)
        session = web.session
        session["current_restaurant_id"] = self.resto.pk
        session.save()
        self.assertEqual(web.post("/gerant/ouverture/").status_code, 403)
        self.assertEqual(Client().post("/gerant/ouverture/").status_code, 302)  # anonyme : renvoyé vers la connexion
        self.resto.refresh_from_db()
        self.assertTrue(self.resto.is_accepting_orders)


class LicenseTests(TestCase):
    """Celui qui paye est ouvert ; celui qui ne paye pas reste fermé."""

    def setUp(self):
        from apps.restaurants.licenses import expire_licenses, license_info, record_license_payment

        self.expire, self.info, self.pay = expire_licenses, license_info, record_license_payment
        self.admin = User.objects.create_user(
            email="lic@test.local", password="pass12345", first_name="A", last_name="D",
            role=Role.PLATFORM_ADMIN, is_staff=True,
        )
        self.resto = Restaurant.objects.create(
            name="Chez Licence", address="x", city="Bobo", status=RestaurantStatus.UNPAID, is_accepting_orders=False
        )

    def test_unpaid_restaurant_is_invisible_to_customers(self):
        self.assertNotContains(Client().get("/restaurants/"), "Chez Licence")
        self.assertEqual(Client().get(f"/restaurants/{self.resto.slug}/").status_code, 404)

    def test_payment_opens_the_restaurant(self):
        from datetime import timedelta

        from django.utils import timezone

        payment = self.pay(self.resto, 3, self.admin, amount=30000, note="mobile money")
        self.resto.refresh_from_db()
        self.assertEqual(self.resto.status, RestaurantStatus.ACTIVE)
        self.assertTrue(self.resto.is_accepting_orders)
        self.assertEqual(self.resto.license_until, timezone.localdate() + timedelta(days=90))
        self.assertEqual(payment.amount, 30000)
        self.assertContains(Client().get("/restaurants/"), "Chez Licence")

    def test_paying_early_adds_to_the_remaining_time(self):
        from datetime import timedelta

        from django.utils import timezone

        self.pay(self.resto, 1, self.admin)
        self.pay(self.resto, 1, self.admin)
        self.resto.refresh_from_db()
        self.assertEqual(self.resto.license_until, timezone.localdate() + timedelta(days=60))

    def test_expired_license_closes_the_restaurant(self):
        from datetime import timedelta

        from django.utils import timezone

        self.pay(self.resto, 1, self.admin)
        Restaurant.objects.filter(pk=self.resto.pk).update(license_until=timezone.localdate() - timedelta(days=1))
        self.assertEqual(self.expire(), 1)
        self.resto.refresh_from_db()
        self.assertEqual(self.resto.status, RestaurantStatus.UNPAID)
        self.assertFalse(self.resto.is_accepting_orders)
        self.assertNotContains(Client().get("/restaurants/"), "Chez Licence")
        self.assertEqual(self.info(self.resto)["state"], "unpaid")

    def test_restaurant_without_a_date_is_never_closed(self):
        free = Restaurant.objects.create(name="Offert", address="x", city="Y", status=RestaurantStatus.ACTIVE)
        self.assertEqual(self.expire(), 0)
        free.refresh_from_db()
        self.assertEqual(free.status, RestaurantStatus.ACTIVE)
        self.assertEqual(self.info(free)["state"], "free")

    def test_admin_records_the_payment_from_the_dossier(self):
        web = Client()
        web.force_login(self.admin)
        page = web.get(f"/admin-plateforme/restaurants/{self.resto.pk}/")
        self.assertContains(page, "Enregistrer le paiement et ouvrir")
        web.post(f"/admin-plateforme/restaurants/{self.resto.pk}/licence/", {"months": "6", "amount": "60000"})
        self.resto.refresh_from_db()
        self.assertEqual(self.resto.status, RestaurantStatus.ACTIVE)
        self.assertEqual(self.resto.license_payments.get().months, 6)
        bad = web.post(f"/admin-plateforme/restaurants/{self.resto.pk}/licence/", {"months": "7"})
        self.assertEqual(self.resto.license_payments.count(), 1)  # durée inconnue : refusée

    def test_manager_cannot_record_a_payment(self):
        manager = User.objects.create_user(
            email="lm@test.local", password="pass12345", first_name="M", last_name="M", role=Role.MANAGER
        )
        Employee.objects.create(user=manager, restaurant=self.resto, role=Role.MANAGER)
        web = Client()
        web.force_login(manager)
        response = web.post(f"/admin-plateforme/restaurants/{self.resto.pk}/licence/", {"months": "12"})
        self.assertIn(response.status_code, (302, 403))
        self.resto.refresh_from_db()
        self.assertEqual(self.resto.status, RestaurantStatus.UNPAID)

    def test_unpaid_manager_sees_the_licence_message(self):
        manager = User.objects.create_user(
            email="lm2@test.local", password="pass12345", first_name="M", last_name="M", role=Role.MANAGER
        )
        Employee.objects.create(user=manager, restaurant=self.resto, role=Role.MANAGER)
        web = Client()
        web.force_login(manager)
        session = web.session
        session["current_restaurant_id"] = self.resto.pk
        session.save()
        self.assertEqual(web.get("/gerant/").status_code, 302)
        self.assertContains(web.get("/demande-en-attente/"), "Licence à payer")
