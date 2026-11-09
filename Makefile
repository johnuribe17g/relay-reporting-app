RUN := docker compose run --rm api

.PHONY: help up down reset migrate seed psql logs lint typecheck test check

help: ## List targets
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

up: ## Start db + api (migrations apply on startup)
	docker compose up -d --build --wait

down: ## Stop everything (keeps the DB volume)
	docker compose down

reset: ## Stop everything and DROP the DB volume
	docker compose down -v

migrate: ## Apply migrations
	docker compose build api
	docker compose run --rm migrate

seed: ## Load data/seed.sql (destructive: truncates and reloads)
	$(RUN) python -m app.seed

psql: ## Open psql on the dev database
	docker compose exec db psql -U relay relay

logs: ## Follow api logs
	docker compose logs -f api

lint: ## ruff check + format check
	$(RUN) ruff check .
	$(RUN) ruff format --check .

typecheck: ## mypy
	$(RUN) mypy

test: ## pytest
	$(RUN) pytest -q

check: lint typecheck test ## Quality gate: lint, typecheck, tests (all in the api container)
