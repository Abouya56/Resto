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


class CategoryPageTests(TestCase):
    def setUp(self):
        from django.test import Client

        from apps.restaurants.models import Employee, Restaurant
        from apps.users.models import User
        from apps.users.roles import Role

        self.resto = Restaurant.objects.create(name="Carte", address="x", city="Y")
        manager = User.objects.create_user(
            email="carte@test.local", password="pass12345", first_name="C", last_name="M", role=Role.MANAGER
        )
        Employee.objects.create(user=manager, restaurant=self.resto, role=Role.MANAGER)
        self.drinks = Category.objects.create(restaurant=self.resto, name="Boissons", sort_order=0)
        self.grill = Category.objects.create(restaurant=self.resto, name="Grillades", sort_order=0)
        self.empty = Category.objects.create(restaurant=self.resto, name="Desserts", sort_order=5)
        Product.objects.create(restaurant=self.resto, category=self.grill, name="Poulet", price=3000)
        Product.objects.create(restaurant=self.resto, category=self.drinks, name="Bissap", price=500)
        Product.objects.create(restaurant=self.resto, category=self.drinks, name="Coca", price=600, is_available=False)
        self.web = Client()
        self.web.force_login(manager)
        session = self.web.session
        session["current_restaurant_id"] = self.resto.pk
        session.save()

    def names(self):
        page = self.web.get("/gerant/categories/")
        return [c.name for c in page.context["categories"]], page

    def test_list_shows_menu_order_counts_and_empty_warning(self):
        names, page = self.names()
        self.assertEqual(names, ["Boissons", "Grillades", "Desserts"])
        drinks = page.context["categories"][0]
        self.assertEqual((len(drinks.dishes), drinks.visible_count), (2, 1))
        self.assertContains(page, "Vide : n'apparaît pas sur la carte.")
        self.assertEqual(page.context["shown_count"], 2)

    def test_arrows_reorder_and_menu_follows(self):
        self.web.post(f"/gerant/categories/{self.grill.pk}/deplacer/", {"direction": "up"})
        names, _ = self.names()
        self.assertEqual(names, ["Grillades", "Boissons", "Desserts"])
        self.web.post(f"/gerant/categories/{self.grill.pk}/deplacer/", {"direction": "up"})  # déjà en haut
        self.assertEqual(self.names()[0], ["Grillades", "Boissons", "Desserts"])
        menu = self.client.get(f"/restaurants/{self.resto.slug}/")
        content = menu.content.decode()
        self.assertLess(content.index("Grillades"), content.index("Boissons"))

    def test_toggle_hides_category_from_customers(self):
        self.web.post(f"/gerant/categories/{self.grill.pk}/visibilite/")
        self.grill.refresh_from_db()
        self.assertFalse(self.grill.is_active)
        self.assertNotContains(self.client.get(f"/restaurants/{self.resto.slug}/"), "Poulet")

    def test_only_empty_categories_can_be_deleted(self):
        self.web.post(f"/gerant/categories/{self.drinks.pk}/supprimer/")
        self.assertTrue(Category.objects.filter(pk=self.drinks.pk).exists())
        self.web.post(f"/gerant/categories/{self.empty.pk}/supprimer/")
        self.assertFalse(Category.objects.filter(pk=self.empty.pk).exists())

    def test_new_category_goes_last_and_form_has_no_order_number(self):
        page = self.web.get("/gerant/categories/nouvelle/")
        self.assertNotContains(page, 'name="sort_order"')
        self.web.post("/gerant/categories/nouvelle/", {"name": "Entrées", "is_active": "on"})
        self.assertEqual(self.names()[0][-1], "Entrées")

    def test_see_dishes_of_one_category(self):
        page = self.web.get(f"/gerant/produits/?categorie={self.drinks.pk}")
        self.assertEqual({p.name for p in page.context["products"]}, {"Bissap", "Coca"})


class ProductPageTests(TestCase):
    """Réutilise la carte de CategoryPageTests (Boissons, Grillades, Desserts)."""

    setUp = CategoryPageTests.setUp

    def test_list_grouped_by_category_with_filters(self):
        page = self.web.get("/gerant/produits/")
        self.assertEqual([g["category"].name for g in page.context["groups"]], ["Boissons", "Grillades"])
        counts = {f["key"]: f["count"] for f in page.context["filters"]}
        self.assertEqual(counts["indisponibles"], 1)
        self.assertEqual(counts["sans-photo"], 3)
        self.assertEqual(counts["non-relies"], 3)
        unavailable = self.web.get("/gerant/produits/?etat=indisponibles")
        self.assertEqual([p.name for p in unavailable.context["products"]], ["Coca"])
        found = self.web.get("/gerant/produits/?q=poul")
        self.assertEqual([p.name for p in found.context["products"]], ["Poulet"])

    def test_toggle_returns_to_same_filtered_page(self):
        coca = Product.objects.get(name="Coca")
        response = self.web.post(
            f"/gerant/produits/{coca.pk}/disponibilite/", {"next": "/gerant/produits/?etat=indisponibles"}
        )
        self.assertRedirects(
            response, f"/gerant/produits/?etat=indisponibles#plat-{coca.pk}", fetch_redirect_response=False
        )
        coca.refresh_from_db()
        self.assertTrue(coca.is_available)
        evil = self.web.post(f"/gerant/produits/{coca.pk}/disponibilite/", {"next": "https://pirate.example/"})
        self.assertTrue(evil.url.startswith("/gerant/produits/"))

    def test_retired_dishes_can_still_be_found(self):
        Product.objects.filter(name="Poulet").update(is_active=False)
        page = self.web.get("/gerant/produits/")
        self.assertNotIn("Poulet", [p.name for p in page.context["products"]])
        retired = self.web.get("/gerant/produits/?etat=retires")
        self.assertEqual([p.name for p in retired.context["products"]], ["Poulet"])

    def test_sales_of_the_week_and_stock_left(self):
        from decimal import Decimal

        from apps.inventory.models import RecipeIngredient, StockItem
        from apps.orders.models import Cart, OrderType
        from apps.orders.services import add_to_cart, checkout_cart

        bissap = Product.objects.get(name="Bissap")
        cart = Cart.objects.create(restaurant=self.resto, order_type=OrderType.TAKEAWAY, session_key="v")
        add_to_cart(cart, bissap, 3)
        checkout_cart(cart, contact={"first_name": "A", "last_name": "B", "phone": "70000000"})
        bottles = StockItem.objects.create(restaurant=self.resto, name="Bissap", unit="bouteille", quantity=12)
        RecipeIngredient.objects.create(product=bissap, stock_item=bottles, quantity=Decimal("1"))
        page = self.web.get("/gerant/produits/")
        row = next(p for p in page.context["products"] if p.name == "Bissap")
        self.assertEqual(row.sold_week, 3)
        self.assertEqual(row.enough_for, 12)
        self.assertContains(page, "Encore 12")


class DishPhotoTests(TestCase):
    setUp = CategoryPageTests.setUp

    def _look(self, name, category):
        from types import SimpleNamespace

        from apps.core.templatetags.resto import dish_look

        return dish_look(SimpleNamespace(name=name, category=SimpleNamespace(name=category)))["tone"]

    def test_illustration_matches_the_kind_of_dish(self):
        self.assertEqual(self._look("Brakina", "Boissons"), "drink")
        self.assertEqual(self._look("Eau minérale", "Boissons"), "drink")
        self.assertEqual(self._look("Coca cola", "Boissons"), "drink")
        self.assertEqual(self._look("Salade de fruits", "Desserts"), "sweet")  # dessert avant accompagnement
        self.assertEqual(self._look("Dégué", "Desserts"), "sweet")
        self.assertEqual(self._look("Poulet bicyclette braisé", "Grillades"), "grill")
        self.assertEqual(self._look("Brochettes de bœuf", "Grillades"), "grill")
        self.assertEqual(self._look("Alloco", "Accompagnements"), "side")
        self.assertEqual(self._look("Riz blanc", "Accompagnements"), "side")  # d'après la catégorie
        self.assertEqual(self._look("Garba", "Nourriture Ivorien"), "main")
        self.assertEqual(self._look("Atiéké", "Nourriture Ivorien"), "main")

    def test_every_dish_shows_an_image_on_every_page(self):
        poulet = Product.objects.get(name="Poulet")  # aucune photo
        bissap = Product.objects.get(name="Bissap")
        bissap.image.name = "products/exemple.jpg"
        bissap.save()
        menu = self.client.get(f"/restaurants/{self.resto.slug}/")
        self.assertContains(menu, "dish-ph-grill")  # Poulet : illustration
        self.assertContains(menu, "products/exemple.jpg")  # Bissap : sa vraie photo
        plats = self.web.get("/gerant/produits/")
        self.assertContains(plats, "dish-ph-grill")
        self.assertContains(plats, "pd-photo-edit")  # petit appareil photo : changer la photo
        self.assertContains(self.web.get("/gerant/categories/"), "dish-ph-grill")
        self.assertContains(self.web.get(f"/gerant/produits/{poulet.pk}/"), "Sans photo, une illustration")

    def test_manager_can_replace_the_illustration_with_a_photo(self):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        poulet = Product.objects.get(name="Poulet")
        buffer = BytesIO()
        Image.new("RGB", (400, 300), (200, 100, 30)).save(buffer, format="JPEG")
        photo = SimpleUploadedFile("poulet.jpg", buffer.getvalue(), content_type="image/jpeg")
        response = self.web.post(
            f"/gerant/produits/{poulet.pk}/",
            {
                "category": poulet.category_id,
                "name": "Poulet",
                "price": "3000",
                "prep_minutes": "15",
                "is_available": "on",
                "is_active": "on",
                "image": photo,
            },
        )
        self.assertEqual(response.status_code, 302)
        poulet.refresh_from_db()
        self.assertTrue(poulet.image)
        self.assertNotContains(self.client.get(f"/restaurants/{self.resto.slug}/"), "dish-ph-grill")


class PhotoCreditsTests(TestCase):
    def test_credits_page_lists_authors_and_licences(self):
        page = self.client.get("/credits-photos/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Wikimedia Commons")
        self.assertContains(page, "Riz gras")
        self.assertContains(page, "creativecommons.org/licenses/by-sa/4.0/")
        self.assertContains(self.client.get("/"), "/credits-photos/")  # lien en bas de chaque page
        import json
        from pathlib import Path

        import apps.core.views as core_views

        data = json.loads(
            (Path(core_views.__file__).parent / "data" / "photo_credits.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(data), 27)
        self.assertTrue(all(row["author"] and row["license"] and row["source"].startswith("https://") for row in data))
