#!/bin/sh
# Back up the live JobPilot database to backups/jobpilot-YYYYMMDD-HHMMSS.dump.
#
# pg_dump runs inside the compose "postgres" container, so nothing PostgreSQL-related has to
# be installed on the host. Works under Git Bash on Windows as well as Linux/macOS sh.
#
#   sh backend/scripts/db_backup.sh            # or: make db-backup
#
# Environment:
#   BACKUP_KEEP   how many dumps to keep in the backup directory (default 14)
#   BACKUP_DIR    where dumps go, relative to the repo root or absolute (default backups)
#   POSTGRES_USER / POSTGRES_DB   default jobpilot / jobpilot, as in docker-compose.yml
#
# A dump is only kept if it is non-empty and "pg_restore --list" can read it; retention runs
# only after that check passes, so a failed backup never deletes a good one.
# See docs/DATABASE.md, "Backups and restore".
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"

KEEP=${BACKUP_KEEP:-14}
DIR=${BACKUP_DIR:-backups}
DB_USER=${POSTGRES_USER:-jobpilot}
DB_NAME=${POSTGRES_DB:-jobpilot}
APP_SCHEMAS='master unified transaction media audit'

case $KEEP in
    '' | *[!0-9]* | 0) echo "db_backup: BACKUP_KEEP must be a positive integer, got '$KEEP'" >&2; exit 2 ;;
esac

mkdir -p "$DIR"
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="$DIR/jobpilot-$STAMP.dump"
PARTIAL="$OUT.partial"
LIST=$(mktemp)
trap 'rm -f "$PARTIAL" "$LIST"' EXIT

if [ -e "$OUT" ]; then
    echo "db_backup: $OUT already exists, refusing to overwrite" >&2
    exit 1
fi

# 1. Dump. Written to a .partial file first so an interrupted run never looks like a backup.
if ! docker compose exec -T postgres pg_dump -U "$DB_USER" -d "$DB_NAME" --format=custom > "$PARTIAL"; then
    echo "db_backup: pg_dump failed" >&2
    exit 1
fi

# 2. Verify: non-empty, and readable by pg_restore (run in the container, file piped in).
if [ ! -s "$PARTIAL" ]; then
    echo "db_backup: dump is empty" >&2
    exit 1
fi
if ! docker compose exec -T postgres pg_restore --list < "$PARTIAL" > "$LIST"; then
    echo "db_backup: pg_restore --list could not read the dump" >&2
    exit 1
fi
mv "$PARTIAL" "$OUT"

# 3. Retention: keep the newest $KEEP dumps (by modification time), delete the rest.
#    Only files named jobpilot-*.dump are considered; .partial files and anything else are left alone.
DELETED=0
for old in $(cd "$DIR" && ls -1t jobpilot-*.dump 2>/dev/null | tail -n +"$((KEEP + 1))"); do
    rm -f "$DIR/$old"
    echo "db_backup: retention removed $DIR/$old"
    DELETED=$((DELETED + 1))
done
KEPT=$(cd "$DIR" && ls -1 jobpilot-*.dump 2>/dev/null | wc -l | tr -d ' ')

# 4. One summary line. TOC table lines look like "215; 1259 16390 TABLE audit audit_logs jobpilot".
#    "TABLE DATA" lines (one per table with rows) are excluded so each table counts once.
TOTAL=$(grep -E '^[0-9]+; [0-9]+ [0-9]+ TABLE ' "$LIST" | grep -vc ' TABLE DATA ' || true)
APP=0
for s in $APP_SCHEMAS; do
    n=$(grep -cE "^[0-9]+; [0-9]+ [0-9]+ TABLE $s " "$LIST" || true)
    APP=$((APP + n))
done
BYTES=$(wc -c < "$OUT" | tr -d ' ')
KB=$(( (BYTES + 1023) / 1024 ))
echo "backup OK: $OUT  size=${KB} KB ($BYTES bytes)  tables=$TOTAL ($APP in app schemas, $((TOTAL - APP)) other)  kept=$KEPT/$KEEP removed=$DELETED"
