RUN := docker compose run --rm api
WEB := docker compose run --rm --no-deps web

.PHONY: help up down reset migrate seed psql logs lint typecheck test check

help: ## List targets
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

up: ## Start db + api + web (migrations apply on startup; -V renews web's node_modules)
	docker compose up -d --build --wait -V

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

typecheck: ## mypy + tsc --noEmit
	$(RUN) mypy
	$(WEB) npm run typecheck

test: ## pytest + vitest
	$(RUN) pytest -q
	$(WEB) npm test

check: lint typecheck test ## Quality gate: lint, typecheck, tests (backend in the api container, frontend in the web one)
