#!/usr/bin/env bash
# restore.sh


set -u

DB_USER="${POSTGRES_USER:-barq_app}"
DB_NAME="${POSTGRES_DB:-barq_tasks}"
CONTAINER="postgres"

if [ $# -ne 1 ]; then
    echo "Usage: ./restore.sh <backup_file.sql>"
    exit 2
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "FAIL: backup file not found: ${BACKUP_FILE}"
    exit 1
fi

echo "== Checking postgres container is running =="
if ! docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true; then
    echo "FAIL: ${CONTAINER} container is not running"
    exit 1
fi
echo "PASS: ${CONTAINER} is running"

echo "== Restoring ${BACKUP_FILE} into ${DB_NAME} =="
if docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" < "$BACKUP_FILE" > /tmp/restore_output.log 2>&1; then
    echo "PASS: restore command completed"
else
    echo "FAIL: restore command failed, see /tmp/restore_output.log"
    tail -20 /tmp/restore_output.log
    exit 1
fi

echo "== Verifying data is present after restore =="
COUNT=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM records;" 2>/dev/null | tr -d '[:space:]')

if [ -n "$COUNT" ] && [ "$COUNT" -ge 1 ] 2>/dev/null; then
    echo "PASS: restored table contains ${COUNT} row(s)"
else
    echo "FAIL: could not confirm rows after restore (got: '${COUNT}')"
    exit 1
fi

echo ""
echo "Restore complete from: ${BACKUP_FILE}"