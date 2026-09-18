#!/usr/bin/env bash
set -euo pipefail

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[entrypoint] running database migrations"
  alembic upgrade head
fi

if [ "${RUN_SEED:-false}" = "true" ]; then
  echo "[entrypoint] seeding demo data (idempotent)"
  python -m app.seed || echo "[entrypoint] seed failed (continuing)"
fi

exec "$@"
