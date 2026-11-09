# CLAUDE.md

## Project
Relay reporting app. Ticket DASH-247: help a customer admin see whether their recent
activity (calls, leads, appointments) is normal for them, per account and per location.
Out of scope: auth, alerting, forecasting/predictive ML, production infra.

## Ticket gate
Never write application code without an approved plan: PLAN.md for the overall
feature, and plans/<ticket>.md for each ticket. If the plan for the current work
doesn't exist or I haven't approved it, stop and ask.

## Stack
- PostgreSQL 16 (docker-compose)
- Backend: Python 3.12, FastAPI, SQLAlchemy 2.0 (sync), Alembic, Pydantic v2 + pydantic-settings,
  psycopg 3, uv, pytest, ruff, mypy (strict)
- Frontend: React + TypeScript (strict) + Vite, Vitest + React Testing Library
- Keep it simple: no async SQLAlchemy, no task queues, no extra state libraries.

## Data rules
- `data/schema.sql` and `data/seed.sql` are immutable. Never edit, regenerate or extend them.
- `occurred_at` is TIMESTAMP WITHOUT TIME ZONE holding UTC. To get account-local time, always use:
  `(occurred_at AT TIME ZONE 'UTC') AT TIME ZONE accounts.timezone`
  A single `AT TIME ZONE tz` converts in the wrong direction.
- Timezone is per account (IANA name, DST-aware). Never use fixed offsets.
- The seed ends on 2026-07-27. Never use now() to decide the reporting week.
- Data facts and quirks: see docs/data-profile.md.

## Workflow
- One ticket at a time. Before coding a ticket, write a short plan in plans/ and wait for my approval.
- Tests first for aggregation logic, using small fixtures with hand-computed expected values.
- Don't commit unless I ask. Conventional commit messages (feat:, fix:, test:, docs:, chore:).
- If something in the data or the spec is ambiguous, ask instead of guessing.
- When a ticket makes a design decision with real alternatives, add an entry to docs/decisions.md in the same change.

## Commands
Only Docker and make are needed. Everything runs in containers.
- `make up`: build and start db + api + web (a one-shot `migrate` service applies migrations first; `-V` renews web's node_modules volume)
- `make down`: stop (keeps the DB volume). `make reset`: stop and drop the DB volume
- `make migrate`: apply migrations. `make seed`: truncate and reload `data/seed.sql` (destructive, idempotent)
- `make psql`: psql on the dev database. `make logs`: follow api logs
- `make check`: the quality gate: `make lint` (ruff check + format check), `make typecheck` (mypy + `tsc --noEmit`),
  `make test` (pytest + vitest; the frontend steps run in the `web` container). Tests use their own databases
  (`relay_test`, `relay_migrations_test`), never the dev one
- API: http://127.0.0.1:8000, `GET /api/health`. Web (Vite dev server, proxies `/api` to the API): http://127.0.0.1:5173
