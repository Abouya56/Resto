from django.core.exceptions import ValidationError

from apps.deliveries.models import Delivery
from apps.orders.models import OrderType


def ensure_delivery(order):
    """Garde une fiche de livraison (adresse, frais) pour chaque commande en livraison."""
    if order.order_type != OrderType.DELIVERY:
        raise ValidationError("Cette commande n'est pas une livraison.")
    delivery, _ = Delivery.objects.get_or_create(
        order=order,
        defaults={
            "address_text": order.location_display or order.delivery_address_text,
            "fee": order.delivery_fee,
        },
    )
    return delivery
