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


# Une même adresse (téléphone, wifi) qui rate trop de connexions sur des comptes différents est bloquée aussi.
MAX_ATTEMPTS_PER_IP = 30


def _ip_key(ip):
    return "login-fail-ip:" + (ip or "")


def is_locked(email, ip=None):
    if ip and cache.get(_ip_key(ip), 0) >= MAX_ATTEMPTS_PER_IP:
        return True
    return bool(email) and cache.get(_key(email), 0) >= MAX_ATTEMPTS


def register_failure(email, ip=None):
    """Compte un essai raté. Le compteur s'efface seul au bout de LOCK_MINUTES."""
    if ip:
        cache.set(_ip_key(ip), cache.get(_ip_key(ip), 0) + 1, LOCK_MINUTES * 60)
    if not email:
        return
    key = _key(email)
    cache.set(key, cache.get(key, 0) + 1, LOCK_MINUTES * 60)


def reset(email):
    cache.delete(_key(email))
