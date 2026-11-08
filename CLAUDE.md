# CLAUDE.md

## Project
Relay reporting app. Ticket DASH-247: help a customer admin see whether their recent
activity (calls, leads, appointments) is normal for them, per account and per location.
Out of scope: auth, alerting, forecasting/predictive ML, production infra.

## Ticket gate
Never write application code without an approved plan: PLAN.md for the overall
feature, and plans/<ticket>.md for each ticket. If the plan for the current work
doesn't exist or I haven't approved it, stop and ask.

## Stack (planned)
- PostgreSQL 16 (docker-compose)
- Backend: Python, FastAPI, SQLAlchemy 2.0 (sync), Alembic, Pydantic v2, pytest
- Frontend: React + TypeScript + Vite
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

## Commands
(to be added as the project is scaffolded)
