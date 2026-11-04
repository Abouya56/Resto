"""Démonstration gratuite sur Render : un seul petit serveur, sans Redis ni Caddy.

Ne sert qu'à montrer le site. Pour de vrais restaurants, utiliser config.settings.production (voir deploy/).
"""

import os

from .production import *  # noqa: F403

# Render donne l'adresse du site (ex. resto-demo.onrender.com) ; on l'accepte seule.
_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if _host:
    ALLOWED_HOSTS = [_host]  # noqa: F405
    CSRF_TRUSTED_ORIGINS = [f"https://{_host}"]  # noqa: F405
    SITE_URL = f"https://{_host}"

# Base de données fournie par Render (variable DATABASE_URL).
DATABASES = {"default": env.db("DATABASE_URL")}  # noqa: F405

# Un seul processus : les mises à jour en direct passent par la mémoire (pas de Redis).
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# Les photos sont servies par Django (pas de Caddy). Elles disparaissent à chaque redémarrage du serveur gratuit.
SERVE_MEDIA = True

# Comptes de démonstration visibles sur la page de connexion (données fictives uniquement).
DEMO_LOGINS = os.environ.get("DEMO_LOGINS", "True") == "True"

# Render termine déjà le https : pas de redirection en plus.
SECURE_SSL_REDIRECT = False
