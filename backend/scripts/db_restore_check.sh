#!/bin/sh
# Prove the newest backup restores: restore it into the scratch database
# jobpilot_restore_check, assert it has the expected base tables across the five schemas and
# the same alembic_version as the live database, then drop the scratch database.
#
#   sh backend/scripts/db_restore_check.sh            # or: make db-restore-check
#
# The live database is only read (SELECT on alembic_version). The scratch database is dropped
# on exit whether the check passes or fails.
# Environment: BACKUP_DIR (default backups), EXPECTED_TABLES (default 35),
#              POSTGRES_USER / POSTGRES_DB (default jobpilot / jobpilot).
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"

SCRATCH=jobpilot_restore_check
DIR=${BACKUP_DIR:-backups}
EXPECTED_TABLES=${EXPECTED_TABLES:-35}
EXPECTED_SCHEMAS=5
DB_USER=${POSTGRES_USER:-jobpilot}
LIVE_DB=${POSTGRES_DB:-jobpilot}
SCHEMA_FILTER="table_type = 'BASE TABLE' AND table_schema IN ('master','unified','transaction','media','audit')"

psql_q() {  # psql_q DB SQL
    docker compose exec -T postgres psql -U "$DB_USER" -d "$1" -v ON_ERROR_STOP=1 -Atc "$2"
}
drop_scratch() {
    psql_q postgres "DROP DATABASE IF EXISTS $SCRATCH" > /dev/null && echo "restore-check: dropped $SCRATCH"
}

DUMP=$(cd "$DIR" 2>/dev/null && ls -1t jobpilot-*.dump 2>/dev/null | head -n 1 || true)
if [ -z "$DUMP" ]; then
    echo "restore-check: no jobpilot-*.dump in $DIR; run make db-backup first" >&2
    exit 1
fi
DUMP="$DIR/$DUMP"
echo "restore-check: newest dump is $DUMP"

LIVE_VERSION=$(psql_q "$LIVE_DB" "SELECT string_agg(version_num, ',') FROM alembic_version")
echo "restore-check: live $LIVE_DB alembic_version=$LIVE_VERSION"

# Start clean (a previous run may have been killed) and always clean up afterwards.
psql_q postgres "DROP DATABASE IF EXISTS $SCRATCH" > /dev/null
trap drop_scratch EXIT

sh "$ROOT/backend/scripts/db_restore.sh" "$SCRATCH" "$DUMP"

TABLES=$(psql_q "$SCRATCH" "SELECT count(*) FROM information_schema.tables WHERE $SCHEMA_FILTER")
SCHEMAS=$(psql_q "$SCRATCH" "SELECT count(DISTINCT table_schema) FROM information_schema.tables WHERE $SCHEMA_FILTER")
VERSION=$(psql_q "$SCRATCH" "SELECT string_agg(version_num, ',') FROM alembic_version")

FAIL=0
if [ "$TABLES" != "$EXPECTED_TABLES" ]; then
    echo "restore-check: FAIL base tables=$TABLES, expected $EXPECTED_TABLES" >&2; FAIL=1
fi
if [ "$SCHEMAS" != "$EXPECTED_SCHEMAS" ]; then
    echo "restore-check: FAIL schemas with tables=$SCHEMAS, expected $EXPECTED_SCHEMAS" >&2; FAIL=1
fi
if [ "$VERSION" != "$LIVE_VERSION" ]; then
    echo "restore-check: FAIL alembic_version=$VERSION, live has $LIVE_VERSION" >&2; FAIL=1
fi
if [ "$FAIL" -ne 0 ]; then
    exit 1
fi
echo "restore-check: PASS $DUMP -> $SCRATCH: $TABLES base tables in $SCHEMAS schemas, alembic_version=$VERSION matches live"
