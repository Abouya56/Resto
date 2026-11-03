"""Configuration utilisée par la suite de tests."""

from .base import *  # noqa: F403

DEBUG = True
STOCK_ENABLED = True  # les tests vérifient la fonction ; un test dédié vérifie qu'éteinte, elle disparaît

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
MEDIA_ROOT = BASE_DIR / "media_test"  # noqa: F405
PRIVATE_MEDIA_ROOT = BASE_DIR / "media_test" / "private"  # noqa: F405
