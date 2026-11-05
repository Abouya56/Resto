"""Blocage après plusieurs essais ratés : empêche de deviner un mot de passe en essayant des milliers de fois."""

from django.core.cache import cache

MAX_ATTEMPTS = 5
LOCK_MINUTES = 15
LOCKED_MESSAGE = (
    f"Trop d'essais ratés : ce compte est bloqué pendant {LOCK_MINUTES} minutes. "
    "Réessayez plus tard, ou demandez un nouveau mot de passe."
)


def _key(email):
    return "login-fail:" + (email or "").strip().lower()


def is_locked(email):
    return bool(email) and cache.get(_key(email), 0) >= MAX_ATTEMPTS


def register_failure(email):
    """Compte un essai raté. Le compteur s'efface seul au bout de LOCK_MINUTES."""
    if not email:
        return
    key = _key(email)
    cache.set(key, cache.get(key, 0) + 1, LOCK_MINUTES * 60)


def reset(email):
    cache.delete(_key(email))
