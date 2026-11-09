# Relay Analytics App — DASH-247

A reporting screen that tells a customer admin whether last week's activity (calls, leads, appointments) was normal for them, per account and per location. Contents: [run it](#run-it) · [tests](#tests-and-the-quality-gate) · [configuration](#configuration) · [make targets](#make-targets) · [how I read the ticket](#how-i-read-dash-247) · [the data](#the-data) · [API](#api-at-a-glance) · [stack and choices](#stack-and-why) · [AI summary](#ai-summary-status) · [assumptions](#key-assumptions) · [decisions](#decisions-and-trade-offs) · [deferred](#deliberately-deferred) · [another day](#with-another-day) · [how it was built](#how-it-was-built) · [repo map](#repository-map)

## What this is

The admin opens the app on Monday morning and wants one answer: **was last week normal for us, and if not, which location should I look at?** One screen: the account verdict with its total against its normal, a location table ranked by how far each location is from its own normal, and a detail view with about 12 weeks of history against that location's normal band. Out of scope (ticket and CLAUDE.md): auth, alerting, forecasting, production infrastructure.

## Run it

Needs only Docker and `make`. `cp .env.example .env` is optional (everything has a default).

```bash
make up     # builds and starts db, api and web; migrations apply first
make seed   # loads data/seed.sql (destructive: truncates and reloads)
```

Open http://127.0.0.1:5173 (web), API at http://127.0.0.1:8000 (`GET /api/health`), Postgres on `127.0.0.1:5433`. The first screen is account 15 at the week of 2026-07-20: the account is normal (20 events) and **Site C is `higher`** (12 events against its usual 5.5). Account 6 at 2026-06-01 shows the spike. Before `make seed` the page shows the API's `account_not_found` error instead of crashing. `make down` stops (keeps the data), `make reset` also drops the database volume. On my machine, a no-cache build plus `make up` and `make seed` took about 40 seconds; the very first run also downloads the Postgres, Node and Python base images, which depends on your network. Nothing is installed on the host.

## Tests and the quality gate

```bash
make check   # ruff check + format check, mypy (strict), tsc --noEmit, pytest, vitest
```

At the time of writing: **pytest 383 passed, vitest 104 passed**. Backend tests use their own databases (`relay_test`, `relay_migrations_test`), never the dev one. Aggregation logic has hand-computed fixtures and a backtest over every account and selectable week ([D-23](docs/decisions.md#d-23-backtest-assertions-and-result-not-tuned): 4.93 % of location-weeks flagged against a ceiling fixed before the run, nothing tuned).

## Configuration

All optional; defaults are in code (`backend/app/settings.py`) and `.env.example`. `DATABASE_URL`, `TEST_DATABASE_URL`, `SEED_PATH` and the web's `API_URL` are set by compose, not by you.

| Variable                                                             | Default                           | What it does                                                                             |
| -------------------------------------------------------------------- | --------------------------------- | ---------------------------------------------------------------------------------------- |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`                  | `relay`, `relay`, `relay`         | database credentials; `make psql` assumes these defaults                                 |
| `REPORT_BASELINE_WEEKS`, `REPORT_MIN_HISTORY_WEEKS`                  | `12`, `8`                         | baseline window; minimum prior weeks before a week is judged                             |
| `REPORT_Z_MIN`, `REPORT_MIN_ABS`, `REPORT_MIN_BASELINE_MEDIAN`       | `2.0`, `3.0`, `4.0`               | flag threshold; minimum absolute difference; below this normal a location is `too_quiet` |
| `DEMO_ACCOUNT_ID`                                                    | `15`                              | account used when `X-Account-Id` is missing (a demo stand-in for login)                  |
| `LLM_SUMMARY_ENABLED`                                                | `false`                           | AI summary on or off                                                                     |
| `SUMMARY_PROVIDER`, `SUMMARY_MODEL`, `ANTHROPIC_API_KEY`             | `mock`, `claude-haiku-5-5`, unset | provider, model and key for the real adapter                                             |
| `SUMMARY_MOCK_MODE`, `SUMMARY_TIMEOUT_SECONDS`, `SUMMARY_MAX_TOKENS` | `ok`, `5.0`, `1024`               | force a mock failure; adapter timeout; adapter token cap                                 |

## Make targets

| Target                                       | Does                                                                                   |
| -------------------------------------------- | -------------------------------------------------------------------------------------- |
| `make help`                                  | list targets                                                                           |
| `make up` / `make down`                      | start (build, migrate, `-V` renews web's `node_modules`) / stop, keeping the DB volume |
| `make reset`                                 | stop and drop the DB volume                                                            |
| `make migrate` / `make seed`                 | apply migrations / truncate and reload `data/seed.sql`                                 |
| `make psql` / `make logs`                    | psql on the dev database / follow api logs                                             |
| `make lint` / `make typecheck` / `make test` | ruff / mypy and `tsc --noEmit` / pytest and vitest                                     |
| `make check`                                 | the quality gate: lint, typecheck, test                                                |

## How I read DASH-247

- **User:** one admin for one account; no auth. The account comes from an `X-Account-Id` header with a demo default, and the UI has an account switcher labeled as a stand-in for login ([D-22](docs/decisions.md#d-22-account-from-an-x-account-id-header-with-a-demo-default-account-15-get-apiaccounts-is-unscoped)).
- **"Normal" means a location's own recent history**, not a comparison between locations, plus an account rollup that has its own series. The metric is total events per week; per-type counts are a breakdown only ([D-08](docs/decisions.md#d-08-one-metric-total-events-and-a-single-tier-verdict)).
- **The window:** the trailing 12 complete weeks before the selected week, never including it or later weeks, zero-filled, with the median as the centre ([D-02](docs/decisions.md#d-02-baseline-trailing-12-complete-weeks-before-the-selected-week-median-center)). A week is flagged only if `|z| ≥ 2` and the difference is at least 3 events, with `spread = max(1.4826·MAD, √median, 1)` ([D-14](docs/decisions.md#d-14-verdict-parameters-and-the-too_quiet-rule), [D-17](docs/decisions.md#d-17-baselineband-is-the-verdicts-no-flag-region-defined-in-t2)). Flags are direction-neutral: "higher" or "lower than usual".
- **Time:** weeks run Monday to Sunday in the account's IANA time zone, DST-aware; only complete weeks are judged; "now" is the data's last timestamp, never `now()` ([D-03](docs/decisions.md#d-03-complete-weeks-only-as-of-anchored-to-the-data), [D-04](docs/decisions.md#d-04-weeks-are-mondaysunday-in-the-accounts-timezone)).
- **Not judged:** fewer than 8 prior weeks (`not_enough_history`), a normal below 4 events (`too_quiet`), or no events at all (`no_activity`). The UI says why.
- **The views:** account summary, ranked location table (unjudged rows below, with the reason), location detail with a chart and a weeks table, and a glossary. Each account has 17 selectable weeks, 2026-03-30 to 2026-07-20 ([D-21](docs/decisions.md#d-21-selectable-weeks-are-per-account-and-judgeable-only-a-location-absent-at-w-is-a-404)).

## The data

20 accounts and 12,626 events in `data/seed.sql`, which is never edited; **the seed ends on 2026-07-27**. Migration 1 is an adapted copy of `data/schema.sql` ([D-07](docs/decisions.md#d-07-migration-1-stays-faithful-to-dataschemasql)). Reports read only the `clean_events` view: 12 exact duplicate rows removed, text trimmed, event types lower-cased, the time zone converted in one place ([D-05](docs/decisions.md#d-05-clean_events-is-a-plain-view-not-a-materialized-view), [D-06](docs/decisions.md#d-06-cleaning-rules-in-the-view-exact-duplicate-dedupe-after-light-normalization)). Counts in [docs/data-profile.md](docs/data-profile.md) are raw, so account 6's spike week is 881 there and 880 in the app. Unknown event types are not counted and are reported separately ([D-16](docs/decisions.md#d-16-unknown-event-types-not-counted-reported-separately)). Account 20 has no events and gets its own empty state.

**Account 6's 2026-06-03 spike** (805 events in one day, about 60 times a typical Wednesday) is kept as real data ([D-09](docs/decisions.md#d-09-account-6s-2026-06-03-spike-stays-in-as-real-data)). It hits all 15 of its locations: at 2026-06-01, **12 are flagged `higher` and 3 are unjudged (`too_quiet`)**, and the account is `higher` (880 events against a median of 73.5). PLAN §13 says "all 15 locations flag together"; that is wrong, see [D-23](docs/decisions.md#d-23-backtest-assertions-and-result-not-tuned).

## API at a glance

Every endpoint except the first is scoped by the account from `X-Account-Id` (default 15), never from a path; every error has one shape, `{"error": {"code", "message"}}` ([D-20](docs/decisions.md#d-20-one-report-service-behind-thin-endpoints-injectable-inputs-one-error-shape)). PLAN §6 is the sketch; [plans/T3-backend-api.md](plans/T3-backend-api.md), D-20 to D-22 and D-29 are the source for the shapes.

- `GET /api/accounts`: the demo switcher's list (the one unscoped endpoint).
- `GET /api/weeks`: the account's selectable weeks and the default (the last complete week).
- `GET /api/report?week=YYYY-MM-DD`: account summary and the ranked locations, with the parameters used. An account with no events gets `week: null` and `no_activity`.
- `GET /api/locations/{location}/history?week=`: weekly totals and the band for one location; an absent location is a 404.
- `POST /api/summary` (body `{"week": ...}`): the optional AI summary, see below.

## Stack and why

Python 3.12, FastAPI, SQLAlchemy 2.0 (sync), Alembic, Pydantic v2, psycopg 3, PostgreSQL 16; React, TypeScript (strict) and Vite; everything under docker-compose ([D-01](docs/decisions.md#d-01-stack-python-fastapi-sqlalchemy-alembic--postgresql), [D-13](docs/decisions.md#d-13-the-whole-app-runs-under-docker-compose-from-t1)). Python for the migration, validation and test tooling and the LLM SDKs; Node and Java were viable and cost more ceremony for this size.

### Notable technical choices

**Few dependencies, on purpose.** A 4–6 hour slice rewards a small surface: every dependency is
setup time, a lockfile change, and something a reviewer has to trust. Each choice below has the
"in a real project" counterpart.

| Area              | Here                                                                                                                                             | Why                                                                                                                                                                           | In a real project / with another day                                                                     |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Data access       | SQLAlchemy 2.0 Core with `text()` SQL, no ORM models                                                                                             | The work is aggregation (zero-filled weekly series, timezone bucketing); hand-written SQL is easier to read and verify than ORM queries, and there are no entities to persist | ORM models for a write-heavy domain (accounts, settings, users); the analytics queries would stay as SQL |
| Migrations        | Alembic, faithful to the provided `schema.sql` (D-07), plus a `clean_events` view (D-05, D-06)                                                   | Real migrations as the brief asks; cleaning rules in one place                                                                                                                | A materialized view or a rollup table once data volume needs it                                          |
| Statistics        | Pure Python (median, MAD) over series built in SQL (D-15)                                                                                        | Easy to unit-test with hand-computed fixtures                                                                                                                                 | Same split; push down to SQL only if profiling says so                                                   |
| Frontend state    | React only: URL as the source of truth, two small hooks (`useUrlState`, `useAsync`), no router, no state library (D-27)                          | One screen; the state that must survive reload is three URL params                                                                                                            | A router and TanStack Query for server state; Zustand or Redux only if shared client state grows         |
| HTTP client (LLM) | stdlib `urllib`, no SDK (D-29)                                                                                                                   | One call; avoids a runtime dependency and a lockfile change                                                                                                                   | The provider's SDK (retries, typed responses, streaming)                                                 |
| LLM orchestration | None: one structured call (D-29)                                                                                                                 | No tools, retrieval or multi-step flow to orchestrate; a framework would hide the validation under review                                                                     | LangChain/LangGraph with LangSmith tracing and evals if the feature grows to multi-step or RAG           |
| Styling           | One plain CSS file (D-28)                                                                                                                        | "Function over form"                                                                                                                                                          | A design system or component library                                                                     |
| Process           | My own minimal flow: PLAN.md, a plan per ticket with an approval gate, `/plan-ticket`, `/close-ticket`, a reviewer subagent, `docs/decisions.md` | Every artifact reflects a decision of mine; Spec Kit considered, too much template for this size                                                                              | A shared spec template if several people or agents work in parallel                                      |

Not built here but needed in production: CI running `make check`, structured logging and
metrics (including the summary's fallback rate), auth and per-tenant scoping beyond a header,
and the items under "Before production" in PLAN §11.

Also: report parameters and the AI flag are typed settings, not constants ([D-18](docs/decisions.md#d-18-report_-prefix-and-a-separate-settings-class-for-the-report-parameters)); the web app is a Vite dev server behind a proxy, which is not a production serving story ([D-26](docs/decisions.md#d-26-the-frontend-is-a-vite-dev-server-in-docker-compose-not-static-files-served-by-fastapi)); `data/` is protected by deny rules ([D-11](docs/decisions.md#d-11-protect-data-with-native-deny-rules-not-a-custom-hook)).


## AI summary: status

A short summary of the selected week, shown on a card under the account summary.

> **Status: an early preview, not a finished feature.** I included it because a working preview
> lets business stakeholders try the idea and give feedback while the production work is still
> pending: an evaluation set, cost and rate controls, monitoring, and prompt and latency tuning
> (the full list is under "Before production" in PLAN §11). That's why it sits behind a flag,
> **off by default**, and can be turned off in one line. The core feature (verdicts, ranking,
> location detail) does not depend on it. What *is* finished is the safety around the model:
> the trust boundary, the validator, the deterministic fallback and their tests.

- **Off by default.** `LLM_SUMMARY_ENABLED` is `false`. The card is always visible; nothing is requested until the user clicks **Generate summary**, and with the flag off the answer is a deterministic template built from the same report (`reason: "disabled"`). `POST /api/summary` takes `{"week": ...}` like `/api/report` and returns 200, not 404, when the flag is off.
- **Enable it with one setting:** copy `.env.example` to `.env`, set `LLM_SUMMARY_ENABLED=true`, run `make up`. That turns on the summary with the mock provider; nothing leaves your machine.
- **Mock by default.** `SUMMARY_PROVIDER=mock` is the default and needs no key or network. Its output is labeled **"AI summary · preview (mock provider)"**, never presented as a model's. `SUMMARY_MOCK_MODE` forces each failure (`unknown_location`, `contradicting_verdict`, `malformed_json`, `exception`, `timeout`) so the fallback labels can be seen by hand.
- **Real provider (optional, still a preview).** To call a model, also set `SUMMARY_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=<your key>` in `.env`, then `make up`. The adapter makes one Messages API call (`SUMMARY_MODEL`, default `claude-haiku-5-5`; `SUMMARY_TIMEOUT_SECONDS`; `SUMMARY_MAX_TOKENS`) over the standard library, with no tools; its answer goes through the same validator as the mock's, and the label reads **"AI summary · preview (anthropic)"**. With `anthropic` and no key the app uses the mock and logs a warning, never an error. The adapter is smoke-tested by hand only: `make check` and CI never call the network or need a key. The model is sent the computed numbers for the account (ids, totals, medians, ranges), never location or account names.
- **What the model may do.** The deterministic logic decides what is unusual. The model gets only ids and numbers for the current account (no location names, no account name) and returns a one or two sentence headline plus structured claims. The server validates both: claims are near-enums that must match the computed verdicts, and the headline has no digits, cites locations only as `[L1]`..`[L5]` tokens and must not contradict a verdict (a heuristic, see D-29). **Every number and name shown is rendered by the server**; the fact lines under the headline are the same with or without the model.
- **Fallback.** Any failure returns the template with a `reason`: `disabled`, `nothing_to_summarize` (no week to summarize), `provider_error`, `timeout` or `validation_failed`. The UI label says which (`Template summary — <reason>`).
- **Not production-ready.** What is missing before production is listed in [PLAN.md §11](PLAN.md#11-where-would-an-llm-fit), in the bullet "Before production" (evaluation set, logging and redaction policy, per-tenant rate limits and budget caps, a prompt-injection review, a review of what customer data may be sent to a provider, fallback-rate monitoring).
- **Excluded by design:** a tool-calling chat, tools and MCP ([D-10](docs/decisions.md)). Also not built: caching, retries, streaming.
- **Where it differs from PLAN.md:** the 200 template instead of a 404, the button click as the opt-in, and a model-written headline (PLAN §11 says no model-written text). Recorded in [D-29](docs/decisions.md); PLAN.md was not edited.

## Key assumptions

PLAN §12 holds the nine open questions; none is answered, and each has a working assumption. Condensed:

1. The 2026-06-03 spike for account 6 is real activity (e.g. a campaign), kept in; the median baseline limits its effect. If it is an artifact, account 6's baseline is biased for 12 weeks.
2. Weeks are Monday to Sunday in the account's time zone. Only about 8 seed events move if not.
3. "Messy data" means what the profile found; more cleaning rules would be needed otherwise.
4. Account 18's `UTC` time zone is real, not a default.
5. "Site A" style labels are stable identifiers; a rename would look like one location stopping and another starting.
6. Low weeks matter as much as high ones (flags are direction-neutral).
7. The 12 duplicates are double-inserts and safe to drop.
8. Account 20 is a new customer, so its empty state is right.
9. Production "as-of" is the wall clock through an injectable clock; the seed uses the data's last timestamp.

## Decisions and trade-offs

The full log is [docs/decisions.md](docs/decisions.md), one entry per decision with real alternatives. The index, by theme:

- **Data and time:** [D-03](docs/decisions.md#d-03-complete-weeks-only-as-of-anchored-to-the-data) complete weeks, as-of from the data · [D-04](docs/decisions.md#d-04-weeks-are-mondaysunday-in-the-accounts-timezone) Monday to Sunday in the account zone · [D-05](docs/decisions.md#d-05-clean_events-is-a-plain-view-not-a-materialized-view) `clean_events` is a plain view · [D-06](docs/decisions.md#d-06-cleaning-rules-in-the-view-exact-duplicate-dedupe-after-light-normalization) cleaning rules · [D-07](docs/decisions.md#d-07-migration-1-stays-faithful-to-dataschemasql) migration faithful to `schema.sql` · [D-09](docs/decisions.md#d-09-account-6s-2026-06-03-spike-stays-in-as-real-data) account 6 spike kept · [D-16](docs/decisions.md#d-16-unknown-event-types-not-counted-reported-separately) unknown event types · [D-21](docs/decisions.md#d-21-selectable-weeks-are-per-account-and-judgeable-only-a-location-absent-at-w-is-a-404) selectable weeks
- **The verdict:** [D-02](docs/decisions.md#d-02-baseline-trailing-12-complete-weeks-before-the-selected-week-median-center) 12-week median baseline · [D-08](docs/decisions.md#d-08-one-metric-total-events-and-a-single-tier-verdict) one metric, one tier · [D-14](docs/decisions.md#d-14-verdict-parameters-and-the-too_quiet-rule) parameters and `too_quiet` · [D-15](docs/decisions.md#d-15-statistics-in-python-sql-builds-the-zero-filled-series-location-existence-and-week-bounds) statistics in Python · [D-17](docs/decisions.md#d-17-baselineband-is-the-verdicts-no-flag-region-defined-in-t2) the no-flag band · [D-23](docs/decisions.md#d-23-backtest-assertions-and-result-not-tuned) backtest, not tuned
- **API and setup:** [D-12](docs/decisions.md#d-12-migrations-in-a-separate-migrate-service-seed-by-truncate-and-reload) separate `migrate` service, seed by reload · [D-13](docs/decisions.md#d-13-the-whole-app-runs-under-docker-compose-from-t1) everything under compose · [D-18](docs/decisions.md#d-18-report_-prefix-and-a-separate-settings-class-for-the-report-parameters) `REPORT_` settings · [D-20](docs/decisions.md#d-20-one-report-service-behind-thin-endpoints-injectable-inputs-one-error-shape) one report service, one error shape · [D-22](docs/decisions.md#d-22-account-from-an-x-account-id-header-with-a-demo-default-account-15-get-apiaccounts-is-unscoped) account from a header · [D-25](docs/decisions.md#d-25-api-tests-a-module-scoped-seeded-connection-and-dependency-overrides) API test fixtures
- **Frontend:** [D-26](docs/decisions.md#d-26-the-frontend-is-a-vite-dev-server-in-docker-compose-not-static-files-served-by-fastapi) Vite dev server in compose · [D-27](docs/decisions.md#d-27-url-reconciliation-rules-and-the-header-less-bootstrap) URL state and reconciliation · [D-28](docs/decisions.md#d-28-presentation-in-t4-plain-css-a-glossary-built-from-the-apis-parameters-the-chart-kept) plain CSS, glossary, chart
- **AI summary:** [D-10](docs/decisions.md#d-10-llm-trust-boundary-the-model-summarizes-it-never-decides) trust boundary · [D-29](docs/decisions.md#d-29-ai-summary-an-always-visible-card-backed-by-the-template-id-only-claims-plus-a-validated-headline) card, ids, headline, `urllib` · [D-30](docs/decisions.md#d-30-real-provider-request-settings-claude-haiku-55-effort-low-api-version-2026-10-21) request settings · [D-31](docs/decisions.md#d-31-summary-payload-five-listed-locations-a-completeness-rule-and-a-mock-mode-env) payload cap, mock mode
- **Workflow and review:** [D-01](docs/decisions.md#d-01-stack-python-fastapi-sqlalchemy-alembic--postgresql) stack · [D-11](docs/decisions.md#d-11-protect-data-with-native-deny-rules-not-a-custom-hook) deny rules for `data/` · [D-19](docs/decisions.md#d-19-the-aggregation-reviewer-reads-the-database-read-only-through-pgoptions-with-no-db-role) reviewer reads the DB read-only · [D-24](docs/decisions.md#d-24-the-aggregation-reviewer-compares-with-the-running-api-through-a-prefix-scoped-curl) reviewer compares with the API

[PLAN.md](PLAN.md) is the working plan and was not edited after the decisions; where it differs, **the log wins**: the AI summary answers 200 with the template instead of a 404 when the flag is off, and the button click is the opt-in ([D-29](docs/decisions.md#d-29-ai-summary-an-always-visible-card-backed-by-the-template-id-only-claims-plus-a-validated-headline)), 17 selectable weeks instead of "25 seed weeks" (D-21), 12 of 15 instead of "all 15" (D-23), and ticket 5 built before ticket 6.

## Deliberately deferred

From PLAN §4: per-type verdicts (per-type location counts of 1 to 5 a week are mostly noise); a second, "strong" verdict tier; per-account overrides of thresholds and features; week-to-date comparison (complete weeks answer the Monday question); a tool-calling chat over the data (rejected by design, D-10); a dedicated account-wide banner. Also: a per-location sparkline in the table (the report has no per-location series, so it needs a backend change, [D-28](docs/decisions.md#d-28-presentation-in-t4-plain-css-a-glossary-built-from-the-apis-parameters-the-chart-kept)); caching, retries and streaming for the AI summary; serving the frontend as static files.

## With another day

In priority order:

1. **An evaluation set for the AI summary:** 20 to 30 report payloads with expected claims, run
   against the real model to measure how often the validator rejects it, before trusting the
   headline any further. Then the rest of PLAN §11's "Before production".
2. **Check the data with its owner:** account 12's 10 location flags ([D-23](docs/decisions.md#d-23-backtest-assertions-and-result-not-tuned)), the account 6 spike,
   and account 18's time zone (PLAN §12).
3. **CI running `make check`**, plus structured logs and the summary's fallback rate as a metric.
4. **The per-location sparkline** (needs a per-location series in `/api/report`) and a
   direction-aware flag colour, since a "higher" week can be good news.
5. **In a real product:** auth and real tenant scoping instead of a header; a router and TanStack
   Query once there are several screens.

## How it was built

One ticket at a time: PLAN.md, a plan per ticket approved before any code, tests first on hand-computed fixtures, mutation checks, an independent reviewer subagent for the aggregation, and a decision log; my own minimal flow rather than Spec Kit (see the table above). The raw sessions, my notes and my reflection are in [ai-log/](ai-log/README.md#reflection). 

**Time:** about 9 hours of focused work, spread over Sunday and Monday with breaks, so above the
4–6 hour guidance. I planned 6 tickets at about an hour each; they averaged about an hour and a
half, mostly the early ones, before the project structure and the agent setup (CLAUDE.md, the
commands, the reviewer) were in place. Most of the extra time went into verification (the
independent reviewer, mutation checks, the AI validator and fallback) rather than more features.

## Repository map

`backend/` FastAPI app, domain logic, migrations, tests · `frontend/` React app and tests · `data/` immutable schema and seed · `docs/` decision log and data profile · `plans/` one plan per ticket · `ai-log/` sessions, notes, reflection · `PLAN.md` the working plan.
