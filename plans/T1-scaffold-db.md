# T1: Scaffold + DB

Status: **APPROVED**, with the decisions recorded in §9. Implementation pauses after the deny rules and the
compose/Makefile/health skeleton, for review before the migrations.
Source: PLAN.md §3, §7, §8, §9, §10. Data facts: docs/data-profile.md.
Branch: `feat/T1-scaffold-db` (PLAN §8: one branch per ticket). It already exists and is checked out. No commits until asked.

**In:** docker-compose (db + migrate + api), Alembic migrations 1 and 2, seed script, view tests,
FastAPI skeleton (health only), settings stub, pytest/ruff/mypy, Makefile, `permissions.deny` rules on `data/`.
**Out:** frontend, domain logic (baseline/verdict), report endpoints, ORM models, per-type logic.

## 1. Repo layout

```
docker-compose.yml          db, migrate (one-shot), api
Makefile
.env.example                compose has inline defaults, so .env is optional (see Q6)
.dockerignore
.claude/settings.json       committed; permissions.deny on data/ (§10). No script, no hook.
backend/
  Dockerfile                python:3.12-slim + uv; venv at /opt/venv (outside the bind mount)
  pyproject.toml            deps + ruff, mypy, pytest config
  uv.lock
  alembic.ini
  migrations/env.py         URL from settings; no target_metadata (no ORM models in T1)
  migrations/versions/0001_create_tables.py
  migrations/versions/0002_clean_events_view.py
  app/__init__.py
  app/main.py               FastAPI app, GET /api/health
  app/settings.py           pydantic-settings stub: database_url, test_database_url
  app/db.py                 sync engine factory (create_engine, no async)
  app/seed.py               `python -m app.seed`; also importable (load_seed(conn))
  tests/conftest.py         test-DB lifecycle + fixtures
  tests/test_health.py  test_migrations.py  test_clean_events.py  test_seed.py
CLAUDE.md                   "Commands" section filled in (T1 done-criterion)
```

Compose mounts `./backend:/app` (live code, no rebuild for `make check`) and `./data:/data:ro`.
The read-only mount means the container cannot modify `data/` either.

## 2. Migration 1: tables

`op.create_table` (typed and reversible), matching `data/schema.sql` column for column:

| Column | schema.sql | Migration 1 | Note |
|---|---|---|---|
| `accounts.id`, `activity_events.id` | `INTEGER PRIMARY KEY` | `INTEGER` PK, **no identity/serial** | Seed inserts explicit ids. `GENERATED ALWAYS` would reject them, and `BY DEFAULT` leaves the sequence at 1 so the first real insert collides. Ingest isn't in scope; see Q5. |
| `name`/`industry`/`timezone`, `location`/`event_type`/`outcome` | `VARCHAR(n)` | same `VARCHAR(n)` | |
| `created_at`, `occurred_at` | `TIMESTAMP` | `TIMESTAMP WITHOUT TIME ZONE` | Holds UTC. Not `timestamptz`: that would change what the stored value means and invert the CLAUDE.md conversion. |
| `duration_seconds`, `outcome` | `NULL` | nullable | |
| FK `account_id → accounts(id)` | yes | yes, named `fk_activity_events_account_id` | Seed inserts accounts first, so it loads. |
| Index | none | `ix_activity_events_account_id_occurred_at (account_id, occurred_at)` | PLAN §7. Not a performance claim at 12k rows. |

**Honest note on "adapted":** `schema.sql` is already valid PostgreSQL 16. No type needs translating.
The differences are only the Alembic form, explicit constraint names, and the one extra index.

**Deliberately NOT added** (each would stop the unmodified seed loading or hide a data problem):
- `UNIQUE` over the payload columns (the 12 duplicate pairs would fail the load; dedupe belongs in the view).
- `CHECK (event_type IN (...))` (unknown types must load and be caught by the DQ test, PLAN §3).
- `NOT NULL` on `outcome`/`duration_seconds` (about 3% / 4% are NULL).
- `CHECK` that `timezone` is valid IANA (not expressible in a CHECK). Failure mode: a bad zone makes
  every view query error. Mitigation: the seed test asserts all account zones exist in `pg_timezone_names`.
- A `locations` table (PLAN §3: keyed by `(account_id, location)`).

`downgrade()` drops the index then the tables (events first).
Faithfulness is tested, not just claimed (§6, `test_migrations.py`).

## 3. Migration 2: `clean_events`

The SQL lives in the migration file as a string and does not import from `app/`, so migrations stay frozen.

```sql
CREATE VIEW clean_events AS
WITH normalized AS (
    SELECT e.id,
           e.account_id,
           btrim(e.location, E' \t\r\n')                 AS location,    -- trim only, NO lower()
           lower(btrim(e.event_type, E' \t\r\n'))        AS event_type,
           e.occurred_at,
           e.duration_seconds,
           btrim(e.outcome, E' \t\r\n')                  AS outcome      -- NULL stays NULL
    FROM activity_events e
),
ranked AS (
    SELECT n.*,
           row_number() OVER (
               PARTITION BY account_id, location, event_type,
                            occurred_at, duration_seconds, outcome
               ORDER BY id
           ) AS rn
    FROM normalized n
)
SELECT r.id, r.account_id, r.location, r.event_type, r.occurred_at,
       r.duration_seconds, r.outcome,
       l.local_ts,
       date_trunc('week', l.local_ts)::date AS local_week      -- Monday, ISO, regardless of locale
FROM ranked r
JOIN accounts a ON a.id = r.account_id
CROSS JOIN LATERAL (
    SELECT (r.occurred_at AT TIME ZONE 'UTC') AT TIME ZONE a.timezone AS local_ts
) l
WHERE r.rn = 1;
```

`downgrade()`: `DROP VIEW clean_events`.

PLAN §3 rule → implementation:

| PLAN §3 rule | Where |
|---|---|
| Remove exact duplicates, keep lowest `id` | `row_number() … ORDER BY id`, `WHERE rn = 1` |
| `trim` text fields | `btrim(x, E' \t\r\n')` (see Q4: plain `trim()` only strips spaces) |
| `lower(event_type)` only, no case-folding of `location` | `lower()` on `event_type` alone |
| Expose `local_ts` and `local_week` once, double `AT TIME ZONE` | LATERAL subquery, the only place the conversion appears |
| Count by `event_type`; ignore `duration_seconds`/`outcome` | Both columns are exposed but not used by anything in T1. `outcome` stays in the view because it's part of the dedupe key. |
| Unknown `event_type` not silently dropped | The view has no filter on `event_type` |

**NULLs in the dedupe.** `PARTITION BY` (like `GROUP BY`/`DISTINCT`) treats NULLs as equal, so two rows with
`duration_seconds = NULL, outcome = NULL` land in one partition and collapse. A `NULL` vs `600` pair is a
different partition and both survive. I deliberately avoid a self-join or `NOT EXISTS` on `=`, because
`NULL = NULL` is unknown and would **silently keep NULL-bearing duplicates**. That isn't an edge case: every
`lead_created` and `appointment_set` row has NULL `duration_seconds` (profile §9), so a naive `=` dedupe would miss
duplicates for 2 of the 3 event types. Fixtures D2/D3 pin this down.

**Dedupe after normalization (my recommendation, small deviation from PLAN wording "exact").** Reasoning:
two rows differing only by whitespace/case of `event_type` (or trailing whitespace in `location`) are the
same real-world double-insert. And the dedupe key then equals what aggregation sees, so the view can never return
two rows that look identical after cleaning. Dedupe-before would keep both and inflate counts. Risk is
low because only whitespace and `event_type` case are normalized (distinct sites never merge). No effect on this
seed (no variants, profile §5/§6). Fixture N3 pins it. If you prefer strictly raw-exact, the change is
moving the `normalized` CTE below `ranked`. Q4.

## 4. Seed script (`python -m app.seed`)

- `load_seed(conn)` is **caller-managed**: it opens, commits and rolls back **no transaction of its own**. On the
  connection it is given, it reads `/data/seed.sql` (path from settings, default `/data/seed.sql`, read-only mount),
  runs `TRUNCATE activity_events, accounts;`, then executes the file's text.
  psycopg 3 sends a no-parameter multi-statement string via the simple-query protocol, so the file is
  executed **unmodified**, with no parsing or splitting on our side. Explicit ids mean no sequences to reset.
- **Atomic:** the CLI (`python -m app.seed`) wraps the call in `engine.begin()`. Any error rolls back the
  TRUNCATE too, so the DB is never left half-loaded, and a previous good load survives a failed reload.
  Tests call `load_seed(conn)` inside their own outer rolled-back transaction (§5). The atomicity test uses a
  SAVEPOINT (§6d), because in Postgres an error aborts the whole outer transaction.
- **Run twice:** the second run truncates and reloads, ending in the identical state (12,626 / 20). Tested.
  Rejected alternative: "skip if non-empty" can't detect a partial or edited table (Q7).
- Prints the two row counts. Does not assert them (tests do).
- No environment guard: tests call `load_seed(conn)` on the test DB by design. It is a dev-only tool and
  destructive by nature (the Makefile help says so).
- `make seed` = `docker compose run --rm api python -m app.seed`. `run` starts `db` and `migrate` first (via
  `depends_on`), so the tables exist.

## 5. docker-compose, env, test database

| Service | Image | Details |
|---|---|---|
| `db` | `postgres:16` | env `POSTGRES_USER/PASSWORD/DB` = `relay` (defaults inline). Named volume `pgdata`. Healthcheck `pg_isready -U relay -d relay` (interval 2s, retries 15). Published `127.0.0.1:5433:5432` for `make psql`/editor use, avoiding clashes with a host Postgres. |
| `migrate` | same build as `api` | `command: alembic upgrade head`. `depends_on: db (service_healthy)`. `restart: "no"`. One-shot. |
| `api` | `backend/Dockerfile` | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`. `depends_on: db (healthy), migrate (service_completed_successfully)`. Healthcheck: python one-liner (urllib) on `/api/health` (slim has no curl). Published `8000:8000`. |

- **Migrations on startup:** a separate `migrate` one-shot, not inside the api command. A failed migration is
  visible as its own failed service; `make check`/`make seed` don't depend on api starting; and no
  race if api ever scales. Risk to verify at implementation: `docker compose up --wait` with a one-shot that exits 0.
  Fallback (decided, §7): `make up` runs `docker compose run --rm migrate`, then `up -d --wait db api`. Never the api entrypoint.
- **Env vars:** `DATABASE_URL=postgresql+psycopg://relay:relay@db:5432/relay`,
  `TEST_DATABASE_URL=postgresql+psycopg://relay:relay@db:5432/relay_test`, `SEED_PATH=/data/seed.sql`.
  Local dev credentials only. Nothing secret, nothing committed except `.env.example`.
- **Test database:** `relay_test` on the same server, created by `conftest.py`, not by an init script
  (`/docker-entrypoint-initdb.d` only runs on a fresh volume, so it fails on any existing one).
  Session fixture:
  1. Safety guard: abort unless the DB name ends in `_test`.
  2. Connect to the maintenance DB `postgres` (autocommit); `DROP DATABASE IF EXISTS relay_test WITH (FORCE)`; `CREATE DATABASE relay_test`.
  3. `alembic upgrade head` against it, so the migrations are exercised from scratch every run.
  4. Per-test fixture: one connection, `BEGIN`, test inserts fixture rows, queries, then **`ROLLBACK`**. Tables are always
     empty between tests. The seed test does `load_seed(conn)` inside the same rolled-back transaction
     (`TRUNCATE` is transactional in Postgres), so no 2.4 MB reload is committed.
- **Second throwaway database for the migration round trip:** `relay_migrations_test`, created and dropped by its own
  fixture with the same `_test` name guard. `downgrade base` destroys the schema, so it must never run against
  `relay_test`, whose schema every other test relies on.
- The dev DB (`relay`) is never touched by tests.

## 6. Tests

Written first, run red against missing migrations, then green. Fixtures are rows
`(id, account, location, event_type, occurred_at UTC, duration, outcome)`. Weekday anchors: 2026-02-01 is a
Sunday (profile §3), so Mondays are 02-02, 02-09, 02-16, 02-23, 03-02, 03-09, …; 2026-07-20 is a Monday.
Offsets: Chicago CST −6 / CDT −5; Denver MST −7 / MDT −6; Phoenix MST −7 always; New York EDT −4 (summer);
Kolkata +5:30; US DST began **2026-03-08 02:00 local** = 08:00 UTC in Chicago, 09:00 UTC in Denver.
`local = UTC + offset`. `local_week` = the Monday on or before the local date.

Fixture accounts: **A1** Chicago, **A2** Denver, **A3** Phoenix, **A4** UTC, **A5** Asia/Kolkata, **A6** New York.
All dedupe fixtures use A1, location `Site A`, unless stated.

### 6a. Dedupe and normalization (`test_clean_events.py`)

| # | Input rows (id: type, occurred_at, duration, outcome) | Expected `clean_events` |
|---|---|---|
| D1 | 1: call, `2026-02-03 15:00:00`, 600, connected · 2: identical | 1 row, **id 1** |
| D2 | 3: lead, `2026-02-03 16:00:00`, NULL, NULL · 4: identical | 1 row, **id 3** (NULL = NULL for dedupe) |
| D3 | 5: lead, `…17:00:00`, NULL, 'open' · 6: lead, same time, 600, 'open' | **2 rows** (NULL ≠ 600) |
| D3b | 7: call, `…18:00:00`, 600, NULL · 8: same, 600, 'missed' | **2 rows** (NULL ≠ 'missed') |
| D4 | Base 9: call, `…19:00:00`, 600, connected, plus each of: 10: `…19:00:01` (+1 s) · 11: duration 601 · 12: type lead_created · 13: location `Site B` · 14: account A2 | **6 rows**, all kept (near-duplicates stay, profile §8) |
| D5 | 30, 10, 20 inserted in this order, all identical (call, `2026-02-04 09:00:00`, 300, connected) | 1 row, **id 10** (lowest id wins, non-consecutive) |
| D6 | Raw table `activity_events` after D1 | still **2 rows** (view never mutates) |
| N1 | 15: type `' Call_Received '` | `event_type = 'call_received'` |
| N2 | 16: location `' Site A\t'`, call, `2026-02-04 11:00:00`, 5, connected · 17: location `Site A`, call, `…12:00:00`, 5, connected · 18: location `site a`, call, `…13:00:00`, 5, connected | 3 rows. 16 and 17 → location `Site A` (trimmed); 18 stays `site a`. `count(distinct location)` = **2** (no case-folding) |
| N3 | 19: `call_received`, `2026-02-04 10:00:00`, 5, connected · 20: `' CALL_RECEIVED '`, same other columns | 1 row, **id 19** (dedupe after normalization) |
| N4 | 21: type `phone_call` | row present, `event_type = 'phone_call'` (not dropped; DQ test can see it) |
| N5 | `select column_name, data_type from information_schema.columns where table_name='clean_events'` | exactly `id, account_id, location, event_type, occurred_at, duration_seconds, outcome, local_ts, local_week` with `local_ts` = `timestamp without time zone`, `local_week` = `date` |

### 6b. Timezone direction, week edges, DST (`test_clean_events.py`)

Each row: stored UTC → arithmetic → expected `local_ts` / `local_week`. "Wrong" = what a single
`occurred_at AT TIME ZONE tz` or a UTC bucket would give.

| # | Acct | UTC `occurred_at` | Arithmetic | Expected local_ts | local_week | What it proves |
|---|---|---|---|---|---|---|
| T1 | A1 Chicago | 2026-02-01 16:39:22 | −6 h (CST) | 2026-02-01 10:39:22 | 2026-01-26 | Direction (profile event 12); Feb 1 is Sunday → week of Jan 26 |
| T2 | A6 New York | 2026-07-01 03:30:00 | −4 h (EDT) | **2026-06-30 23:30:00** | 2026-06-29 | Direction, date flips back a day. Wrong direction (+4) gives 07-01 07:30 |
| T3 | A1 Chicago | 2026-07-01 16:39:22 | −5 h (CDT) | 2026-07-01 11:39:22 | 2026-06-29 | Summer offset differs from T1 (no fixed −6) |
| W1 | A1 Chicago | 2026-02-09 05:59:59 | −6 h | 2026-02-08 23:59:59 (Sun) | **2026-02-02** | Last second of Sunday. UTC-week would be 02-09 |
| W2 | A1 Chicago | 2026-02-09 06:00:00 | −6 h | 2026-02-09 00:00:00 (Mon) | **2026-02-09** | First second of Monday |
| W3 | A4 UTC | 2026-02-08 23:59:59 | 0 | same | 2026-02-02 | UTC account, Sunday edge |
| W4 | A4 UTC | 2026-02-09 00:00:00 | 0 | same | 2026-02-09 | UTC account, Monday edge; local = UTC, no shift |
| W5 | A5 Kolkata | 2026-02-08 18:29:59 | +5:30 | 2026-02-08 23:59:59 | 2026-02-02 | Zone *ahead* of UTC: direction holds both ways |
| W6 | A5 Kolkata | 2026-02-08 18:30:00 | +5:30 | 2026-02-09 00:00:00 | **2026-02-09** | …and local week can be *later* than UTC week (UTC week would be 02-02) |
| S1 | A1 Chicago | 2026-03-08 07:59:59 | −6 h (still CST, before 08:00 UTC) | 2026-03-08 01:59:59 | 2026-03-02 | Last second before DST |
| S2 | A1 Chicago | 2026-03-08 08:00:00 | −5 h (now CDT) | **2026-03-08 03:00:00** | 2026-03-02 | Local 02:xx doesn't exist; UTC→local never produces it |
| S3 | A1 Chicago | 2026-03-09 04:59:59 | −5 h (CDT) | 2026-03-08 23:59:59 (Sun) | **2026-03-02** | Sunday edge *after* DST |
| S4 | A1 Chicago | 2026-03-09 05:00:00 | −5 h | 2026-03-09 00:00:00 (Mon) | **2026-03-09** | Fixed −6 would give 03-08 23:00 → week 03-02 (wrong) |
| S5 | A1 Chicago | 2026-03-02 05:59:59 / 06:00:00 | −6 h (pre-DST) | 03-01 23:59:59 / 03-02 00:00:00 | 02-23 / 03-02 | Pre-DST edge control |
| P1 | A2 Denver | 2026-03-09 06:30:00 | −6 h (MDT since 03-08 09:00 UTC) | 2026-03-09 00:30:00 | **2026-03-09** | Phoenix vs Denver, same instant, after DST… |
| P1′ | A3 Phoenix | 2026-03-09 06:30:00 | −7 h (no DST) | 2026-03-08 23:30:00 | **2026-03-02** | …different local week |
| P2 | A2 Denver and A3 Phoenix | 2026-03-02 06:30:00 | both −7 h (Denver still MST) | 2026-03-01 23:30:00 | 2026-02-23 (both) | Control: identical *before* DST |
| P3 | A2 Denver / A3 Phoenix | 2026-07-13 06:30:00 | −6 h / −7 h | 2026-07-13 00:30:00 / 2026-07-12 23:30:00 | 2026-07-13 / 2026-07-06 | Summer repeat |

### 6c. Migrations (`test_migrations.py`) and health (`test_health.py`)

| Case | Check |
|---|---|
| Faithful to `schema.sql` | Execute `data/schema.sql` **read-only as text** inside a rolled-back txn in a scratch schema; compare `information_schema.columns` (name, type, nullability, varchar length) and PK columns for both tables against the migrated `public` tables. The only allowed difference is the extra index (asserted explicitly). |
| Round trip | In its **own throwaway DB `relay_migrations_test`**, never `relay_test`: `upgrade head` → `downgrade base` → `upgrade head` succeeds; the view is gone after downgrading 0002 and the tables after 0001. |
| Index present | `pg_indexes` contains `ix_activity_events_account_id_occurred_at` on `(account_id, occurred_at)`. |
| Not too strict | An `activity_events` row with unknown type, NULL outcome and an exact duplicate row all insert without error. |
| Health ok | `GET /api/health` → 200 `{"status":"ok","db":"ok"}`. |
| Health DB down | Dependency pointed at a bad URL → 503. |

### 6d. Seed-load and data-profile numbers (`test_seed.py`)

All inside the rolled-back transaction after `load_seed(conn)`. Numbers recomputed from `data/seed.sql` while
writing this plan, using an independent script, and matched against the profile except where noted.

| Check | Expected | Source / note |
|---|---|---|
| Raw counts | `accounts` 20, `activity_events` 12,626 | profile §1 |
| `clean_events` count | **12,614** (12 removed) | profile §7 |
| Removed ids | `{1524,1539,2237,5852,5857,6326,6967,7525,8739,9596,9604,11267}` absent; each lower pair-id present | profile §7 (consecutive pairs) |
| Removed per account | acct 6: 4; 1: 2; 18: 2; 2, 4, 8, 12: 1 each | profile §7 |
| Per type (clean) | call_received **7,771**, lead_created **3,042**, appointment_set **1,801** | raw 7,780/3,044/1,802 minus the dedupe (9/2/1 = 12) |
| Account 20 | 0 rows in `clean_events` | profile §1 |
| Locations | 69 distinct `(account_id, location)` | profile §1 |
| Weeks | 27 distinct `local_week`: the 25 complete weeks (2026-02-02 … 2026-07-20) plus partials. 2026-01-26: **18** events / **8** accounts. 2026-07-27: **79** events / **17** accounts | profile §3 |
| Account 6 spike | week 2026-06-01 total = **880**; week 2026-06-08 = **102**; median of account 6's 25 complete-week totals = **76** | **Discrepancy:** profile §11 says 881. That is the *raw* count. Ids 8738/8739 are an account 6 duplicate pair inside the spike week, so the view correctly gives 880. Dataset-wide that week is 1,269 (raw 1,270). |
| Local vs UTC week | exactly **8** events where `local_week <> date_trunc('week', occurred_at)::date`, ids `{476, 932, 1871, 10146, 11092, 11093, 11094, 12045}`. By zone: Chicago 2, Denver 3, LA 2, New York 1, Phoenix 0, UTC 0 | profile §4. Same 8 on raw and clean (no duplicate is a week-changer) |
| Week-changer arithmetic (each asserted) | 476 Denver `2026-02-09 06:02:46` −7 → `02-08 23:02:46`, wk 02-02 (not 02-09). 932 LA `02-16 04:01:23` −8 → `02-15 20:01:23`, wk 02-09 (not 02-16). 1871 Chicago `03-02 05:11:21` −6 → `03-01 23:11:21`, wk 02-23 (not 03-02). 10146 LA `06-22 06:36:23` −7 → `06-21 23:36:23`, wk 06-15 (not 06-22). 11092 NY `07-06 02:39:28` −4 → `07-05 22:39:28`. 11093 Denver `07-06 02:40:24` −6 → `07-05 20:40:24`. 11094 Chicago `07-06 03:35:05` −5 → `07-05 22:35:05`; all three wk 06-29 (not 07-06). 12045 Denver `07-20 05:15:54` −6 → `07-19 23:15:54`, wk **07-13** (not 07-20) | note 12045 sits at the edge of the default report week |
| **DQ: unknown event types** | `select distinct event_type from clean_events` ⊆ `{call_received, lead_created, appointment_set}`; fails with the offending values listed | PLAN §3. A test, not a runtime filter (see Q9) |
| Timezones valid | every `accounts.timezone` is in `pg_timezone_names`; the set is exactly the 6 zones in profile §1 | guards the view against a bad zone |
| Idempotent | `load_seed` twice → same counts and same `clean_events` count | §4 |
| Atomic | Load the seed once, then `conn.begin_nested()` (SAVEPOINT) and call `load_seed` with a broken file (valid `TRUNCATE`, then a failing statement). It raises; roll back to the savepoint; the earlier load is intact (12,626 / 20). A SAVEPOINT is required because an error aborts the outer transaction in Postgres. | §4 |

Not tested in T1: baseline/verdict logic (T2), API contracts beyond health (T3).

## 7. Makefile

Only Docker and make are required on the host.

| Target | Does |
|---|---|
| `make up` | `docker compose up -d --build --wait` (db → migrate → api) |
| `make down` | `docker compose down` (keeps the volume) |
| `make reset` | `docker compose down -v` (drops the DB volume) |
| `make migrate` | `docker compose run --rm migrate` |
| `make seed` | `docker compose run --rm api python -m app.seed` |
| `make psql` | `docker compose exec db psql -U relay relay` |
| `make logs` | `docker compose logs -f api` |
| `make lint` | `ruff check .` and `ruff format --check .` (in the api container) |
| `make typecheck` | `mypy app tests` |
| `make test` | `pytest -q` |
| **`make check`** | `lint` → `typecheck` → `test`, stopping at the first failure. Everything in containers via `docker compose run --rm api …`. |

**Fallback (decided):** if `docker compose up --wait` proves flaky with the exiting `migrate` service, `make up` becomes
`docker compose run --rm migrate` followed by `docker compose up -d --build --wait db api`. Migrations are never moved into the api entrypoint.

`make check` needs only `db` to be healthy (via `depends_on`); it creates `relay_test` itself. Frontend
checks join `make check` in T4 (PLAN §9 lists them, but there's no frontend yet; Q10).

## 8. Done when

- [ ] `git diff --exit-code main -- data/` is empty and `git status` shows no change under `data/` (also a clean `git diff` at the end).
- [ ] Deny rules verified by one live attempt: in a **fresh** session, ask Claude to edit `data/schema.sql`; the
      Edit/Write is denied by the permission rule and the file is unchanged (output pasted into the ai-log).
- [ ] From a **clean clone** with no `.env`: `make up && make seed && curl localhost:8000/api/health` returns 200,
      then `make check` is green. Repeated after `make reset`. Total under ~10 minutes including image pulls.
- [ ] `make seed` run twice gives identical counts (12,626 / 20; view 12,614).
- [ ] Every row of §6 exists as a test and passes; the seed-load numbers match §6d.
- [ ] `alembic upgrade head`, `downgrade base` and `upgrade head` all succeed.
- [ ] `CLAUDE.md` **Commands** section filled in (up, down, reset, seed, check, psql), and the stack lines updated (uv, mypy, Python 3.12, psycopg 3).
- [ ] `.env.example` present; no secrets committed; `ruff`, `mypy`, `pytest` all green inside the container.
- [ ] **PLAN.md is not edited** (the brief keeps it as written). `docs/data-profile.md` Method section has a one-line note that its counts are raw (before dedupe), with the 881 → 880 example (Q8). The "adapted" clarification (Q1) lives in this plan and later the README.
- [ ] Nothing committed without your say-so. Proposed messages when asked: `chore: add data/ deny rules`, `chore: scaffold docker-compose, api skeleton, make check`, `feat: add tables migration`, `feat: add clean_events view`, `feat: add idempotent seed script`, `docs: note raw counts in data-profile`.

Implementation order (tests first): deny rules → compose/Dockerfile/Makefile/health + settings
(**review checkpoint**) → migration 1 + migration tests → view tests (red) → migration 2 (green) → seed + seed tests → CLAUDE.md.

## 9. Open questions (decision needed) and PLAN challenges

### Decisions (from review)

- **Q1:** agreed. PLAN.md is **not** edited; the "adapted" clarification goes in this plan and later the README.
- **Q2, Q4, Q5, Q6, Q7, Q10, Q11, Q13:** my recommendations accepted as written.
- **Q3:** separate `migrate` one-shot. Fallback if `up --wait` is flaky is in the Makefile (§7). Never the api entrypoint.
- **Q8:** add a one-line note to the Method section of `docs/data-profile.md` (counts are raw, before dedupe; 881 → 880). No change to PLAN.md.
- **Q9, input for the T2 plan:** belongs to T2. Leaning: totals count only the 3 known types, plus a visible DQ warning when others appear.
- **Q12:** custom hook script and its tests **dropped** (time budget). Replaced by native `permissions.deny` rules (§10). Backstops remain the `:ro` mount and the `git diff` check.

### Original questions and recommendations

Each has my recommendation. Q1, Q2, Q4, Q8, Q9 and Q10 challenge PLAN.md or the profile directly. (Q12 below is superseded by the decision above.)

| # | Issue | Recommendation | Trade-off |
|---|---|---|---|
| Q1 | **PLAN §7 says migration 1 is "adapted to Postgres".** `schema.sql` already is Postgres-valid, so there's nothing to translate. | Say so in the plan and docs: the migration is the same schema in Alembic form + named constraints + one index. | None. It's wording, but it prevents a reviewer hunting for adaptations. |
| Q2 | **PLAN §3 says `trim`.** Postgres `trim()` strips only spaces, not tabs/newlines. | `btrim(x, E' \t\r\n')`, as in §3. | Slightly more verbose SQL. No effect on this seed. |
| Q3 | **How migrations run on startup.** Separate `migrate` one-shot (recommended) vs. `alembic upgrade head && uvicorn` in the api command. | One-shot service. | `up --wait` with an exiting service has had version-specific quirks, to be verified on Docker 29.1.3. If flaky, fall back to the entrypoint. |
| Q4 | **Dedupe after normalization** vs. strictly on raw columns (PLAN says "exact"). | After. Reasoning in §3. | Looser than "exact" in a hypothetical messy ingest; identical on this seed. |
| Q5 | **`id` columns:** plain `INTEGER` PK like `schema.sql` vs. identity. | Plain `INTEGER`. | A future ingest path needs identity + `setval`. Out of scope for the ticket. |
| Q6 | **`.env.example` in T1** (PLAN §8 puts it in T6). Compose introduces env vars now. | Create it now (about 6 lines, defaults also inline in compose). T6 only verifies it. | None. Otherwise T1 ships undocumented variables. |
| Q7 | **Seed behavior on rerun:** truncate + reload in one txn vs. skip when non-empty. | Truncate + reload. | Destructive to dev data by design. Skip-if-populated can't detect a partial or edited table. |
| Q8 | **Profile §11 says 881** for account 6's spike week; the view gives **880** (raw vs. deduped). Likewise profile §1/§5 counts are raw. | Keep the tests on view numbers. Optionally add a one-line footnote to `docs/data-profile.md` and PLAN §13 noting "raw counts". I won't touch either without your say-so. | Docs edit vs. a lingering 1-event discrepancy a reviewer may spot. |
| Q9 | **Unknown `event_type` has no runtime handling.** PLAN §3 says only "a data-quality test fails". A test can't protect a running app: an unknown type would pass through the view, and whether it counts toward "total events" (PLAN §2: "all 3 event types") is undefined. | T1 keeps the view pass-through (as PLAN). **T2 must decide** whether totals count only the 3 known types and whether the report surfaces a DQ warning. Flagging now so it isn't a surprise. | Counting only known types is safer for the metric but silently hides new types, so pair it with a visible warning. |
| Q10 | **PLAN §9: `make check` includes frontend tests/typecheck**, but there's no frontend until T4. | `make check` is backend only in T1; T4 adds the frontend. | The "single gate" is temporarily partial. |
| Q11 | **Tooling picks:** `uv` + `uv.lock` (vs. pip + requirements.txt); `mypy` (vs. pyright); Python 3.12; `psycopg` 3 (not psycopg2); pydantic-settings. | uv, mypy (`.gitignore` already lists `.mypy_cache`), 3.12, psycopg 3. | uv adds one tool to the image build but gives a lockfile and fast builds; pyright is faster but adds a Node dependency. |
| Q12 | *Superseded by the decision above.* Originally: custom hook vs. ro mount vs. deny rules. | Now: deny rules + ro mount, no hook script. | See §10. |
| Q13 | **Health endpoint:** `/api/health` with a DB `SELECT 1` (recommended) vs. a dumb liveness `/health`. | `/api/health` (matches PLAN §6's `/api` prefix), 503 when the DB is unreachable. | A DB blip marks the api unhealthy in compose. Acceptable here. |

## 10. `data/` write guard: native deny rules

Replaces the earlier hook-script design (dropped for the time budget). No script, no unit tests.

`.claude/settings.json` (committed; `settings.local.json` is already git-ignored):

```json
{
  "permissions": {
    "deny": [
      "Edit(/data/**)",
      "Write(/data/**)"
    ]
  }
}
```

`/data/**` is project-root-relative. In Claude Code, an `Edit` deny rule applies to all of the built-in
file-editing tools (Write, MultiEdit, NotebookEdit), and `Write(...)` is listed explicitly as well. The exact pattern
syntax is checked by the live attempt below, not assumed.

**Verification:** one live attempt in a **fresh** session (permissions load at session start): ask Claude to edit
`data/schema.sql`, confirm it is denied and `git diff -- data/` is empty. I will not test this against the real
file in the implementing session.

**What it does NOT cover:**
- **Bash.** `sed -i`, `>`/`>>`, `cp`, `mv`, `rm`, `git checkout/restore`, `python -c` can still modify `data/`.
- Other tools or MCP servers that write files, and edits made outside Claude Code (editor, shell, IDE).
- **Itself:** the rules can be edited or removed, or overridden in local or user settings.
- Committed changes: it does not look at git.

Backstops: the `./data:/data:ro` compose mount (containers only), `git diff --exit-code main -- data/` in §8, and review.
