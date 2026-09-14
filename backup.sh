#!/usr/bin/env bash
# backup.sh

set -u

DB_USER="${POSTGRES_USER:-barq_app}"
DB_NAME="${POSTGRES_DB:-barq_tasks}"
CONTAINER="postgres"
BACKUP_DIR="./backups"
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
BACKUP_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.sql"

mkdir -p "$BACKUP_DIR"

echo "== Checking postgres container is running =="
if ! docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true; then
    echo "FAIL: ${CONTAINER} container is not running"
    exit 1
fi
echo "PASS: ${CONTAINER} is running"

echo "== Creating dump (plain SQL, with clean/if-exists for easy restore) =="
if docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" \
    --format=plain --clean --if-exists > "$BACKUP_FILE"; then
    echo "PASS: dump written to ${BACKUP_FILE}"
else
    echo "FAIL: pg_dump failed"
    rm -f "$BACKUP_FILE"
    exit 1
fi

if [ -s "$BACKUP_FILE" ]; then
    LINES=$(wc -l < "$BACKUP_FILE")
    echo "PASS: backup file is non-empty (${LINES} lines)"
else
    echo "FAIL: backup file is empty"
    exit 1
fi

echo ""
echo "Backup complete: ${BACKUP_FILE}"