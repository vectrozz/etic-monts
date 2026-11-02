# Etic'Monts — déploiement (VPS emb.boblabs.eu)

> Le VPS héberge d'autres sites (tensorcash, otc-bot…). Tout ce qui suit ne
> touche **que** le projet compose `eticmonts`, le vhost `emb.conf` et la
> crontab EMB. Ne jamais lancer de commande docker/nginx globale.

## Architecture

```
Internet ─▶ nginx de l'hôte (TLS, /etc/nginx/sites-enabled/emb.conf)
         ─▶ 127.0.0.1:8085 ─▶ app-flask (gunicorn 3 workers, sert aussi /static)
                             ─▶ postgres-db (PostgreSQL 17, volume eticmonts_postgres-data)
```

| Où | Quoi |
|---|---|
| `/root/EMB/etic-monts` | le dépôt git + `.env` (secrets, jamais commité) |
| `/etc/nginx/sites-available/emb.conf` | vhost (copie de `deploy/nginx/emb.boblabs.eu.conf`) |
| `/etc/letsencrypt/live/emb.boblabs.eu/` | certificat, renouvelé par `snap.certbot.renew.timer` (webroot) |
| `/home/postgres-backups/` | dumps quotidiens |
| crontab root | sauvegarde quotidienne |

Le schéma de la base est géré par **Alembic** (`migrations/`). L'application
refuse de démarrer si la base n'est pas à la bonne révision.

---

## Workflow : seul `main` est déployé

Développeur seul, pas de pull request :

1. travailler sur une branche locale (ou directement sur `main`) ;
2. `scripts/ci.sh` doit passer (le hook pre-push le relance de toute façon) ;
3. fusionner dans `main` et pousser : `git switch main && git merge --ff-only <branche> && git push` ;
4. sur le VPS : `scripts/deploy.sh` — il déploie `origin/main` et **refuse
   toute autre branche**. On ne commite jamais sur le serveur.

---

## 1. Sauvegardes (corrigé le 02/11/2026)

Tous les dumps du 21/04/2026 au 02/11/2026 font **0 octet** : la ligne cron
utilisait `docker ps -qf "name=postgres-db"`, qui renvoie aussi
`otc-bot-postgres-db` (créé le 20/04/2026) → `docker exec` échouait chaque nuit.
Corrigé le 02/11/2026 : dump manuel valide
(`manual_20261102_155738.sql`, 35 Ko) et ligne cron avec le nom exact du
conteneur :

```cron
0 2 * * * docker exec eticmonts-postgres-db-1 pg_dump -U eticmont eticmont > /home/postgres-backups/db_backup_$(date +\%Y\%m\%d_\%H\%M\%S).sql
```

Après le déploiement v3.1 (§2), remplacer cette ligne par le script, qui
vérifie le dump et signale l'échec :

```cron
0 2 * * * /root/EMB/etic-monts/scripts/backup_db.sh >> /var/log/eticmonts-backup.log 2>&1
```

Optionnel : supprimer les ~600 fichiers vides
`find /home/postgres-backups -name 'db_backup_*.sql' -size 0 -delete`.

---

## 2. Premier déploiement v2 → v3.1 (une seule fois)

Prod actuelle : `main@8efb901` (v2.0) avec deux fichiers modifiés à la main
sur le serveur (`docker-compose.prod.yml`, `nginx/nginx.conf` : le conteneur
nginx « rétrogradé » en backend 127.0.0.1:8085). La v3.1 supprime ce
conteneur : gunicorn écoute directement sur 127.0.0.1:8085, **le vhost
`emb.conf` et certbot ne changent pas**.

Prérequis : la v3.1 est fusionnée dans `main` et poussée (`scripts/ci.sh` OK).

```bash
cd /root/EMB/etic-monts

# 1. sauvegarde
docker exec eticmonts-postgres-db-1 pg_dump -U eticmont eticmont \
  > /home/postgres-backups/pre-v3_$(date +%Y%m%d_%H%M%S).sql && ls -la /home/postgres-backups/pre-v3_*

# 2. mettre de côté les modifications locales du serveur (reprises par la v3)
git stash push -m "v2 server edits (nginx demoted to 127.0.0.1:8085)"

# 3. variables ajoutées par la v3
cat >> .env <<'EOF'
FEATURES=cout_revient
BOOTSTRAP_ADMIN_USER=a
APP_PORT=8085
POSTGRES_BIND=127.0.0.1
EOF

# 4. récupérer main (deploy.sh n'existe qu'à partir de la v3), puis déployer
#    (sauvegarde vérifiée, build, migrations Alembic, redémarrage, health check)
git pull --ff-only origin main
scripts/deploy.sh
```

`deploy.sh` supprime l'ancien conteneur `eticmonts-nginx-1` (il occupait
127.0.0.1:8085) et recrée `postgres-db` une fois (son port n'est plus publié
que sur 127.0.0.1 au lieu de 0.0.0.0 ; les données restent dans le volume).
Coupure : quelques secondes.

Ce que la migration fait sur la base (testé sur une copie de la prod du
02/11/2026, nombre de lignes identique avant/après) : ajoute les colonnes de
rôle/profil à `fermes` (tous les comptes deviennent `producteur`), la
contrainte UNIQUE sur `fermes.name`, les tables `app_settings`,
`catalog_items`, `production_cost` et les tables marketplace (vides, module
désactivé). Aucune donnée existante n'est modifiée.

Vérifications :

```bash
docker compose -f docker-compose.prod.yml ps                     # app-flask healthy
docker compose -f docker-compose.prod.yml logs --tail=30 app-flask   # "Promoted existing user 'a' to admin"
curl -s http://127.0.0.1:8085/healthz                            # {"schema":"0004","status":"ok",…}
```

Puis dans le navigateur avec le compte `a` : tableau de bord, **Coût de
revient → Fraise** (saisir puis supprimer une campagne test),
**Administration → Synthèse réseau**. Enfin, mettre la crontab à jour (§1).

> En v3, la synthèse réseau, les coefficients et la gestion des utilisateurs
> sont réservés aux admins ; un producteur ne voit que sa propre fiche.

---

## 3. Déploiements suivants

```bash
# sur le poste de dev
scripts/ci.sh                               # ou: make ci (le hook pre-push le fait aussi)
git switch main && git merge --ff-only <branche> && git push

# sur le VPS
/root/EMB/etic-monts/scripts/deploy.sh      # toujours origin/main, sans argument
```

`deploy.sh` : contrôles (`.env`, checkout sur `main`, aucun fichier suivi
modifié) → sauvegarde (échoue si le dump est vide) → fast-forward sur
`origin/main` → build → `alembic upgrade head` → redémarrage de `app-flask`
→ `/healthz`. Il affiche la marche à suivre pour revenir en arrière.

## Activer un module

Les modules sont choisis dans `.env` (`FEATURES`), puis `scripts/deploy.sh`.
Exemple, module WhatsApp (listes des fermes via l'app Android) :

```bash
sed -i 's/^FEATURES=.*/FEATURES=cout_revient,whatsapp/' /root/EMB/etic-monts/.env
/root/EMB/etic-monts/scripts/deploy.sh
```

Puis **WhatsApp → Téléphone relais** sur le site et
[android/README.md](../android/README.md) pour installer l'app.

## 4. Migrations de base (Alembic)

- Nouvelle évolution de schéma : `alembic revision -m "…"` puis écrire le SQL
  dans `migrations/versions/NNNN_….py` (`upgrade` **et** `downgrade`).
- `scripts/ci.sh` teste : base neuve upgrade → downgrade → upgrade, upgrade
  du schéma v2 réel, et l'image de prod. Avec `--dump backups/xxx.sql`, il
  migre aussi une copie de vraies données.
- Ne jamais modifier une migration déjà passée en prod.
- Voir `migrations/README.md`.

## 5. Sauvegarde / restauration

```bash
scripts/backup_db.sh                                   # dump vérifié dans $BACKUP_DIR
KEEP_DAYS=120 scripts/backup_db.sh                     # + purge des dumps valides > 120 jours (garde toujours les 7 derniers)
scripts/restore_db.sh /home/postgres-backups/xxx.sql   # DESTRUCTIF, demande confirmation
```

Copier un dump sur le poste de dev (lecture seule côté serveur) :

```bash
ssh root@62.84.176.253 'docker exec eticmonts-postgres-db-1 pg_dump -U eticmont eticmont' > backups/prod_$(date +%Y%m%d).sql
```

Les dumps contiennent des données personnelles : `backups/` et `*.sql` sont
ignorés par git.

## 6. Retour arrière

- **Code** : sur le poste de dev, `git revert` des commits fautifs sur `main`,
  `scripts/ci.sh`, `git push`, puis `scripts/deploy.sh` sur le VPS (la prod
  reste toujours sur `main`). Si la version annulée contenait une migration,
  ajouter une nouvelle migration qui la défait plutôt que de lancer
  `alembic downgrade` à la main.
- **Retour d'urgence en v2** (une seule fois, juste après la mise en v3) : le
  code v2 fonctionne sur la base migrée (colonnes ajoutées avec valeurs par
  défaut) — revert des commits v3 sur `main` comme ci-dessus.
- **Données** : `scripts/restore_db.sh <dump de l'étape sauvegarde>`.

## 7. TLS

Rien à faire : vhost `emb.conf` + certbot *webroot* (`/var/www/certbot`,
snippet `snippets/acme.conf` partagé par tous les vhosts) + timer
`snap.certbot.renew.timer`. Certificat valide jusqu'au 17/12/2026, renouvelé
automatiquement 30 jours avant. Contrôle : `certbot renew --dry-run`.
Nouvelle installation : `deploy/nginx/README.md`.

## 8. Sécurité (constats du 02/11/2026)

- PostgreSQL EMB était publié sur `0.0.0.0:5433` (Docker contourne UFW) →
  publié sur `127.0.0.1` à partir de la v3.1.
- UFW autorise encore le port `5010` (ancien serveur Flask de dev) : plus
  utilisé, la règle peut être retirée (`ufw delete allow 5010`).
- `otc-bot-postgres-db` est aussi publié sur `0.0.0.0:5454` (hors EMB, à
  vérifier par son propriétaire).
