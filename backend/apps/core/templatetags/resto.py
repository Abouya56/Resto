import os
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.filter
def get_item(mapping, key):
    if not mapping:
        return None
    return mapping.get(key)


@register.filter
def prix(value):
    """2500.00 -> « 2 500 FCFA »."""
    try:
        amount = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return value
    # Le franc CFA n'a pas de centimes : on arrondit \u00e0 l'unit\u00e9.
    text = f"{int(amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP)):,}".replace(",", "\u202f")
    return f"{text}\u00a0{settings.CURRENCY_LABEL}"


@register.simple_tag
def asset(path):
    """URL d'un fichier statique avec sa version : le navigateur recharge le fichier dès qu'il change."""
    url = static(path)
    if "?" in url:
        return url
    found = finders.find(path)
    if found:
        url = f"{url}?v={int(os.path.getmtime(found))}"
    return url
