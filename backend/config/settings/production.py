"""Configuration de production."""

from .base import *  # noqa: F403

DEBUG = False

# Pas de valeur par défaut : DJANGO_ALLOWED_HOSTS doit être renseigné explicitement.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")  # noqa: F405
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=31536000)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"

# Les comptes de démonstration ne sont jamais proposés en production.
DEMO_LOGINS = False

# Fichiers statiques versionnés (nom haché) et compressés, servis par WhiteNoise.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Photos envoyées (plats, logos, QR codes) chez Cloudinary quand CLOUDINARY_URL est donné :
# elles survivent aux redémarrages des serveurs gratuits (Render efface son disque).
# Les pièces d'identité restent sur le serveur (stockage privé, jamais public).
if env("CLOUDINARY_URL", default=""):  # noqa: F405
    INSTALLED_APPS = [*INSTALLED_APPS, "cloudinary_storage", "cloudinary"]  # noqa: F405
    STORAGES["default"] = {"BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"}
