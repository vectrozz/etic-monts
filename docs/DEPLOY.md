# Etic'Monts — déploiement

- [Mise en production v3.1 : coût de revient fraise](#mise-en-production-v31--coût-de-revient-fraise) ← **à faire**
- [Architecture](#architecture)
- [Première installation](#première-installation)
- [Mise à jour courante](#mise-à-jour-courante)
- [Sauvegarde / restauration](#sauvegarde--restauration)
- [HTTPS](#https-lets-encrypt)
- [Sécurité serveur](#sécurité-serveur)

---

## Mise en production v3.1 : coût de revient fraise

La prod tourne aujourd'hui en **v2.0** (base MAEC). La v3.1 apporte :

- le module **coût de revient fraise** (seul nouveau module activé en prod) ;
- la nouvelle interface (clair / sombre automatique, navigation mobile) ;
- la gestion des rôles (admin / producteur) ;
- la marketplace reste **désactivée** (`FEATURES=cout_revient`).

### Ce que fait la migration (automatique au démarrage)

Testée sur le dump de prod du 13/04/2026 (16 fermes) :

| Changement | Effet |
|---|---|
| `fermes` : colonnes `role`, `is_active`, `contact_email`, `contact_phone`, `lat`, `lng`, `photo_path` | tous les comptes existants deviennent `producteur`, actifs |
| `fermes.name` : contrainte UNIQUE | ajoutée seulement si aucun doublon (aucun en prod) |
| nouvelles tables `app_settings`, `catalog_items`, `production_cost` | vides au départ |
| tables marketplace | **non créées** tant que le module est désactivé |

Aucune donnée existante n'est modifiée ni supprimée. Le code v2 fonctionne
encore sur une base migrée (colonnes ajoutées avec valeurs par défaut) : le
retour arrière ne demande pas de restauration.

### ⚠️ Rôles : à lire avant de déployer

En v2, tout utilisateur connecté voyait « Résumé EMB » et pouvait modifier les
coefficients. En v3, la **synthèse réseau, les coefficients MAEC, la gestion
des utilisateurs et la vue réseau du coût de revient sont réservés aux
admins**, et un producteur ne voit que sa propre fiche.

Après migration il n'y a **aucun admin**. Renseignez dans `.env` l'identifiant
d'un compte existant : il sera promu admin au démarrage (mot de passe
inchangé).

```env
BOOTSTRAP_ADMIN_USER=a        # votre identifiant actuel
```

### Étapes

```bash
cd /opt/eticmont                     # dossier du déploiement sur le serveur

# 0. Repérer comment le site est servi aujourd'hui (le serveur répond
#    "nginx/1.18.0 (Ubuntu)" : c'est le nginx de l'hôte qui est devant).
docker compose -f docker-compose.prod.yml ps
grep -rn "static" /etc/nginx/sites-enabled/     # chemin servi pour /static/
#    → le dossier static/ reste à la racine du dépôt : aucun changement
#      nécessaire si nginx pointe sur /opt/eticmont/static/.

# 1. Sauvegarde
scripts/backup_db.sh 2>/dev/null || \
  docker compose -f docker-compose.prod.yml exec -T postgres-db \
    pg_dump -U eticmont eticmont > /home/postgres-backups/pre-v3_$(date +%Y%m%d_%H%M%S).sql

# 2. Code
git fetch && git checkout <branche ou tag de release>   # ou rsync depuis le poste

# 3. .env — ajouter / vérifier :
#      FEATURES=cout_revient
#      BOOTSTRAP_ADMIN_USER=<votre identifiant>
#      NGINX_CONF=nginx-ssl.conf     # seulement si le nginx du compose est utilisé en HTTPS
#      POSTGRES_BIND=127.0.0.1       # Postgres n'est plus exposé publiquement
#    (SECRET_KEY, POSTGRES_*, REGISTER_TOKEN restent inchangés)

# 4. Reconstruire et relancer l'application (la base n'est pas touchée)
docker compose -f docker-compose.prod.yml up -d --build app-flask
docker compose -f docker-compose.prod.yml logs --tail=50 app-flask
#    attendu : "Promoted existing user 'a' to admin", aucune trace d'erreur

# 5. Vérifier
curl -sI https://emb.boblabs.eu/login | head -1                          # HTTP/1.1 200
curl -s https://emb.boblabs.eu/login | grep -o 'style.css?v=[0-9]*'       # nouvelle feuille versionnée
curl -sI https://emb.boblabs.eu/static/fonts/geist-latin-wght.woff2 | head -1   # 200 → nginx sert bien le nouveau static/
```

Puis dans le navigateur, avec le compte admin : tableau de bord, fiche,
**Coût de revient → Fraise**, saisir une campagne de test et la supprimer,
**Administration → Synthèse réseau**.

> Le CSS est versionné (`style.css?v=…`) : le cache 30 jours du nginx ne
> sert donc pas l'ancienne feuille de style après la mise à jour.

### Retour arrière

```bash
git checkout <commit v2 précédent>
docker compose -f docker-compose.prod.yml up -d --build app-flask
```

La base reste compatible. Restaurer la sauvegarde de l'étape 1 n'est utile
que pour effacer les saisies faites entre-temps.

---

## Architecture

```
Internet ──▶ nginx (TLS, /static/) ──▶ gunicorn :8000 (Flask, 3 workers) ──▶ PostgreSQL 17
                                                                           volume eticmonts_postgres-data
```

| Fichier | Rôle |
|---|---|
| `docker-compose.prod.yml` | services `app-flask`, `nginx`, `postgres-db` (projet `eticmonts`) |
| `Dockerfile` | image de l'application |
| `deploy/gunicorn.conf.py` | configuration gunicorn |
| `deploy/nginx/nginx.conf`, `nginx-ssl.conf` | reverse proxy HTTP / HTTPS (choisi par `NGINX_CONF`) |
| `.env` | secrets et réglages (modèle : `.env.example`) |
| `scripts/backup_db.sh`, `scripts/restore_db.sh` | sauvegarde / restauration |

Ce qui ne change jamais entre deux déploiements : le volume
`eticmonts_postgres-data`, le dossier de sauvegardes, le `.env`,
`static/uploads/` (photos de profil).

> Ne jamais lancer `docker compose down -v` : `-v` supprime le volume de la base.

---

## Première installation

```bash
git clone https://github.com/vectrozz/etic-monts.git /opt/eticmont && cd /opt/eticmont
cp .env.example .env && nano .env          # SECRET_KEY, POSTGRES_PASSWORD, REGISTER_TOKEN, BOOTSTRAP_ADMIN_*
sudo mkdir -p /home/postgres-backups
docker compose -f docker-compose.prod.yml up -d --build
```

Pour repartir d'un dump existant : lancer d'abord `postgres-db` seul, puis
`scripts/restore_db.sh <dump.sql>`, puis le reste de la stack.

## Mise à jour courante

```bash
cd /opt/eticmont
scripts/backup_db.sh
git pull
docker compose -f docker-compose.prod.yml up -d --build app-flask nginx
```

## Sauvegarde / restauration

```bash
scripts/backup_db.sh                             # → $BACKUP_DIR/db_backup_<date>.sql
KEEP_DAYS=30 scripts/backup_db.sh                # + supprime les dumps de plus de 30 jours
scripts/restore_db.sh /home/postgres-backups/db_backup_XXXX.sql   # demande confirmation
```

Crontab quotidienne :

```cron
0 2 * * * cd /opt/eticmont && KEEP_DAYS=60 scripts/backup_db.sh >> /var/log/eticmont-backup.log 2>&1
```

Les dumps contiennent des données personnelles : ils ne doivent jamais être
commités (ignorés par `.gitignore`).

## HTTPS (Let's Encrypt)

```bash
sudo snap install --classic certbot && sudo ln -s /snap/bin/certbot /usr/bin/certbot
docker compose -f docker-compose.prod.yml stop nginx
sudo certbot certonly --standalone -d emb.boblabs.eu
echo "NGINX_CONF=nginx-ssl.conf" >> .env
docker compose -f docker-compose.prod.yml up -d nginx
```

Renouvellement (crontab) :

```cron
0 3 * * * certbot renew --quiet --pre-hook "docker compose -f /opt/eticmont/docker-compose.prod.yml stop nginx" --post-hook "docker compose -f /opt/eticmont/docker-compose.prod.yml start nginx"
```

Si c'est le nginx de l'hôte qui termine le TLS (cas actuel), il suffit qu'il
proxifie vers l'application et serve `/static/` depuis `/opt/eticmont/static/`.

## Sécurité serveur

- **UFW** : n'ouvrir que 22, 80, 443. Docker contourne UFW pour les ports
  publiés : Postgres est donc publié sur `127.0.0.1` uniquement
  (`POSTGRES_BIND`).
- **fail2ban** : jails `sshd`, `nginx-http-auth`, `nginx-botsearch` (monter
  les logs nginx sur l'hôte si le nginx du compose est utilisé).
- **Inscription** : protégée par `REGISTER_TOKEN`. Sur une base existante,
  un nouvel inscrit est toujours `producteur` (seule une base vide fait du
  premier compte un admin).
