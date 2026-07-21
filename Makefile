.PHONY: setup build up down restart logs migrate seed test lint format backup restore reset bench

setup:
	cp -n .env.example .env || true
	@echo "Edit .env and set OPENROUTER_API_KEY, then run 'make build up migrate seed'."

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python scripts/seed_authority_library.py
	docker compose exec api python scripts/seed_sonohl_example.py

test:
	docker compose exec api pytest
	cd frontend && npm test --if-present

lint:
	docker compose exec api ruff check app
	cd frontend && npm run lint --if-present

format:
	docker compose exec api ruff format app
	cd frontend && npm run format --if-present

backup:
	docker compose exec api python scripts/backup.py

restore:
	docker compose exec api python scripts/restore.py $(FILE)

reset:
	docker compose down -v

# quick_scan regression harness (10 fixtures in backend/benchmark_suite.json).
# DRY_RUN_LLM=1: free/fast, scripted LLM responses, real HTTP to openFDA/CMS
# (both free/keyless) -- safe to run on every pipeline/prompt change.
# Bare `make bench`: real LLM calls too -- costs real money, run deliberately
# to sign off a change, not on every commit.
bench:
	docker compose exec -e DRY_RUN_LLM=$(DRY_RUN_LLM) api python -m app.bench.run_benchmark
