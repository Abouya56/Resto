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


@register.filter
def montant(value):
    """2500.00 -> « 2 500 » (sans l'unité : pour les tableaux dont l'en-tête dit déjà « FCFA »)."""
    return str(prix(value)).replace(" " + settings.CURRENCY_LABEL, "")


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


@register.filter
def qte(value):
    """Quantité de stock lisible : 20.000 -> « 20 », 0.250 -> « 0,25 »."""
    try:
        amount = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return value
    text = f"{amount.normalize():f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


@register.filter
def file_url(value):
    """Adresse d'un fichier, ou « » s'il n'y en a pas (au lieu d'une erreur)."""
    if not value or not getattr(value, "name", None):
        return ""
    try:
        return value.url
    except (ValueError, AttributeError):
        return ""


@register.filter
def is_image_field(bound_field):
    from django import forms

    return isinstance(getattr(bound_field, "field", None), forms.ImageField)


# Illustration par défaut d'un plat sans photo : on la choisit d'après les mots de son nom, puis de sa catégorie.
# L'ordre compte : « Eau minérale » est une boisson avant tout, « Salade de fruits » un dessert avant un accompagnement.
DISH_LOOKS = (
    (
        "drink",
        "bi-cup-straw",
        (
            "boisson",
            "jus",
            "bissap",
            "gnamakoudji",
            "zoom",
            "eau",
            "coca",
            "fanta",
            "sprite",
            "brakina",
            "biere",
            "soda",
            "the",
            "cafe",
            "lait",
            "vin",
            "cocktail",
            "limonade",
        ),
    ),
    ("sweet", "bi-cake2", ("dessert", "gateau", "glace", "degue", "fruit", "beignet", "crepe", "patisserie", "mousse")),
    (
        "grill",
        "bi-fire",
        (
            "grillade",
            "brochette",
            "poulet",
            "poisson",
            "porc",
            "mouton",
            "boeuf",
            "viande",
            "braise",
            "steak",
            "merguez",
            "agneau",
            "capitaine",
            "carpe",
        ),
    ),
    ("side", "bi-basket", ("accompagnement", "alloco", "frite", "salade", "legume", "plantain")),
)
DISH_DEFAULT = ("main", "bi-egg-fried")


def _fold(text):
    import unicodedata

    decomposed = unicodedata.normalize("NFD", (text or "").lower().replace("œ", "oe"))
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def _words(text):
    import re

    return set(re.findall(r"[a-z]+", _fold(text)))


@register.simple_tag
def dish_look(product):
    """{'tone': 'drink', 'icon': 'bi-cup-straw'} : l'illustration d'un plat qui n'a pas encore de photo."""
    for source in (product.name, getattr(product.category, "name", "")):
        words = _words(source)
        stems = {w.rstrip("s") for w in words}
        for tone, icon, keywords in DISH_LOOKS:
            if any(keyword in words or keyword in stems for keyword in keywords):
                return {"tone": tone, "icon": icon}
    return {"tone": DISH_DEFAULT[0], "icon": DISH_DEFAULT[1]}


# Logo par défaut d'un restaurant sans logo : ses initiales sur une couleur (toujours la même pour un même nom).
LOGO_TONES = ("ember", "forest", "ocean", "plum", "gold", "teal", "rose")
LOGO_STOP_WORDS = {"le", "la", "les", "l", "du", "de", "des", "au", "aux", "et", "un", "une"}


@register.simple_tag
def restaurant_look(restaurant):
    """{'initials': 'CM', 'tone': 'plum'} pour « Chez Maman »."""
    import re

    name = _fold(getattr(restaurant, "name", "") or "Restaurant")
    words = re.findall(r"[a-z]+", name) or ["r"]
    main = [word for word in words if word not in LOGO_STOP_WORDS] or words
    initials = "".join(word[0] for word in main[:2]).upper()
    seed = sum((index + 1) * ord(char) for index, char in enumerate(name))
    return {"initials": initials, "tone": LOGO_TONES[seed % len(LOGO_TONES)]}


@register.simple_tag(takes_context=True, name="querystring")
def querystring(context, **kwargs):
    """Les paramètres de l'adresse actuelle, modifiés (valeur None = on l'enlève). Sans le « ? » devant.

    Remplace l'étiquette de Django 5.1 pour que le site marche aussi avec Django 4.2.
    """
    request = context["request"]
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value is None:
            params.pop(key, None)
        elif isinstance(value, (list, tuple)):
            params.setlist(key, [str(item) for item in value])
        else:
            params[key] = str(value)
    return params.urlencode()


@register.filter
def whatsapp_link(order):
    """Lien WhatsApp vers le client avec le message prêt ("" sans téléphone)."""
    from apps.orders.whatsapp import whatsapp_url

    return whatsapp_url(order)
