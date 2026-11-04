#!/bin/sh
# Démarrage de la démonstration sur Render : prépare la base, crée le super admin, lance le site.
# Le mot de passe du super admin vient de la variable ADMIN_PASSWORD saisie dans Render (jamais dans le projet).
set -e
python manage.py migrate --noinput

# Pour repartir d'une base vide : mettre RESET_DB=1 dans Render pour UN déploiement, puis l'enlever.
if [ "${RESET_DB:-}" = "1" ]; then
  python manage.py flush --noinput
fi

if [ -n "${ADMIN_EMAIL:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ]; then
  python manage.py create_platform_admin --email "$ADMIN_EMAIL" --password "$ADMIN_PASSWORD" \
    --first-name Admin --last-name Resto --if-missing --skip-validation
fi

exec daphne -b 0.0.0.0 -p "${PORT:-10000}" config.asgi:application
