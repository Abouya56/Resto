"""Interrupteur de la gestion de stock (réglage STOCK_ENABLED).

Éteint : le stock disparaît de l'appli (menus, pages, alertes, déduction automatique, plats « épuisés »).
Rien n'est supprimé : en le rallumant, tout est retrouvé tel quel.
"""

from functools import wraps

from django.conf import settings
from django.http import Http404
from rest_framework.permissions import BasePermission


def stock_enabled():
    return bool(getattr(settings, "STOCK_ENABLED", False))


def stock_filter():
    """Filtre des plats visibles aux clients : cache les plats épuisés seulement si le stock est suivi."""
    return {"out_of_stock": False} if stock_enabled() else {}


def stock_only(view):
    """Pages du stock : introuvables tant que la fonction est éteinte."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not stock_enabled():
            raise Http404()
        return view(request, *args, **kwargs)

    return wrapper


class StockEnabledPermission(BasePermission):
    def has_permission(self, request, view):
        return stock_enabled()
