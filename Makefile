.PHONY: up down logs build backend frontend test test-backend test-frontend seed migrate lint db-backup db-restore-check

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f backend worker

build:
	docker compose build

# --- local development without docker ---
backend:
	cd backend && uvicorn app.main:app --reload --port 8000

worker:
	cd backend && python -m app.worker.main

frontend:
	cd frontend && npm run dev

migrate:
	cd backend && alembic upgrade head

seed:
	cd backend && python -m app.seed

test: test-backend test-frontend

test-backend:
	cd backend && pytest

test-frontend:
	cd frontend && npm run typecheck && npm run build

# --- database backups (run pg_dump/pg_restore inside the postgres container) ---
# See docs/DATABASE.md, "Backups and restore". BACKUP_KEEP=N overrides the retention (14).
db-backup:
	sh backend/scripts/db_backup.sh

# Restore the newest dump into a scratch DB, check tables + alembic_version, drop it.
db-restore-check:
	sh backend/scripts/db_restore_check.sh
