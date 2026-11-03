"""Reçu de commande : la page imprimable et l'e-mail envoyé au client."""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)


def receipt_email(order):
    if order.customer_email:
        return order.customer_email
    if order.customer_id:
        return order.customer.email
    return ""


def tracking_url(order):
    return f"{settings.SITE_URL.rstrip('/')}{reverse('orders:track')}?numero={order.number}"


def send_order_receipt(order):
    """Envoie le reçu si le client a laissé un e-mail. Un échec d'envoi ne bloque jamais la commande."""
    email = receipt_email(order)
    if not email:
        return False
    context = {"order": order, "tracking_url": tracking_url(order)}
    subject = f"Votre commande N° {order.short_number} chez {order.restaurant.name} — Réf. {order.reference}"
    message = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string("emails/order_receipt.txt", context),
        to=[email],
    )
    message.attach_alternative(render_to_string("emails/order_receipt.html", context), "text/html")
    try:
        message.send()
    except Exception:  # noqa: BLE001 - serveur mail indisponible : la commande reste valide
        logger.exception("Reçu non envoyé pour la commande %s", order.number)
        return False
    return True
