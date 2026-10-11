from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings

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
    if amount == amount.to_integral_value():
        text = f"{int(amount):,}".replace(",", "\u202f")
    else:
        text = f"{amount:,.2f}".replace(",", "\u202f").replace(".", ",")
    return f"{text}\u00a0{settings.CURRENCY_LABEL}"
