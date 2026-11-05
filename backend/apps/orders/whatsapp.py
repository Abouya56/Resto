"""Prévenir le client gratuitement : un lien WhatsApp avec le message déjà écrit.

La réception touche le bouton, WhatsApp s'ouvre sur la conversation du client : il n'y a plus qu'à envoyer.
Aucun service payant, aucun compte à créer.
"""

import re
from urllib.parse import quote

from django.conf import settings
from django.urls import reverse

from apps.orders.models import OrderStatus, OrderType


def international_number(phone):
    """« 07 00 00 00 00 » → « 2250700000000 ». Renvoie "" si le numéro est inutilisable."""
    raw = (phone or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if raw.startswith("+"):
        return digits
    if digits.startswith("00"):
        return digits[2:]
    code = getattr(settings, "PHONE_COUNTRY_CODE", "225")
    if digits.startswith(code) and len(digits) > len(code) + 7:
        return digits
    return code + digits


def client_message(order):
    """Le texte envoyé au client, selon que la commande est acceptée ou refusée."""
    hello = f"Bonjour {order.customer_first_name}," if order.customer_first_name else "Bonjour,"
    name = f"N° {order.short_number}" if order.short_number else order.number
    restaurant = order.restaurant.name
    if order.status == OrderStatus.CANCELLED:
        reason = f" ({order.cancellation_reason.lower()})" if order.cancellation_reason else ""
        return f"{hello} désolé : votre commande {name} chez {restaurant} n'a pas pu être acceptée{reason}."
    ready_for = f"pour {order.arrival_label}" if order.arrival_at else "à votre arrivée"
    next_step = {
        OrderType.DINE_IN: "Elle arrive bientôt à votre table.",
        OrderType.TAKEAWAY: f"Elle sera prête dans environ {order.restaurant.estimated_prep_minutes} min.",
        OrderType.DELIVERY: "Elle sera livrée bientôt.",
        OrderType.PREORDER: f"Elle sera prête {ready_for}.",
    }.get(order.order_type, "")
    track = f"{settings.SITE_URL.rstrip('/')}{reverse('orders:track')}"
    return f"{hello} votre commande {name} chez {restaurant} est acceptée. {next_step} Suivre votre commande : {track}"


def whatsapp_url(order):
    """Lien qui ouvre WhatsApp sur le client avec le message prêt. "" si la commande n'a pas de téléphone."""
    number = international_number(order.customer_phone)
    if not number:
        return ""
    return f"https://wa.me/{number}?text={quote(client_message(order))}"
