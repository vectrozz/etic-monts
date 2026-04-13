#!/bin/bash

BACKUP_DIR=/home/postgres-backups
DB_CONTAINER=db-postgres-db-1
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE=$BACKUP_DIR/db_backup_$TIMESTAMP.sql

mkdir -p $BACKUP_DIR

docker exec $DB_CONTAINER pg_dump -U eticmont eticmont > $BACKUP_FILE

echo "Backup completed: $BACKUP_FILE"
