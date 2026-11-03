"""Configuration de développement."""

from .base import *  # noqa: F403

DEBUG = True

# Test sur téléphone (même Wi-Fi) : l'adresse du PC change selon le réseau, donc on accepte toute adresse.
# Uniquement en développement : jamais en production (production.py exige une liste précise).
ALLOWED_HOSTS = ["*"]

# Test à distance avec un tunnel Cloudflare (adresse https://xxxx.trycloudflare.com qui change à chaque lancement).
CSRF_TRUSTED_ORIGINS = [*CSRF_TRUSTED_ORIGINS, "https://*.trycloudflare.com"]  # noqa: F405
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # le tunnel parle https, le site le sait ainsi
DEMO_LOGINS = env.bool("DEMO_LOGINS", default=True)  # noqa: F405

# En local sans Redis, les WebSockets restent fonctionnels en mémoire.
if env.bool("USE_INMEMORY_CHANNELS", default=True):  # noqa: F405
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }

# Option pour démarrer sans PostgreSQL (tests / machine de dev minimale).
if env.bool("USE_SQLITE", default=False):  # noqa: F405
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        }
    }
