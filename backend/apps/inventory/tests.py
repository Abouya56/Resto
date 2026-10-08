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
