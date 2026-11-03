"""App installable (PWA) : fiche de l'app, service worker et page « hors connexion »."""

from django.contrib.staticfiles import finders
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

THEME_COLOR = "#0f2a1f"
BACKGROUND_COLOR = "#ecf1e9"


@require_GET
def manifest(request):
    """La fiche que le téléphone lit pour proposer « Ajouter à l'écran d'accueil »."""
    data = {
        "name": "Resto — commandes de restaurants",
        "short_name": "Resto",
        "description": "Commandez sur place, à emporter ou en livraison, et suivez votre commande en direct.",
        "lang": "fr",
        "dir": "ltr",
        "start_url": "/?source=app",
        "scope": "/",
        "id": "/",
        "display": "standalone",
        "orientation": "any",
        "theme_color": THEME_COLOR,
        "background_color": BACKGROUND_COLOR,
        "categories": ["food", "shopping"],
        "icons": [
            {"src": static("img/icons/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": static("img/icons/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {
                "src": static("img/icons/icon-maskable-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
        "shortcuts": [
            {"name": "Voir les restaurants", "url": "/restaurants/"},
            {"name": "Suivre ma commande", "url": "/suivi/"},
        ],
    }
    response = JsonResponse(data, json_dumps_params={"ensure_ascii": False})
    response["Content-Type"] = "application/manifest+json; charset=utf-8"
    response["Cache-Control"] = "public, max-age=3600"
    return response


@require_GET
@never_cache
def service_worker(request):
    """Servi à la racine du site pour pouvoir couvrir toutes les pages (un fichier /static/ ne le pourrait pas)."""
    path = finders.find("js/sw.js")
    if not path:
        raise Http404()
    response = FileResponse(open(path, "rb"), content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    return response


@require_GET
def offline(request):
    return render(request, "offline.html")
