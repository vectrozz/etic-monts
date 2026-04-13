# ETICMONT – Guide de déploiement en production

## Architecture

```
Internet
   │
   ▼
┌──────────┐      ┌────────────┐      ┌──────────────┐
│  Nginx   │─────▶│  Gunicorn  │─────▶│  PostgreSQL   │
│  :80     │      │  (Flask)   │      │  :5432        │
│          │      │  :8000     │      │               │
└──────────┘      └────────────┘      └──────────────┘
   static/                               postgres-data
   files                                 (volume Docker)
```

- **Nginx** – reverse proxy, sert les fichiers statiques, port 80
- **Gunicorn** – serveur WSGI (remplace `python app.py`), port 8000 interne
- **PostgreSQL 17** – base de données, données dans un volume Docker nommé (`postgres-data`)

---

## Prérequis sur le serveur

| Outil | Version minimum |
|-------|----------------|
| Docker Engine | 24+ |
| Docker Compose (plugin) | v2+ |
| Git (optionnel) | pour récupérer le code |

Vérifier :
```bash
docker --version
docker compose version
```

---

## Étape 1 – Copier les fichiers sur le serveur

Transférer le projet sur le serveur (scp, rsync, git clone…).

```bash
# Exemple avec rsync
rsync -avz --exclude '.venv' --exclude '__pycache__' \
  /chemin/local/ETICMONTS/ user@server:/opt/eticmont/
```

Structure attendue sur le serveur :

```
/opt/eticmont/
├── app.py
├── docker-compose.prod.yml
├── Dockerfile.prod
├── gunicorn.conf.py
├── .env                      ← à créer (voir étape 2)
├── .env.example
├── requirements.txt
├── nginx/
│   └── nginx.conf
├── static/
│   └── style.css
├── templates/
│   └── *.html
├── bkp/
│   └── backup.sh
└── restore_db.sh
```

---

## Étape 2 – Créer le fichier `.env`

```bash
cd /opt/eticmont
cp .env.example .env
nano .env
```

**Valeurs à modifier impérativement :**

| Variable | À faire |
|----------|---------|
| `SECRET_KEY` | Générer une clé aléatoire : `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `POSTGRES_PASSWORD` | Choisir un mot de passe fort |
| `NGINX_PORT` | Changer si le port 80 est déjà pris |

Exemple de `.env` :
```env
SECRET_KEY=a1b2c3d4e5f6...votre_cle_aleatoire_ici
FLASK_ENV=production
POSTGRES_USER=eticmont
POSTGRES_PASSWORD=mon_mdp_fort_!2026
POSTGRES_DB=eticmont
POSTGRES_HOST=postgres-db
POSTGRES_PORT=5432
NGINX_PORT=80
POSTGRES_EXTERNAL_PORT=5433
BACKUP_DIR=/home/postgres-backups
```

---

## Étape 3 – Premier déploiement (base vide)

> **Si vous avez déjà une base de données existante, passez à l'étape 3b.**

```bash
cd /opt/eticmont

# Créer le dossier de backups sur l'hôte
sudo mkdir -p /home/postgres-backups

# Construire et lancer les conteneurs
docker compose -f docker-compose.prod.yml up -d --build
```

L'application crée automatiquement les tables au démarrage (`CREATE TABLE IF NOT EXISTS`).

Vérifier que tout tourne :
```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f
```

L'application est accessible sur `http://emb.boblabs.eu`.

---

## Étape 3b – Premier déploiement (avec restauration d'une base existante)

```bash
cd /opt/eticmont

# 1. Lancer d'abord uniquement PostgreSQL
docker compose -f docker-compose.prod.yml up -d postgres-db

# 2. Attendre que le conteneur soit prêt
docker compose -f docker-compose.prod.yml logs postgres-db
# → attendre "database system is ready to accept connections"

# 3. Copier le fichier de backup dans le dossier de backups
cp /chemin/vers/votre/db_backup_XXXXXXXX.sql /home/postgres-backups/

# 4. Restaurer la base (adapter le nom du conteneur et du fichier)
CONTAINER=$(docker compose -f docker-compose.prod.yml ps -q postgres-db)
docker exec -i "$CONTAINER" psql -U eticmont -d eticmont < /home/postgres-backups/db_backup_XXXXXXXX.sql

# 5. Vérifier les tables
docker exec -it "$CONTAINER" psql -U eticmont -d eticmont -c "\dt"

# 6. Lancer le reste de la stack
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Étape 4 – Vérification

```bash
# Vérifier que les 3 conteneurs tournent
docker compose -f docker-compose.prod.yml ps

# Tester l'accès HTTP
curl -I http://localhost

# Vérifier les logs pour erreurs éventuelles
docker compose -f docker-compose.prod.yml logs app-flask
docker compose -f docker-compose.prod.yml logs nginx
```

---

## Mise à jour de l'application (sans toucher à la base)

```bash
cd /opt/eticmont

# 1. Récupérer les nouveaux fichiers (rsync, git pull, scp…)

# 2. Reconstruire UNIQUEMENT l'app et nginx (PAS la base)
docker compose -f docker-compose.prod.yml up -d --build app-flask nginx

# Cela ne touche PAS au conteneur postgres-db ni au volume postgres-data.
```

> **Important** : Ne jamais lancer `docker compose down -v` — le flag `-v` SUPPRIME les volumes (= votre base de données).

---

## Sauvegarde de la base de données

### Backup manuel
```bash
CONTAINER=$(docker compose -f docker-compose.prod.yml ps -q postgres-db)
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
docker exec "$CONTAINER" pg_dump -U eticmont eticmont > /home/postgres-backups/db_backup_$TIMESTAMP.sql
echo "Backup: /home/postgres-backups/db_backup_$TIMESTAMP.sql"
```

### Backup automatique (crontab)
```bash
# Éditer le crontab
crontab -e

# Ajouter une ligne pour un backup quotidien à 2h du matin :
0 2 * * * CONTAINER=$(docker ps -qf "name=postgres-db") && docker exec "$CONTAINER" pg_dump -U eticmont eticmont > /home/postgres-backups/db_backup_$(date +\%Y\%m\%d_\%H\%M\%S).sql
```

---

## Restauration de la base depuis un backup

```bash
CONTAINER=$(docker compose -f docker-compose.prod.yml ps -q postgres-db)
BACKUP_FILE=/home/postgres-backups/db_backup_XXXXXXXX.sql

# Terminer les connexions existantes et supprimer/recréer la base
docker exec -i "$CONTAINER" psql -U eticmont -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'eticmont'; DROP DATABASE IF EXISTS eticmont;"
docker exec -i "$CONTAINER" psql -U eticmont -d postgres -c "CREATE DATABASE eticmont;"

# Restaurer
docker exec -i "$CONTAINER" psql -U eticmont -d eticmont < "$BACKUP_FILE"

# Vérifier
docker exec -it "$CONTAINER" psql -U eticmont -d eticmont -c "\dt"
```

---

## Arrêt / Redémarrage

```bash
# Arrêter tout (la base est préservée dans le volume)
docker compose -f docker-compose.prod.yml down

# Redémarrer
docker compose -f docker-compose.prod.yml up -d
```

---

## Commandes utiles

| Action | Commande |
|--------|---------|
| Voir les logs en temps réel | `docker compose -f docker-compose.prod.yml logs -f` |
| Logs d'un service | `docker compose -f docker-compose.prod.yml logs app-flask` |
| Redémarrer un service | `docker compose -f docker-compose.prod.yml restart app-flask` |
| Shell dans le conteneur app | `docker compose -f docker-compose.prod.yml exec app-flask sh` |
| Shell PostgreSQL | `docker compose -f docker-compose.prod.yml exec postgres-db psql -U eticmont -d eticmont` |
| Voir les volumes | `docker volume ls` |

---

## Ajout HTTPS avec Let's Encrypt

Deux fichiers nginx sont fournis :
- `nginx/nginx.conf` – HTTP uniquement (utilisé par défaut au premier déploiement)
- `nginx/nginx-ssl.conf` – HTTPS + redirection HTTP→HTTPS (à activer après obtention du certificat)

Le `docker-compose.prod.yml` monte déjà les certificats Let's Encrypt en lecture seule.

### 1. Installer Certbot via snap

> **Important** : La version apt de certbot est souvent cassée sur Ubuntu 22.04+. Utiliser snap :

```bash
# Supprimer l'ancienne version apt si installée
sudo apt remove certbot -y

# Installer via snap
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/bin/certbot
```

### 2. Obtenir le certificat SSL

```bash
# Arrêter nginx (port 80 doit être libre pour certbot --standalone)
docker compose -f docker-compose.prod.yml stop nginx

# Obtenir le certificat
sudo certbot certonly --standalone -d emb.boblabs.eu

# Vérifier que le certificat existe
sudo ls /etc/letsencrypt/live/emb.boblabs.eu/
```

### 3. Activer la config HTTPS

```bash
# Remplacer la config HTTP par la config SSL
cp nginx/nginx-ssl.conf nginx/nginx.conf

# Relancer la stack
docker compose -f docker-compose.prod.yml up -d --build
```

L'application est accessible sur `https://emb.boblabs.eu`. Le trafic HTTP est automatiquement redirigé vers HTTPS.

### 4. Renouvellement automatique du certificat

```bash
# Tester le renouvellement (dry run)
sudo certbot renew --dry-run

# Ajouter un cron pour le renouvellement automatique
crontab -e

# Ajouter cette ligne (renouvellement tous les jours à 3h) :
0 3 * * * certbot renew --quiet --pre-hook "docker compose -f /opt/eticmont/docker-compose.prod.yml stop nginx" --post-hook "docker compose -f /opt/eticmont/docker-compose.prod.yml start nginx"
```

---

## Firewall (UFW)

### Configuration des règles

```bash
# Activer UFW si pas déjà fait
sudo ufw enable

# Autoriser SSH (IMPORTANT : à faire AVANT d'activer UFW sinon vous perdez l'accès)
sudo ufw allow 22/tcp

# Autoriser HTTP et HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Interdire l'accès direct à PostgreSQL depuis l'extérieur
# (le port 5433 est exposé par Docker — UFW ne bloque PAS les ports Docker par défaut)
# Pour bloquer l'accès externe à PostgreSQL, voir la note ci-dessous.

# Vérifier les règles
sudo ufw status verbose
```

> **Note importante** : Docker manipule directement iptables et **contourne UFW**. Si `POSTGRES_EXTERNAL_PORT` est exposé dans docker-compose, il sera accessible même avec UFW. Pour sécuriser PostgreSQL :
>
> 1. **Option recommandée** – Ne pas exposer le port PostgreSQL vers l'extérieur. Modifier `docker-compose.prod.yml` :
>    ```yaml
>    ports:
>      - "127.0.0.1:${POSTGRES_EXTERNAL_PORT:-5433}:5432"
>    ```
>    Cela limite l'accès à localhost uniquement.
>
> 2. **Option alternative** – Ajouter une règle dans `/etc/ufw/after.rules` pour filtrer les ports Docker.

### Résumé des ports ouverts

| Port | Usage |
|------|-------|
| 22 | SSH |
| 80 | HTTP (redirigé vers HTTPS) |
| 443 | HTTPS |

---

## Fail2ban

### Installation et configuration

```bash
   sudo apt install fail2ban
```

### Configuration pour Nginx

```bash
sudo tee /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
banaction = ufw

[sshd]
enabled = true
port    = ssh
logpath = %(sshd_log)s

[nginx-http-auth]
enabled  = true
port     = http,https
logpath  = /var/log/nginx/error.log

[nginx-botsearch]
enabled  = true
port     = http,https
logpath  = /var/log/nginx/access.log

[nginx-badbots]
enabled  = true
port     = http,https
logpath  = /var/log/nginx/access.log
EOF
```

> **Note** : Les logs Nginx sont dans le conteneur Docker. Pour que fail2ban puisse les lire, ajouter un volume de logs dans `docker-compose.prod.yml` pour le service nginx :
> ```yaml
> volumes:
>   - nginx-logs:/var/log/nginx
> ```
> Et monter ce même volume ou un bind mount accessible depuis l'hôte :
> ```yaml
> volumes:
>   - ./logs/nginx:/var/log/nginx
> ```
> Puis adapter les `logpath` dans la config fail2ban vers `./logs/nginx/`.

### Démarrer fail2ban

```bash
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# Vérifier le statut
sudo fail2ban-client status
sudo fail2ban-client status sshd
```

---

## Résumé des fichiers de production

| Fichier | Rôle |
|---------|------|
| `docker-compose.prod.yml` | Orchestration des 3 services |
| `Dockerfile.prod` | Image de l'app Flask + Gunicorn |
| `gunicorn.conf.py` | Configuration Gunicorn (workers, port) |
| `nginx/nginx.conf` | Configuration Nginx reverse proxy |
| `.env` | Variables d'environnement (secrets) |
| `.env.example` | Template du `.env` |

---

## Ce qui ne change PAS entre les déploiements

- Le volume Docker `postgres-data` (vos données)
- Le dossier `/home/postgres-backups` sur l'hôte
- Le fichier `.env` sur le serveur (une fois configuré)
