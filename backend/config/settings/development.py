"""Configuration de développement."""
from .base import *  # noqa: F403

DEBUG = True

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
