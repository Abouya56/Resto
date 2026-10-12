# Resto — plateforme multi-restaurant

Plateforme web commerciale de commande et de gestion multi-établissements : menus, tables, QR codes, commandes (sur place, à emporter, livraison), stocks, finances, paiements simulés, notifications et temps réel.

## Technologies

- Python 3.11, Django 5, Django REST Framework, SimpleJWT
- PostgreSQL, Redis, Django Channels / WebSockets
- HTML, CSS, JavaScript, Bootstrap 5
- `qrcode`, Pillow, drf-spectacular (Swagger)
- Docker et Docker Compose

## Prérequis

- Python 3.11+
- PostgreSQL 14+ (ou Docker)
- Git

## Installation locale

```bash
git clone <url-du-depot>
cd Resto
python -m venv .venv
```

Windows PowerShell :

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
copy .env.example .env
```

Linux / macOS :

```bash
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
```

## Configuration `.env`

Copiez `.env.example` vers `.env` puis renseignez notamment :

- `DJANGO_SECRET_KEY`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`
- `REDIS_URL` (optionnel en développement : Channels en mémoire)
- `SITE_URL`

Ne commitez jamais le fichier `.env`.

Sans PostgreSQL sur la machine (démarrage local uniquement) :

```powershell
$env:USE_SQLITE="True"
cd backend
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

## Base PostgreSQL

```sql
CREATE USER resto WITH PASSWORD 'resto_dev_password';
CREATE DATABASE resto OWNER resto;
```

Avec Docker, PostgreSQL est créé automatiquement par `docker-compose`.

## Migrations et données de démo

```bash
cd backend
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
```

Comptes de démonstration créés par `seed_demo` :

| Rôle | E-mail | Mot de passe |
| --- | --- | --- |
| Admin plateforme | admin@resto.local | Admin1234! |
| Personnel (2 restaurants) | gerant.baobab@resto.local, etc. | Staff1234! |

Deux restaurants isolés sont créés : **Le Baobab** et **Chez Maman**.

`seed_demo` refuse de s'exécuter hors mode DEBUG (option `--force` pour passer outre) et ne réinitialise jamais le mot de passe d'un compte existant. Les boutons de connexion rapide n'apparaissent que si `DEMO_LOGINS=True` (par défaut en développement, toujours désactivés en production).

## Parcours et rôles

- **Client** : pas d'inscription publique, il commande sans compte depuis la page d'un restaurant (à emporter, livraison) ou en scannant le QR code de sa table (sur place). Le QR code contient un jeton : sans lui, la commande sur place est refusée ; régénérer le QR invalide l'ancien. Pour suivre sa commande depuis n'importe quel appareil, il va sur **Suivre ma commande** (`/suivi/`) avec son numéro de commande et le téléphone donné (le numéro suffit pour une commande à table sans téléphone ; 10 essais ratés par quart d'heure au maximum).
- **Restaurateur** : ouvre un restaurant via « Ouvrir un restaurant » (pièce d'identité obligatoire). Le restaurant reste **en attente** jusqu'à validation par l'admin plateforme, puis le gérant complète la fiche et ajoute son équipe.
- **Personnel** (rôle défini par restaurant) :
  | Rôle | Accès |
  | --- | --- |
  | Gérant | tout : menu, tables/QR, équipe, stock, finances, commandes, livraisons |
  | Cuisine | accepter, préparer, marquer prête |
  | Serveur | servir, remettre (à emporter), terminer, encaisser les espèces |
  | Livreur | ses livraisons uniquement |
- **Admin plateforme** (`/admin-plateforme/`, app `backoffice`) : valide ou refuse les restaurants, consulte les pièces KYC, les utilisateurs et les commandes.

Le rôle est vérifié **dans le restaurant consulté** : être gérant dans un établissement ne donne aucun droit de gérant dans un autre.

## Lancer le serveur

Le frontend est servi par Django (templates + fichiers statiques).

```bash
cd backend
python manage.py runserver
```

Pour les WebSockets en local, préférez Daphne :

```bash
cd backend
daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

Puis ouvrez http://127.0.0.1:8000/

- API Swagger : http://127.0.0.1:8000/api/docs/
- Admin Django : http://127.0.0.1:8000/admin/

## Tests et qualité du code

```bash
cd backend
python manage.py test --settings=config.settings.test
```

Les tests couvrent en priorité l'**isolation des données entre restaurants**, les droits par rôle, le jeton QR, l'encaissement espèces et la confidentialité des pièces KYC.

Style et imports vérifiés avec [ruff](https://docs.astral.sh/ruff/) (configuration dans `pyproject.toml`) :

```bash
pip install -r backend/requirements-dev.txt
ruff check backend && ruff format --check backend
```

## Docker

```bash
docker compose up --build
```

Le service `web` attend PostgreSQL, applique les migrations, charge le jeu de démo et démarre Daphne. Ce `docker-compose.yml` sert au **développement** (`config.settings.development`).

## Mise en production

Utilisez `DJANGO_SETTINGS_MODULE=config.settings.production` et renseignez au minimum :

- `DJANGO_SECRET_KEY` : longue et aléatoire ;
- `DJANGO_ALLOWED_HOSTS` : obligatoire, aucune valeur par défaut ;
- `DJANGO_CSRF_TRUSTED_ORIGINS` : par exemple `https://resto.example.com` ;
- la base PostgreSQL et `REDIS_URL`.

La configuration active la redirection HTTPS, HSTS, les cookies sécurisés et des fichiers statiques versionnés (WhiteNoise). L'image Docker collecte les statiques à la construction et tourne sans les droits root.

À prévoir côté serveur :

- servir `media/` (logos, photos des plats) par le serveur web ; Django ne le fait qu'en mode DEBUG ;
- sauvegarder `private_media/` avec la base de données : elle contient les pièces d'identité, qui ne sont jamais exposées par une URL publique et ne se consultent que depuis le panneau admin.

## Structure

```
Resto/
├── backend/
│   ├── config/                 # settings, urls, asgi, routing WS
│   ├── apps/
│   │   ├── core/               # tenancy, permissions, middleware, stockage privé
│   │   ├── users/
│   │   ├── restaurants/
│   │   ├── menus/
│   │   ├── tables/
│   │   ├── orders/
│   │   ├── deliveries/
│   │   ├── payments/
│   │   ├── inventory/
│   │   ├── finance/
│   │   ├── notifications/
│   │   └── backoffice/         # panneau admin plateforme
│   ├── templates/              # interfaces HTML
│   ├── static/
│   └── manage.py
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── README.md
```

## Isolation multi-restaurant

Toutes les données métier sont liées à un `Restaurant`. Les querysets API et les vues HTML filtrent sur les employments actifs, et chaque action vérifie le rôle de l'utilisateur dans le restaurant concerné. Un identifiant d'URL d'un autre établissement renvoie 403/404.

## Paiements

Aucun prestataire réel n'est branché. L'architecture (`apps/payments/providers.py`) permet d'ajouter plus tard espèces, mobile money ou paiement en ligne. Le provider `simulated` encaisse automatiquement en développement.

Les commandes passées sur le site sont réglées en espèces. Le paiement passe à « Payé » automatiquement quand la commande est remise (livrée, récupérée ou terminée), ou manuellement avec le bouton « Marquer comme payé » (serveur ou gérant). Le chiffre d'affaires ne compte que les paiements encaissés.
