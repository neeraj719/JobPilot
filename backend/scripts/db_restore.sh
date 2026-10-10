#!/bin/sh
# Restore a pg_dump custom-format file into a named database.
#
#   sh backend/scripts/db_restore.sh TARGET_DB DUMP_FILE
#   FORCE=1 sh backend/scripts/db_restore.sh jobpilot backups/jobpilot-....dump   # over the live DB
#
# pg_restore runs inside the compose "postgres" container with the dump piped in, so nothing
# PostgreSQL-related has to be installed on the host. The target database is created if it
# does not exist. The restore uses --clean --if-exists --no-owner and runs in a single
# transaction: it either applies completely or leaves the target as it was.
#
# Restoring over the live database (POSTGRES_DB, default jobpilot) is refused unless FORCE=1.
# Stop the API and worker first (docker compose stop backend worker, or stop uvicorn and the
# worker process): open connections hold locks that block the DROPs.
# See docs/DATABASE.md, "Backups and restore".
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)

if [ $# -ne 2 ]; then
    echo "usage: db_restore.sh TARGET_DB DUMP_FILE" >&2
    exit 2
fi
TARGET=$1
DUMP=$2
DB_USER=${POSTGRES_USER:-jobpilot}
LIVE_DB=${POSTGRES_DB:-jobpilot}

# Resolve the dump path before changing directory, so relative paths work from anywhere.
case $DUMP in
    /* | [A-Za-z]:*) ;;
    *) DUMP="$(pwd)/$DUMP" ;;
esac
cd "$ROOT"

if [ ! -s "$DUMP" ]; then
    echo "db_restore: dump file '$DUMP' is missing or empty" >&2
    exit 2
fi
# The name is interpolated into SQL below, so only allow plain lower-case identifiers.
if ! printf '%s' "$TARGET" | grep -qE '^[a-z_][a-z0-9_]{0,62}$'; then
    echo "db_restore: '$TARGET' is not a plain lower-case database name" >&2
    exit 2
fi
case $TARGET in
    postgres | template0 | template1)
        echo "db_restore: refusing to restore into system database '$TARGET'" >&2
        exit 2 ;;
esac
if [ "$TARGET" = "$LIVE_DB" ] || [ "$TARGET" = jobpilot ]; then
    if [ "${FORCE:-}" != 1 ]; then
        echo "db_restore: '$TARGET' is the live database; refusing without FORCE=1." >&2
        echo "db_restore: stop the API and worker first, then: FORCE=1 sh backend/scripts/db_restore.sh $TARGET $2" >&2
        exit 3
    fi
    echo "db_restore: FORCE=1 set, restoring over live database '$TARGET'"
fi

psql_q() {  # psql_q DB SQL  -> unaligned, tuples-only output
    docker compose exec -T postgres psql -U "$DB_USER" -d "$1" -v ON_ERROR_STOP=1 -Atc "$2"
}

EXISTS=$(psql_q postgres "SELECT 1 FROM pg_database WHERE datname = '$TARGET'")
if [ "$EXISTS" != 1 ]; then
    echo "db_restore: creating database $TARGET"
    psql_q postgres "CREATE DATABASE \"$TARGET\"" > /dev/null
fi

echo "db_restore: restoring $DUMP into $TARGET"
if ! docker compose exec -T postgres pg_restore -U "$DB_USER" -d "$TARGET" \
        --clean --if-exists --no-owner --single-transaction --exit-on-error < "$DUMP"; then
    echo "db_restore: pg_restore failed; the transaction was rolled back" >&2
    exit 1
fi

VERSION=$(psql_q "$TARGET" "SELECT string_agg(version_num, ',') FROM alembic_version" 2>/dev/null || echo "none")
TABLES=$(psql_q "$TARGET" "SELECT count(*) FROM information_schema.tables WHERE table_type = 'BASE TABLE' AND table_schema IN ('master','unified','transaction','media','audit')")
SCHEMAS=$(psql_q "$TARGET" "SELECT count(DISTINCT table_schema) FROM information_schema.tables WHERE table_type = 'BASE TABLE' AND table_schema IN ('master','unified','transaction','media','audit')")
echo "restore OK: database=$TARGET alembic_version=${VERSION:-none} tables=$TABLES schemas=$SCHEMAS"
