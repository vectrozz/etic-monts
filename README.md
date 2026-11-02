# Etic'Monts

Application web de la coopérative Etic'Monts (Monts du Lyonnais) : suivi des
données MAEC et biodiversité des fermes, coût de revient des cultures, et —
en développement — une marketplace (produits, stocks, commandes clients,
tournées de livraison).

Production : <https://emb.boblabs.eu>

## Modules

| Module | Contenu | Activation |
|---|---|---|
| **MAEC** (cœur) | Comptes, tableau de bord surfaces / biodiversité / plastique / sol / eau / lutte intégrée, fiche ferme, synthèse réseau, coefficients, catalogue partagé | toujours |
| `cout_revient` | Coût de revient par culture (fraise) : temps de travail, intrants, structure → €/kg, marge, repères réseau anonymes | `FEATURES=cout_revient` |
| `marketplace` | Produits, stocks, clients et liens de commande, commandes, tournées | `FEATURES=…,marketplace` |

`FEATURES` est une liste séparée par des virgules (`all` = tout). La
production tourne avec `FEATURES=cout_revient`. Un module désactivé n'a ni
routes, ni entrées de menu, ni tables créées.

## Structure

```
.
├── app.py                  point d'entrée WSGI (gunicorn app:app)
├── eticmonts/              package Python
│   ├── __init__.py         application factory, enregistrement des modules
│   ├── config.py           configuration (variables d'environnement)
│   ├── schema.py           création / migration idempotente du schéma, par module
│   ├── production_cost.py  modèle et calcul du coût de revient
│   ├── blueprints/         routes (main, farm, admin, production_cost, …)
│   └── …                   services (catalogue, commandes, tournées, …)
├── templates/              Jinja (partials/ : sidebar, icônes)
├── static/                 CSS, JS, polices et Chart.js servis localement
├── tests/                  pytest (calcul + smoke tests sur PostgreSQL)
├── scripts/                backup_db.sh, restore_db.sh, seed_demo.py
├── deploy/                 gunicorn.conf.py, nginx/
├── docs/                   DEPLOY.md, notes d'intégration
├── Dockerfile
├── docker-compose.yml      dev (Flask + Postgres, tous les modules)
└── docker-compose.prod.yml prod (gunicorn + nginx + Postgres)
```

## Développement local

```bash
cp .env.example .env          # puis ajuster (SECRET_KEY, mots de passe…)
docker compose up --build     # http://localhost:5003, FEATURES=all par défaut
docker compose exec -e FLASK_ENV=development app-flask python3 scripts/seed_demo.py   # données de démo
```

Sans Docker :

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
POSTGRES_PORT=5434 FLASK_ENV=development FEATURES=all python app.py   # http://localhost:5010
```

Le schéma est créé / mis à jour automatiquement au démarrage
(`eticmonts/schema.py`, idempotent, compatible avec une base v2).

## Tests

```bash
pip install pytest
python -m pytest tests -q                          # calcul du coût de revient

# smoke tests de bout en bout sur une base jetable (jamais la prod) :
docker run -d --name emb-test -e POSTGRES_USER=eticmont -e POSTGRES_PASSWORD=eticmont \
    -e POSTGRES_DB=eticmont -p 127.0.0.1:55432:5432 postgres:17
TEST_POSTGRES_PORT=55432 python -m pytest tests -q
```

Pour valider une migration, restaurez d'abord un dump de prod dans ce
conteneur (`psql … < dump.sql`) puis lancez les tests.

## Déploiement

Voir [docs/DEPLOY.md](docs/DEPLOY.md).
