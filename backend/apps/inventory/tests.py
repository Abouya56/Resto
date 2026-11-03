from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.finance.models import Expense, ExpenseCategory
from apps.inventory.models import StockItem, StockMovementType
from apps.inventory.services import apply_movement
from apps.restaurants.models import Restaurant
from apps.users.models import User
from apps.users.roles import Role


class StockExpenseTests(TestCase):
    def setUp(self):
        self.resto = Restaurant.objects.create(name="Stock", address="x", city="Y")
        self.user = User.objects.create_user(
            email="st@test.local", password="pass12345", first_name="S", last_name="T", role=Role.MANAGER
        )
        self.item = StockItem.objects.create(
            restaurant=self.resto, name="Huile", unit="L", quantity=Decimal("5"), min_threshold=Decimal("2")
        )

    def test_stock_in_and_out(self):
        apply_movement(self.item, StockMovementType.IN, Decimal("3"), "Achat", self.user)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, Decimal("8"))
        apply_movement(self.item, StockMovementType.OUT, Decimal("1"), "Service", self.user)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, Decimal("7"))
        with self.assertRaises(ValidationError):
            apply_movement(self.item, StockMovementType.OUT, Decimal("20"), "Erreur", self.user)

    def test_expense_belongs_to_restaurant(self):
        expense = Expense.objects.create(
            restaurant=self.resto,
            category=ExpenseCategory.SUPPLIES,
            amount=Decimal("1000"),
            description="Légumes",
            date="2026-01-01",
            user=self.user,
        )
        self.assertEqual(expense.restaurant_id, self.resto.id)


class AutoStockTests(TestCase):
    def setUp(self):
        from django.test import Client

        from apps.menus.models import Category, Product
        from apps.restaurants.models import Employee

        self.resto = Restaurant.objects.create(name="Auto", address="x", city="Y")
        self.manager = User.objects.create_user(
            email="auto@test.local", password="pass12345", first_name="A", last_name="M", role=Role.MANAGER
        )
        Employee.objects.create(user=self.manager, restaurant=self.resto, role=Role.MANAGER)
        category = Category.objects.create(restaurant=self.resto, name="Plats")
        self.dish = Product.objects.create(restaurant=self.resto, category=category, name="Riz sauce", price=2000)
        self.rice = StockItem.objects.create(
            restaurant=self.resto, name="Riz", unit="kg", quantity=Decimal("1"), min_threshold=Decimal("0.5")
        )
        self.web = Client()
        self.web.force_login(self.manager)
        session = self.web.session
        session["current_restaurant_id"] = self.resto.pk
        session.save()

    def _order(self, quantity):
        from apps.orders.models import Cart, OrderType
        from apps.orders.services import add_to_cart, checkout_cart

        cart = Cart.objects.create(restaurant=self.resto, order_type=OrderType.TAKEAWAY, session_key="s")
        add_to_cart(cart, self.dish, quantity)
        return checkout_cart(cart, contact={"first_name": "A", "last_name": "B", "phone": "0700000000"})

    def test_manager_says_how_many_dishes_one_unit_serves(self):
        response = self.web.post(
            f"/gerant/plats/{self.dish.pk}/recette/", {"stock_item": self.rice.pk, "servings": "4"}
        )
        self.assertEqual(response.status_code, 302)
        link = self.dish.recipe_items.get()
        self.assertEqual(link.quantity, Decimal("0.25"))
        self.assertEqual(link.servings, Decimal("4"))
        page = self.web.get(f"/gerant/plats/{self.dish.pk}/recette/")
        self.assertContains(page, "1 kg de <strong>Riz</strong> = <strong>4 Riz sauce</strong>", html=False)
        self.assertContains(page, "vous pouvez encore vendre <strong>4 Riz sauce</strong>", html=False)

    def test_one_kg_for_three_dishes_has_no_drift(self):
        from apps.orders.models import OrderStatus
        from apps.orders.services import transition_order

        self.web.post(f"/gerant/plats/{self.dish.pk}/recette/", {"stock_item": self.rice.pk, "servings": "3"})
        self.assertEqual(self.dish.recipe_items.get().servings, Decimal("3"))
        order = self._order(3)
        for status in (OrderStatus.ACCEPTED, OrderStatus.PREPARING):
            transition_order(order, status)
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.quantity, Decimal("0"))

    def test_preparing_an_order_consumes_stock_once(self):
        from apps.inventory.models import RecipeIngredient
        from apps.notifications.models import Notification
        from apps.orders.models import OrderStatus
        from apps.orders.services import transition_order

        RecipeIngredient.objects.create(product=self.dish, stock_item=self.rice, quantity=Decimal("0.25"))
        order = self._order(2)
        transition_order(order, OrderStatus.ACCEPTED)
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.quantity, Decimal("1"))  # rien tant que la cuisine n'a pas commencé
        transition_order(order, OrderStatus.PREPARING, self.manager)
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.quantity, Decimal("0.5"))
        movement = self.rice.movements.get(order=order)
        self.assertEqual(movement.reason, f"Commande N° {order.short_number}")
        self.assertEqual(Notification.objects.filter(title="Stock faible").count(), 1)
        from apps.inventory.services import consume_order

        consume_order(order)
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.quantity, Decimal("0.5"))

    def test_dish_hidden_when_ingredient_runs_out_and_back_after_purchase(self):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from apps.inventory.models import RecipeIngredient
        from apps.orders.models import OrderStatus
        from apps.orders.services import transition_order

        RecipeIngredient.objects.create(product=self.dish, stock_item=self.rice, quantity=Decimal("0.5"))
        order = self._order(2)
        for status in (OrderStatus.ACCEPTED, OrderStatus.PREPARING):
            transition_order(order, status)
        self.dish.refresh_from_db()
        self.assertTrue(self.dish.out_of_stock)
        menu = self.client.get(f"/restaurants/{self.resto.slug}/")
        self.assertNotContains(menu, "Riz sauce")
        with self.assertRaises(DjangoValidationError):
            self._order(1)

        self.web.post(f"/gerant/stocks/{self.rice.pk}/mouvement/", {"action": "in", "quantity": "5"})
        self.dish.refresh_from_db()
        self.assertFalse(self.dish.out_of_stock)

    def test_manual_actions_are_simple(self):
        self.web.post(f"/gerant/stocks/{self.rice.pk}/mouvement/", {"action": "in", "quantity": "2,5"})
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.quantity, Decimal("3.5"))
        self.assertEqual(self.rice.movements.first().reason, "Achat")
        self.web.post(f"/gerant/stocks/{self.rice.pk}/mouvement/", {"action": "adjust", "quantity": "3"})
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.quantity, Decimal("3"))
        page = self.web.get("/gerant/stocks/")
        self.assertContains(page, "J'ai compté")
        self.assertContains(page, "3 <span>kg</span>", html=False)

    def test_new_item_records_starting_stock_and_quantity_locked_after(self):
        self.web.post(
            "/gerant/stocks/nouveau/",
            {"name": "Huile", "unit": "L", "quantity": "10", "min_threshold": "2", "is_active": "on"},
        )
        oil = StockItem.objects.get(name="Huile")
        self.assertEqual(oil.quantity, Decimal("10"))
        self.assertEqual(oil.movements.get().reason, "Stock de départ")
        self.web.post(
            f"/gerant/stocks/{oil.pk}/",
            {"name": "Huile", "unit": "L", "quantity": "999", "min_threshold": "2", "is_active": "on"},
        )
        oil.refresh_from_db()
        self.assertEqual(oil.quantity, Decimal("10"))


class DailyCashTests(TestCase):
    setUp = AutoStockTests.setUp
    _order = AutoStockTests._order

    def test_day_shows_money_in_money_out_and_stock(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.orders.models import OrderStatus
        from apps.orders.services import transition_order
        from apps.payments.providers import CashPaymentProvider

        order = self._order(1)
        CashPaymentProvider().charge(order, method="cash_on_site")
        for status in (OrderStatus.ACCEPTED, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.PICKED_UP):
            transition_order(order, status)
        today = timezone.localdate()
        Expense.objects.create(
            restaurant=self.resto,
            category=ExpenseCategory.SUPPLIES,
            amount=Decimal("500"),
            description="Tomates",
            date=today,
            user=self.manager,
        )
        Expense.objects.create(
            restaurant=self.resto,
            category=ExpenseCategory.RENT,
            amount=Decimal("9000"),
            description="Loyer",
            date=today - timedelta(days=1),
            user=self.manager,
        )
        self.web.post(f"/gerant/stocks/{self.rice.pk}/mouvement/", {"action": "in", "quantity": "3"})

        page = self.web.get("/gerant/finances/")
        journal = page.context["journal"]
        self.assertEqual(journal["cashed"], Decimal("2000"))
        self.assertEqual(journal["spent"], Decimal("500"))
        self.assertEqual(journal["balance"], Decimal("1500"))
        self.assertEqual(journal["stock"][0]["in"], Decimal("3"))
        self.assertContains(page, "Tomates")
        self.assertNotContains(page, "Loyer")

        yesterday = self.web.get(f"/gerant/finances/?jour={(today - timedelta(days=1)).isoformat()}")
        self.assertEqual(yesterday.context["journal"]["spent"], Decimal("9000"))
        self.assertContains(yesterday, "Loyer")
        summary = page.context["summary"]
        self.assertEqual(summary[0]["balance"], Decimal("1500"))
        self.assertEqual(summary[1]["balance"], Decimal("-9000"))

        form = self.web.get(f"/gerant/depenses/nouvelle/?jour={(today - timedelta(days=1)).isoformat()}")
        self.assertContains(form, (today - timedelta(days=1)).isoformat())


class ExpenseListTests(TestCase):
    setUp = AutoStockTests.setUp

    def test_grouped_by_month_with_month_split(self):
        from django.utils import timezone

        today = timezone.localdate()
        Expense.objects.create(
            restaurant=self.resto,
            category=ExpenseCategory.SUPPLIES,
            amount=Decimal("3000"),
            description="Tomates",
            date=today,
            user=self.manager,
        )
        Expense.objects.create(
            restaurant=self.resto,
            category=ExpenseCategory.RENT,
            amount=Decimal("1000"),
            description="Loyer",
            date=today,
            user=self.manager,
        )
        Expense.objects.create(
            restaurant=self.resto,
            category=ExpenseCategory.OTHER,
            amount=Decimal("500"),
            description="Vieux",
            date=today.replace(year=today.year - 1),
            user=self.manager,
        )
        page = self.web.get("/gerant/depenses/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(len(page.context["groups"]), 2)
        self.assertEqual(page.context["groups"][0]["total"], Decimal("4000"))
        self.assertEqual(page.context["month_total"], Decimal("4000"))
        split = page.context["by_category"]
        self.assertEqual([(r["key"], r["percent"]) for r in split], [("supplies", 75), ("rent", 25)])
        self.assertContains(page, "Dépensé ce mois-ci")


class CashTrendTests(TestCase):
    setUp = AutoStockTests.setUp

    def test_trend_lists_only_active_days_and_feeds_chart(self):
        import json
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        Expense.objects.create(
            restaurant=self.resto,
            category=ExpenseCategory.RENT,
            amount=Decimal("9000"),
            description="Loyer",
            date=today - timedelta(days=2),
            user=self.manager,
        )
        page = self.web.get("/gerant/finances/")
        self.assertEqual(len(page.context["active_days"]), 1)
        self.assertEqual(page.context["quiet_days"], 13)
        self.assertEqual(page.context["period_totals"]["balance"], Decimal("-9000"))
        self.assertContains(page, "13 jours sans encaissement ni dépense ne sont pas listés")
        days = json.loads(json.dumps(page.context["chart_days"]))  # données réellement envoyées au graphique
        self.assertEqual(len(days), 14)
        self.assertEqual(days[-1]["day"], today.isoformat())  # le plus récent à droite
        self.assertTrue(days[-1]["selected"])
        self.assertEqual(days[-3]["spent"], 9000.0)
        self.assertContains(page, 'id="fin-chart-data"')
        self.assertContains(page, "js/fin-chart.js")


class StockSwitchedOffTests(TestCase):
    """STOCK_ENABLED éteint (le choix par défaut) : le stock disparaît, rien n'est supprimé."""

    setUp = AutoStockTests.setUp
    _order = AutoStockTests._order

    def test_stock_is_invisible_when_switched_off(self):
        from django.test import override_settings

        with override_settings(STOCK_ENABLED=False):
            for url in (
                "/gerant/stocks/",
                "/gerant/stocks/nouveau/",
                "/gerant/stocks/historique/",
                f"/gerant/plats/{self.dish.pk}/recette/",
            ):
                self.assertEqual(self.web.get(url).status_code, 404, url)
            self.assertEqual(
                self.web.post(
                    f"/gerant/stocks/{self.rice.pk}/mouvement/", {"action": "in", "quantity": "5"}
                ).status_code,
                404,
            )
            dashboard = self.web.get("/gerant/")
            self.assertNotContains(dashboard, "/gerant/stocks/")
            self.assertNotContains(dashboard, "Stock faible")
            self.assertNotContains(self.web.get("/gerant/produits/"), "Relier au stock")
            self.assertNotContains(self.web.get("/gerant/produits/"), "Plus de stock")
            self.assertNotContains(self.web.get("/gerant/finances/"), "Stock du jour")
            self.assertEqual(self.web.get("/api/inventory/items/").status_code, 403)

    def test_dish_left_sold_out_is_orderable_again_and_stock_untouched(self):
        from decimal import Decimal

        from django.test import override_settings

        from apps.inventory.models import RecipeIngredient
        from apps.orders.models import OrderStatus
        from apps.orders.services import transition_order

        RecipeIngredient.objects.create(product=self.dish, stock_item=self.rice, quantity=Decimal("0.5"))
        type(self.dish).objects.filter(pk=self.dish.pk).update(out_of_stock=True)
        with override_settings(STOCK_ENABLED=False):
            self.assertContains(self.client.get(f"/restaurants/{self.resto.slug}/"), "Riz sauce")
            order = self._order(2)  # accepté malgré l'ancien drapeau « épuisé »
            for status in (OrderStatus.ACCEPTED, OrderStatus.PREPARING):
                transition_order(order, status)
            self.rice.refresh_from_db()
            self.assertEqual(self.rice.quantity, Decimal("1"))  # aucune déduction
            self.assertFalse(order.stock_movements.exists())
        # Réactivé : tout est retrouvé tel quel.
        self.assertEqual(self.web.get("/gerant/stocks/").status_code, 200)


class SalesPageTests(TestCase):
    setUp = AutoStockTests.setUp
    _order = AutoStockTests._order

    def _pay(self, method, quantity=1):
        from apps.orders.models import OrderStatus
        from apps.orders.services import transition_order
        from apps.payments.providers import CashPaymentProvider

        order = self._order(quantity)
        CashPaymentProvider().charge(order, method=method)
        for status in (OrderStatus.ACCEPTED, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.PICKED_UP):
            transition_order(order, status)
        return order

    def test_sales_page_shows_money_received_per_day(self):
        from django.utils import timezone

        self._pay("cash_on_site", 1)  # 2 000
        self._pay("cash_on_site", 2)  # 4 000
        from apps.payments.providers import CashPaymentProvider

        pending = self._order(1)  # vendu, paiement en attente (créé à la commande, comme dans l'appli)
        CashPaymentProvider().charge(pending, method="cash_on_site")
        page = self.web.get("/gerant/ventes/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["today_received"], Decimal("6000"))
        sales = page.context["sales"]
        self.assertEqual(sales["total"], Decimal("6000"))
        self.assertEqual(sales["count"], 2)
        today = sales["days"][0]
        self.assertEqual(today["day"], timezone.localdate())
        self.assertEqual(today["average"], Decimal("3000"))
        self.assertEqual(today["methods"][0]["label"], "Espèces")
        self.assertContains(page, "Reçu aujourd'hui")
        self.assertNotContains(page, "pas encore encaissé")  # une commande non encaissée n'est jamais une vente

    def test_previous_month_and_future_are_safe(self):
        past = self.web.get("/gerant/ventes/?mois=2020-03")
        self.assertEqual(past.status_code, 200)
        self.assertContains(past, "Aucun paiement reçu en mars 2020")
        self.assertFalse(past.context["is_current_month"])
        future = self.web.get("/gerant/ventes/?mois=2999-01")
        self.assertTrue(future.context["is_current_month"])  # on ne montre pas l'avenir
        self.assertEqual(self.web.get("/gerant/ventes/?mois=n-importe-quoi").status_code, 200)

    def test_menu_dashboard_and_expenses_point_to_sales(self):
        from django.utils import timezone

        Expense.objects.create(
            restaurant=self.resto,
            category=ExpenseCategory.OTHER,
            amount=Decimal("100"),
            description="x",
            date=timezone.localdate(),
            user=self.manager,
        )
        dashboard = self.web.get("/gerant/")
        self.assertContains(dashboard, "Argent reçu")
        self.assertContains(dashboard, "/gerant/ventes/")
        self.assertContains(self.web.get("/gerant/depenses/"), "Reçu ce mois-ci")


class MoneyDateFilterTests(TestCase):
    setUp = AutoStockTests.setUp
    _order = AutoStockTests._order
    _pay = SalesPageTests._pay

    def _expense(self, days_ago, category, amount, label):
        from datetime import timedelta

        from django.utils import timezone

        return Expense.objects.create(
            restaurant=self.resto,
            category=category,
            amount=Decimal(amount),
            description=label,
            date=timezone.localdate() - timedelta(days=days_ago),
            user=self.manager,
        )

    def test_expenses_by_day_range_and_category(self):
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        self._expense(0, ExpenseCategory.SUPPLIES, "1000", "Tomates")
        self._expense(3, ExpenseCategory.RENT, "9000", "Loyer")
        self._expense(3, ExpenseCategory.SUPPLIES, "2000", "Poulets")
        self._expense(20, ExpenseCategory.OTHER, "500", "Vieux")
        one_day = self.web.get(f"/gerant/depenses/?jour={today - timedelta(days=3)}")
        self.assertEqual({e.description for e in one_day.context["expenses"]}, {"Loyer", "Poulets"})
        self.assertEqual(one_day.context["range_total"], Decimal("11000"))
        self.assertContains(one_day, "sur cette sélection")
        by_category = self.web.get(f"/gerant/depenses/?periode=7j&categorie={ExpenseCategory.SUPPLIES}")
        self.assertEqual({e.description for e in by_category.context["expenses"]}, {"Tomates", "Poulets"})
        self.assertEqual(by_category.context["range_total"], Decimal("3000"))
        nothing = self.web.get("/gerant/depenses/?periode=hier")
        self.assertContains(nothing, "Aucune dépense pour cette sélection")
        self.assertEqual(len(self.web.get("/gerant/depenses/").context["expenses"]), 4)  # sans filtre : tout

    def test_sales_for_one_day_and_a_range(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.payments.models import Payment

        today = timezone.localdate()
        self._pay("cash_on_site", 1)  # 2 000 aujourd'hui
        old = self._pay("cash_on_site", 3)  # 6 000, payé il y a 3 jours
        Payment.objects.filter(order=old).update(paid_at=timezone.now() - timedelta(days=3))
        day = self.web.get(f"/gerant/ventes/?jour={today - timedelta(days=3)}")
        self.assertEqual(day.context["sales"]["total"], Decimal("6000"))
        self.assertTrue(day.context["is_range"])
        self.assertContains(day, "Revenir à la vue par mois")
        self.assertNotContains(day, "Mois précédent")
        self.assertNotContains(day, "Reçu aujourd'hui")  # la période choisie ne contient pas aujourd'hui
        week = self.web.get("/gerant/ventes/?periode=7j")
        self.assertEqual(week.context["sales"]["total"], Decimal("8000"))
        self.assertContains(week, "Reçu aujourd'hui")
        self.assertEqual(self.web.get("/gerant/ventes/?periode=hier").context["sales"]["total"], 0)
        month = self.web.get("/gerant/ventes/")  # sans filtre : navigation par mois comme avant
        self.assertFalse(month.context["is_range"])
        self.assertContains(month, "Mois précédent")

    def test_dashboard_follows_the_chosen_period(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.payments.models import Payment

        paid = self._pay("cash_on_site", 2)  # 4 000 aujourd'hui
        self._expense(0, ExpenseCategory.SUPPLIES, "1500", "Courses")
        today = self.web.get("/gerant/")
        self.assertEqual(today.context["metrics"]["revenue"], Decimal("4000"))
        self.assertEqual(today.context["metrics"]["expenses"], Decimal("1500"))
        Payment.objects.filter(order=paid).update(paid_at=timezone.now() - timedelta(days=1))
        yesterday = self.web.get("/gerant/?periode=hier")
        self.assertEqual(yesterday.context["metrics"]["revenue"], Decimal("4000"))
        self.assertEqual(self.web.get("/gerant/").context["metrics"]["revenue"], 0)
        self.assertEqual(yesterday.context["metrics"]["period_label"], "Hier")
        legacy = self.web.get("/gerant/?period=week")  # anciennes adresses : toujours valables
        self.assertEqual(legacy.context["metrics"]["revenue"], Decimal("4000"))
        self.assertNotContains(self.web.get("/gerant/"), 'class="df"')  # le choix de période est dans Ventes
