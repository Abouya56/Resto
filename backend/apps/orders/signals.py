from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.notifications.services import notify_restaurant_staff, notify_user
from apps.orders.models import Order


def _broadcast_order(order, event):
    layer = get_channel_layer()
    if layer is None:
        return
    payload = {
        "type": "order.event",
        "event": event,
        "order_id": order.id,
        "number": order.number,
        "status": order.status,
        "restaurant_id": order.restaurant_id,
        "order_type": order.order_type,
        "total": str(order.total),
    }
    async_to_sync(layer.group_send)(f"kitchen_{order.restaurant_id}", payload)
    async_to_sync(layer.group_send)(f"order_{order.id}", payload)


@receiver(post_save, sender=Order)
def order_created_or_updated(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return  # chargement de données (loaddata) : rien à notifier
    # Après le commit : les lignes de commande existent et rien n'est émis si la transaction échoue.
    transaction.on_commit(lambda: _notify_order(instance, created))


def _notify_order(instance, created):
    event = "created" if created else "updated"
    _broadcast_order(instance, event)
    if created:
        notify_restaurant_staff(
            instance.restaurant,
            title="Nouvelle commande",
            message=f"Commande {instance.number} reçue ({instance.get_order_type_display()}).",
            notif_type="order",
            url=f"/gerant/commandes/{instance.pk}/",
        )
    elif instance.customer_id:
        notify_user(
            instance.customer,
            title="Commande mise à jour",
            message=f"Votre commande {instance.number} est maintenant : {instance.get_status_display()}.",
            notif_type="order",
            url=f"/commandes/{instance.pk}/",
        )
