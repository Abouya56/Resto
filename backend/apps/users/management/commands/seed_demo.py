from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.finance.models import Expense, ExpenseCategory
from apps.inventory.models import StockItem
from apps.menus.models import Category, Product
from apps.restaurants.models import Employee, Restaurant
from apps.tables.models import DiningTable
from apps.tables.services import ensure_qrcode
from apps.users.models import User
from apps.users.roles import Role


class Command(BaseCommand):
    help = "Crée un jeu de données de démonstration isolé par restaurant."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Autorise l'exécution hors mode DEBUG.")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Les comptes de démo ont des mots de passe publics : "
                "exécution refusée hors DEBUG (--force pour passer outre)."
            )
        admin, admin_created = User.objects.get_or_create(
            email="admin@resto.local",
            defaults={
                "first_name": "Awa",
                "last_name": "Kone",
                "role": Role.PLATFORM_ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if admin_created:
            admin.set_password("Admin1234!")
            admin.save()

        specs = [
            {
                "name": "Le Baobab",
                "slug": "le-baobab",
                "city": "Abidjan",
                "district": "Cocody",
                "address": "Rue des Jardins",
                "manager": ("gerant.baobab@resto.local", "Fatou", "Diop"),
                "cook": ("cuisine.baobab@resto.local", "Mamadou", "Sow"),
                "waiter": ("service.baobab@resto.local", "Aicha", "Bamba"),
                "driver": ("livreur.baobab@resto.local", "Koffi", "Yao"),
                "dishes": [("Grillades", "Poulet braisé", Decimal("4500")), ("Boissons", "Bissap", Decimal("800"))],
            },
            {
                "name": "Chez Maman",
                "slug": "chez-maman",
                "city": "Abidjan",
                "district": "Yopougon",
                "address": "Boulevard Principal",
                "manager": ("gerant.maman@resto.local", "Aminata", "Kone"),
                "cook": ("cuisine.maman@resto.local", "Ibrahim", "Coulibaly"),
                "waiter": ("service.maman@resto.local", "Nadia", "Ouattara"),
                "driver": ("livreur.maman@resto.local", "Serge", "N'Guessan"),
                "dishes": [("Plats", "Attiéké poisson", Decimal("3500")), ("Desserts", "Dégué", Decimal("1000"))],
            },
        ]

        for spec in specs:
            restaurant, _ = Restaurant.objects.get_or_create(
                slug=spec["slug"],
                defaults={
                    "name": spec["name"],
                    "description": f"Restaurant {spec['name']}",
                    "phone": "2122232425",
                    "email": f"contact@{spec['slug']}.local",
                    "address": spec["address"],
                    "city": spec["city"],
                    "district": spec["district"],
                    "delivery_fee": Decimal("1000"),
                    "min_delivery_amount": Decimal("3000"),
                },
            )
            for role, key in (
                (Role.MANAGER, "manager"),
                (Role.COOK, "cook"),
                (Role.WAITER, "waiter"),
                (Role.DRIVER, "driver"),
            ):
                email, first, last = spec[key]
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={"first_name": first, "last_name": last, "role": role},
                )
                if created:
                    user.set_password("Staff1234!")
                    user.role = role
                    user.save()
                Employee.objects.get_or_create(user=user, restaurant=restaurant, defaults={"role": role})

            for index in range(1, 5):
                table, _ = DiningTable.objects.get_or_create(
                    restaurant=restaurant,
                    number=str(index),
                    defaults={"capacity": 4},
                )
                ensure_qrcode(table)

            for cat_name, dish_name, price in spec["dishes"]:
                category, _ = Category.objects.get_or_create(
                    restaurant=restaurant, name=cat_name, defaults={"sort_order": 1}
                )
                Product.objects.get_or_create(
                    restaurant=restaurant,
                    name=dish_name,
                    defaults={"category": category, "price": price, "description": dish_name},
                )

            StockItem.objects.get_or_create(
                restaurant=restaurant,
                name="Huile",
                defaults={"unit": "L", "quantity": Decimal("8"), "min_threshold": Decimal("3")},
            )
            Expense.objects.get_or_create(
                restaurant=restaurant,
                description="Approvisionnement initial",
                defaults={
                    "category": ExpenseCategory.SUPPLIES,
                    "amount": Decimal("25000"),
                    "date": timezone.localdate(),
                    "user": User.objects.get(email=spec["manager"][0]),
                },
            )

        self.stdout.write(self.style.SUCCESS("Données de démonstration prêtes."))
        self.stdout.write("Admin: admin@resto.local / Admin1234!")
        self.stdout.write("Personnel: * / Staff1234!")
