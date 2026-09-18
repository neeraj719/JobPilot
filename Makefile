.PHONY: up down logs build backend frontend test test-backend test-frontend seed migrate lint

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
