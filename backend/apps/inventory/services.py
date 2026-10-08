from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.inventory.models import StockItem, StockMovement, StockMovementType
from apps.notifications.services import notify_restaurant_managers


@transaction.atomic
def apply_movement(item: StockItem, movement_type, quantity, reason, user=None):
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise ValidationError("La quantité doit être positive.")
    if movement_type == StockMovementType.OUT and item.quantity < quantity:
        raise ValidationError("Stock insuffisant.")
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
        reason=reason,
        user=user,
    )
    if item.is_low:
        notify_restaurant_managers(
            item.restaurant,
            title="Stock faible",
            message=f"{item.name} a atteint le seuil minimal ({item.quantity} {item.unit}).",
            notif_type="stock",
            url="/gerant/stocks/",
        )
    return movement
