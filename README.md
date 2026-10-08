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
| Client | client@resto.local | Client1234! |
| Personnel (2 restaurants) | gerant.baobab@resto.local, etc. | Staff1234! |

Deux restaurants isolés sont créés : **Le Baobab** et **Chez Maman**.

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

## Tests

```bash
cd backend
python manage.py test --settings=config.settings.test
```

Le point critique couvert est l'**isolation des données entre restaurants**.

## Docker

```bash
docker compose up --build
```

Le service `web` attend PostgreSQL, applique les migrations, charge le jeu de démo et démarre Daphne.

## Structure

```
Resto/
├── backend/
│   ├── config/                 # settings, urls, asgi, routing WS
│   ├── apps/
│   │   ├── core/               # tenancy, permissions, middleware
│   │   ├── users/
│   │   ├── restaurants/
│   │   ├── menus/
│   │   ├── tables/
│   │   ├── orders/
│   │   ├── deliveries/
│   │   ├── payments/
│   │   ├── inventory/
│   │   ├── finance/
│   │   └── notifications/
│   ├── templates/              # interfaces HTML
│   ├── static/
│   └── manage.py
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── README.md
```

## Isolation multi-restaurant

Toutes les données métier sont liées à un `Restaurant`. Les querysets API et les vues HTML filtrent sur les employments actifs. Un identifiant d'URL d'un autre établissement renvoie 403/404.

## Paiements

Aucun prestataire réel n'est branché. L'architecture (`apps/payments/providers.py`) permet d'ajouter plus tard espèces, mobile money ou paiement en ligne. Le provider `simulated` encaisse automatiquement en développement.
