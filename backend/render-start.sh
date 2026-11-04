#!/bin/sh
# Démarrage de la démonstration sur Render : prépare la base, ajoute les données fictives, lance le site.
set -e
python manage.py migrate --noinput
python manage.py seed_demo --force
exec daphne -b 0.0.0.0 -p "${PORT:-10000}" config.asgi:application
