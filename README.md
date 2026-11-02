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
| `whatsapp` | Listes des fermes reçues du groupe WhatsApp via l'app Android « EMB Relais » ([android/](android/README.md)) : boîte de réception par ferme, expéditeurs → fermes, téléphones relais | `FEATURES=…,whatsapp` |

`FEATURES` est une liste séparée par des virgules (`all` = tout). La
production tourne avec `FEATURES=cout_revient`. Un module désactivé n'a ni
routes ni entrées de menu (ses tables existent mais restent vides).

## Structure

```
.
├── app.py                  point d'entrée WSGI (gunicorn app:app)
├── eticmonts/              package Python
│   ├── __init__.py         application factory, modules, /healthz
│   ├── config.py           configuration (variables d'environnement)
│   ├── schema_version.py   refuse de démarrer si la base n'est pas à jour (Alembic)
│   ├── production_cost.py  modèle et calcul du coût de revient
│   ├── blueprints/         routes (main, farm, admin, production_cost, …)
│   └── …                   services (catalogue, commandes, tournées, …)
├── migrations/             Alembic : env.py + versions/ (SQL écrit à la main)
├── android/                app Android « EMB Relais » (Kotlin) : relaie le groupe WhatsApp
├── templates/              Jinja (partials/ : sidebar, icônes)
├── static/                 CSS, JS, polices et Chart.js servis localement
├── tests/                  pytest : calcul, migrations, smoke tests (+ fixtures/ schéma v2)
├── scripts/                ci.sh, deploy.sh, build-android.sh, backup_db.sh, restore_db.sh, seed_demo.py
├── deploy/                 gunicorn.conf.py, nginx/ (vhost de l'hôte + certbot)
├── docs/                   DEPLOY.md, notes d'intégration
├── Dockerfile
├── docker-compose.yml      dev : Flask (auto-reload) + Postgres, tous les modules
├── docker-compose.prod.yml prod : gunicorn sur 127.0.0.1:8085 + Postgres
├── alembic.ini · pyproject.toml (pytest, ruff) · Makefile
└── requirements.txt · requirements-dev.txt
```

## Développement local

```bash
cp .env.example .env          # puis ajuster si besoin
make dev                      # = docker compose up --build → http://localhost:5003 (FEATURES=all)
docker compose exec -e FLASK_ENV=development app-flask python3 scripts/seed_demo.py   # données de démo
```

Le conteneur de dev applique les migrations au démarrage (`alembic upgrade
head`). Nouvelle évolution de schéma : voir [migrations/README.md](migrations/README.md).

## CI locale (avant chaque push)

```bash
make hooks          # une fois : lance la CI automatiquement avant chaque `git push`
make ci             # = scripts/ci.sh : tout, ≈ 20 s une fois l'image en cache
make ci-fast        # sans construire l'image Docker
make ci-dump DUMP=backups/prod_20261102.sql   # + migration d'une copie de vraies données
```

`scripts/ci.sh` (besoin de `python3` et `docker`) : ruff → syntaxe des
scripts → fichiers compose → PostgreSQL 17 jetable → pytest (calcul du coût
de revient, migrations Alembic sur base neuve / schéma v2 réel / bases
pré-Alembic, smoke tests de l'application) → image de prod : migration du
schéma v2, démarrage gunicorn, `/healthz`. Aucune base existante n'est
touchée. Sans base, `python -m pytest` ne lance que les tests unitaires.

## Déploiement

Seule la branche `main` est déployée : on fusionne dans `main` (CI locale OK,
pas de pull request), on pousse, puis `scripts/deploy.sh` sur le VPS
(sauvegarde → `origin/main` → build → migrations → redémarrage → health
check). Détails : [docs/DEPLOY.md](docs/DEPLOY.md).
