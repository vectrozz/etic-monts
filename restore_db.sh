#!/bin/bash
# ------------------------------------------------------------
# Script : restore_db.sh
# Objectif : Supprimer et recréer la base "eticmont" proprement,
# puis restaurer depuis un fichier SQL de backup.
# ------------------------------------------------------------

# Nom du conteneur PostgreSQL (modifie-le si différent)
CONTAINER_NAME="db-postgres-db-1"

# Nom de la base et de l'utilisateur
DB_NAME="eticmont"
DB_USER="eticmont"

# Fichier de backup (chemin sur l’hôte)
BACKUP_FILE="/home/postgres-backups/db_backup_20250915_000001.sql"

# Vérifier que le fichier de backup existe
if [ ! -f "$BACKUP_FILE" ]; then
  echo "❌ Erreur : le fichier de backup n'existe pas à $BACKUP_FILE"
  exit 1
fi

echo "🚀 Début de la restauration de la base '$DB_NAME' depuis $BACKUP_FILE ..."
echo "------------------------------------------------------------"

# 1️⃣ Supprimer la base si elle existe
docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d postgres -c \
"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME'; DROP DATABASE IF EXISTS $DB_NAME;"

# 2️⃣ Recréer la base vide
docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d postgres -c "CREATE DATABASE $DB_NAME;"

# 3️⃣ Restaurer le contenu du backup
docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" < "$BACKUP_FILE"

echo "✅ Restauration terminée avec succès !"
echo "------------------------------------------------------------"

# 4️⃣ (Optionnel) Vérifier que les tables existent
docker exec -it "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -c "\dt"
