#!/bin/sh
# Sauvegarde du site : la base de données ET les photos. À lancer chaque nuit (voir le guide).
# Les 14 dernières sauvegardes sont gardées dans le dossier « backups ».
set -eu

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f deploy/docker-compose.prod.yml --env-file .env"
DATE=$(date +%Y-%m-%d_%H%M)
mkdir -p backups

# 1. La base de données
$COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "backups/base-$DATE.sql.gz"

# 2. Les photos envoyées (logos, plats) et les pièces d'identité
$COMPOSE exec -T web tar -C /app -czf - media private_media > "backups/fichiers-$DATE.tar.gz"

# 3. On ne garde que les 14 dernières
ls -1t backups/base-*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm --
ls -1t backups/fichiers-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm --

echo "Sauvegarde terminée : backups/base-$DATE.sql.gz et backups/fichiers-$DATE.tar.gz"
