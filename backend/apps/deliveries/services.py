from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.deliveries.models import Delivery, DeliveryStatus
from apps.orders.models import OrderStatus, OrderType
from apps.orders.services import transition_order
from apps.restaurants.models import Employee
from apps.users.roles import Role


def ensure_delivery(order):
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


def assign_driver(delivery, driver):
    is_driver = Employee.objects.filter(
        user=driver,
        restaurant=delivery.order.restaurant,
        role=Role.DRIVER,
        is_active=True,
    ).exists()
    if not is_driver:
        raise ValidationError("L'utilisateur n'est pas un livreur de ce restaurant.")
    delivery.driver = driver
    delivery.status = DeliveryStatus.ASSIGNED
    delivery.assigned_at = timezone.now()
    delivery.save()
    return delivery


def driver_transition(delivery, new_status, user):
    if delivery.driver_id != user.id:
        raise ValidationError("Cette livraison ne vous est pas attribuée.")
    allowed = {
        DeliveryStatus.ASSIGNED: DeliveryStatus.ACCEPTED,
        DeliveryStatus.ACCEPTED: DeliveryStatus.PICKED_UP,
        DeliveryStatus.PICKED_UP: DeliveryStatus.IN_TRANSIT,
        DeliveryStatus.IN_TRANSIT: DeliveryStatus.DELIVERED,
    }
    expected = allowed.get(delivery.status)
    if expected != new_status:
        raise ValidationError("Transition de livraison non autorisée.")
    now = timezone.now()
    delivery.status = new_status
    if new_status == DeliveryStatus.PICKED_UP:
        delivery.picked_up_at = now
        if delivery.order.status == OrderStatus.READY:
            transition_order(delivery.order, OrderStatus.OUT_FOR_DELIVERY, user)
    elif new_status == DeliveryStatus.IN_TRANSIT and delivery.order.status == OrderStatus.READY:
        transition_order(delivery.order, OrderStatus.OUT_FOR_DELIVERY, user)
    elif new_status == DeliveryStatus.DELIVERED:
        delivery.delivered_at = now
        if delivery.order.status == OrderStatus.OUT_FOR_DELIVERY:
            transition_order(delivery.order, OrderStatus.DELIVERED, user)
    delivery.save()
    return delivery
