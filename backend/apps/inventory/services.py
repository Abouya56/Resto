from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.inventory.models import RecipeIngredient, StockItem, StockMovement, StockMovementType
from apps.notifications.services import notify_restaurant_managers

DEFAULT_REASONS = {
    StockMovementType.IN: "Achat",
    StockMovementType.OUT: "Sortie (perte, casse…)",
    StockMovementType.ADJUST: "Inventaire (comptage)",
}


def _alert_if_low(item, before):
    """Une seule alerte : au moment où l'article passe sous le seuil, pas à chaque sortie."""
    if item.is_low and before > item.min_threshold:
        notify_restaurant_managers(
            item.restaurant,
            title="Stock faible",
            message=f"{item.name} : il reste {item.quantity.normalize():f} {item.unit}. Pensez à racheter.",
            notif_type="stock",
            url="/gerant/stocks/",
        )


@transaction.atomic
def apply_movement(item: StockItem, movement_type, quantity, reason="", user=None):
    quantity = Decimal(quantity)
    if movement_type == StockMovementType.ADJUST:
        if quantity < 0:
            raise ValidationError("La quantité comptée ne peut pas être négative.")
    elif quantity <= 0:
        raise ValidationError("La quantité doit être positive.")
    item = StockItem.objects.select_for_update().get(pk=item.pk)
    before = item.quantity
    if movement_type == StockMovementType.OUT and item.quantity < quantity:
        raise ValidationError(f"Stock insuffisant : il reste {item.quantity.normalize():f} {item.unit}.")
    if movement_type == StockMovementType.IN:
        item.quantity += quantity
    elif movement_type == StockMovementType.OUT:
        item.quantity -= quantity
    elif movement_type == StockMovementType.ADJUST:
        item.quantity = quantity
    else:
        raise ValidationError("Type de mouvement inconnu.")
    item.save(update_fields=["quantity", "updated_at"])
    movement = StockMovement.objects.create(
        restaurant=item.restaurant,
        item=item,
        movement_type=movement_type,
        quantity=quantity,
        reason=(reason or "").strip() or DEFAULT_REASONS[movement_type],
        user=user,
    )
    _alert_if_low(item, before)
    refresh_products([item])
    return movement


@transaction.atomic
def consume_order(order, user=None):
    """Retire du stock les ingrédients des plats d'une commande, d'après leurs recettes.

    Appelé quand la cuisine commence la préparation. Ne bloque jamais la cuisine :
    si le stock noté est trop bas, il passe en négatif (signe qu'un achat n'a pas été noté).
    """
    from apps.inventory.feature import stock_enabled

    if not stock_enabled() or order.stock_movements.exists():
        return []  # fonction éteinte, ou commande déjà déduite
    needs = defaultdict(Decimal)
    recipes = RecipeIngredient.objects.filter(product__in=[line.product_id for line in order.items.all()])
    per_product = defaultdict(list)
    for recipe in recipes:
        per_product[recipe.product_id].append(recipe)
    for line in order.items.all():
        for recipe in per_product[line.product_id]:
            needs[recipe.stock_item_id] += recipe.quantity * line.quantity
    if not needs:
        return []
    needs = {pk: amount.quantize(Decimal("0.001")) for pk, amount in needs.items()}
    label = f"Commande N° {order.short_number}" if order.short_number else f"Commande {order.number}"
    movements = []
    items = StockItem.objects.select_for_update().filter(pk__in=needs, restaurant=order.restaurant)
    for item in items:
        before = item.quantity
        item.quantity -= needs[item.pk]
        item.save(update_fields=["quantity", "updated_at"])
        movements.append(
            StockMovement.objects.create(
                restaurant=item.restaurant,
                item=item,
                movement_type=StockMovementType.OUT,
                quantity=needs[item.pk],
                reason=label,
                user=user,
                order=order,
            )
        )
        _alert_if_low(item, before)
    refresh_products(items)
    return movements


def refresh_products(items):
    """Marque « épuisé » chaque plat dont un ingrédient ne suffit plus pour une portion (et l'inverse)."""
    from apps.menus.models import Product

    products = Product.objects.filter(recipe_items__stock_item__in=list(items)).distinct()
    refresh_product_list(products)


def refresh_product_list(products):
    for product in products.prefetch_related("recipe_items__stock_item"):
        missing = any(
            recipe.stock_item.is_active and recipe.stock_item.quantity < recipe.quantity
            for recipe in product.recipe_items.all()
        )
        if product.out_of_stock != missing:
            product.out_of_stock = missing
            product.save(update_fields=["out_of_stock", "updated_at"])
