# PLAN.md: DASH-247

Working plan. It records what we decided and why. Concrete parameter values, UI states and
chart details live in the per-ticket plans in `plans/`. Data facts: [docs/data-profile.md](docs/data-profile.md).

## 1. Ticket interpretation

A customer admin opens the app on Monday morning and wants one answer: **was last week's activity
(calls, leads, appointments) normal for us, and if not, which location should I look at?**

- **User:** a single admin for one account. No auth. The backend resolves the account through a
  `get_current_account` dependency (demo default or header for now). The UI has an account switcher
  labeled as a demo stand-in for login.
- **"Normal" means:** a week compared with that location's own recent history, plus an account-level
  rollup. We do not compare locations with each other.
- **Answer shape:** the account verdict first. Then locations ordered by how far they deviate from
  their own normal, so "which location needs attention" is answered by the ordering.
- **Out of scope:** auth, alerting, forecasting/predictive ML, production infra.

## 2. Definitions

- **Week:** Monday 00:00 to Sunday 23:59:59 in the **account's timezone** (IANA, DST-aware).
  Local time is `(occurred_at AT TIME ZONE 'UTC') AT TIME ZONE accounts.timezone`.
- **As-of:** anchored to the data, never `now()`. It comes from an injectable clock. The default
  here is the max `occurred_at` in the data (2026-07-27). In production it would be the wall clock.
- **Complete week:** a week that ended on or before as-of. We judge complete weeks only. The default
  view is the last complete week (2026-07-20). The partial first and last weeks are excluded from
  everything.
- **Baseline:** the **trailing 12 complete weeks before the selected week**. It never includes the
  selected week or later weeks, so older weeks are judged without future data. Zero-activity weeks
  count as 0 (they are zero-filled). The baseline center is the median.
- **Metric:** total events per week (all 3 event types). Per-type counts are shown as a breakdown
  only.
- **Verdict (single tier):** `spread = max(1.4826·MAD, √median, 1)` and `z = (x − median) / spread`.
  A week is flagged only if `|z| ≥ z_min` **and** `|x − median| ≥ min_abs`. The `√median` term is a
  Poisson floor for when MAD is about 0. The `min_abs` guard stops a 2-event wobble from being
  "abnormal". Flags are direction-neutral ("higher/lower than usual").
- **Ranking:** by `|z|`, with ties broken by absolute difference. Locations that are not judged sort
  below.
- **Not judged:** a location (or account) is not judged if it has fewer than the minimum prior
  history (8 weeks) or if its baseline is too quiet. The UI says why. An account with no events at
  all gets its own empty state.
- **Account rollup:** its own series (the sum of its locations per week) with its own median and
  spread. It is not an aggregate of location verdicts.

## 3. Data handling

Raw tables stay as loaded. Aggregations read only from a SQL view (`clean_events`).

| Rule in the view | Finding |
|---|---|
| Remove exact duplicates (all columns except `id` equal), keep the lowest `id` | §7: 12 double-inserts across 7 accounts |
| `trim` text fields, `lower(event_type)` only. No case-folding of `location`, which could merge distinct sites | §5, §6: no variants in this seed, so this is cheap defensive hygiene only |
| Expose `local_ts` and `local_week` once, using the correct double `AT TIME ZONE` | §4: DST-aware bucketing; one place for the timezone logic |
| Count by `event_type`. `duration_seconds` and `outcome` are ignored | §5: ~3% NULL outcomes. §9: durations unreliable (missed calls have durations, 4% of calls have none) |

Not cleaned, on purpose:
- **Near-duplicates:** no clean signal (§8).
- **The account 6 spike:** treated as real data. The median-based baseline limits its influence (§11).
- **Unknown `event_type` values:** a data-quality test fails on them. They are not silently dropped.

Also handled elsewhere:
- Locations are keyed by `(account_id, location)`. There is no locations table in the seed (§1, §6).
- Weekly series are zero-filled.
- Account 20 (no events) is an explicit empty state.

## 4. Scope

| In | Why |
|---|---|
| Account summary, location ranking, location detail with ~12 weeks of history | The core question |
| Week selector, with account, week and location persisted in the URL | The one user input |
| Total verdict plus per-type breakdown | Total is the best signal at 4–10 events/week |
| Optional AI summary behind a flag | Explicitly in the brief, built last (after docs and verification) |

| Deferred | Why |
|---|---|
| Per-type verdicts | Per-type location counts of ~1–5/week are mostly noise |
| Second ("strong") verdict tier | A single tier is enough to answer the ticket |
| Per-account overrides (thresholds, features, branding) | Natural next step for multi-tenant SaaS; not needed for one demo account |
| Week-to-date / same-elapsed-time comparison | Complete weeks answer the Monday-morning question |
| Tool-calling chat over the data | See section 11 |
| Dedicated "account-wide change" banner | The account verdict already communicates it |

| Out | Why |
|---|---|
| Auth, alerting, forecasting, production infra | Per ticket and CLAUDE.md |

## 5. UX: the single screen

One screen, three parts:
1. **Account summary:** the account verdict for the selected week, the total against its normal, and
   the per-type breakdown.
2. **Location table:** ranked by deviation. Unjudged locations are shown below with the reason.
3. **Location detail:** about 12 weeks of history against that location's normal band.

Plus:
- An account switcher (labeled as a demo stand-in for login) and a week selector.
- Account, week and selected location live in the URL.
- Copy such as "compared with your last 12 weeks" follows the parameters returned by the API.
- UI states and chart details go in the frontend ticket plan.

## 6. API sketch

Account always comes from `get_current_account`, never from a path parameter. Every query is scoped
by it. Responses include the `parameters` actually used (baseline weeks, minimum history, `z_min`,
`min_abs`).

- `GET /api/weeks`: the selectable complete weeks and the default (last complete week).
- `GET /api/report?week=YYYY-MM-DD`: `{account, week, parameters, account_summary, locations[]}`.
  - `account_summary`: `{total, baseline{median, band}, verdict, by_type}`.
  - `locations[]`: `{location, total, baseline, verdict, score, by_type}`, ordered by deviation.
- `GET /api/locations/{location}/history?week=...`: weekly totals for ~12 weeks plus the band used.
- `POST /api/summary` (AI, last): body `{week}`. It returns the summary or `404` when the flag is off.
  The summary is generated only if the request opts in.
- A verdict is `normal | higher | lower | not_enough_history | too_quiet | no_activity`.
  Exact JSON shapes go in the backend ticket plan.

## 7. Schema and migrations

- Alembic is the source of truth. The brief requires a real schema with migrations.
- **Migration 1:** creates `accounts` and `activity_events`, adapted to Postgres from the provided DDL.
  It includes a composite index on `(account_id, occurred_at)`. This is not needed for 12k rows, but
  it is what a real table would have.
- **Migration 2:** creates the `clean_events` view (section 3).
- **Seed script:** runs after migrating and loads `data/seed.sql`, unmodified.
- `data/schema.sql` and `data/seed.sql` are never edited. The migration is a separate, adapted copy
  of the DDL.
- PostgreSQL 16 via docker-compose.

## 8. Tickets

Each ticket gets its own plan in `plans/<ticket>.md`, approved before any code. One branch and one
session per ticket.

1. **Scaffold + DB:** docker-compose, Alembic, migrations 1 and 2, the seed script, and view tests
   (duplicates, timezone and DST bucketing, week edges). Also the backend skeleton (FastAPI app,
   settings module stub, pytest, ruff) and the Makefile with `make check`, so the quality gate exists
   from the first ticket. The frontend scaffold stays in ticket 4.
2. **Backend core:** pure domain logic (baseline, verdict, ranking) with tests first on small
   hand-computed fixtures. Then the typed settings module and the weekly-series queries (zero-filled).
3. **Backend API:** FastAPI endpoints, the `get_current_account` dependency, and the response models.
   Includes the lightweight backtest test (section 9).
4. **Frontend:** the single screen, the URL state, and the account and week selectors.
5. **AI (optional, time-boxed):** the summary interface, the validator, the deterministic fallback and
   the mock provider, then the flag and opt-in. A real provider adapter is the last sub-ticket and
   is only done if time remains.
6. **Docs and final verification:** README (run instructions, decisions, trade-offs, deferred items),
   `.env.example`, a clean-clone run check (must work in ~15 min), and the AI log reflection.

**Order:** 1, 2, 3, 4, then 6, then 5. Ticket 6 comes before ticket 5. If time runs short, the AI
ticket is cut, not the docs and verification.

## 9. Testing strategy and quality gate

- **Tests first** for aggregation and verdict logic, using small fixtures with hand-computed expected
  values. The domain layer is pure functions, tested without a database.
- **Integration tests** against Postgres: the view (dedupe, local week, DST), the queries, and API
  contract tests.
- **Backtest, lightweight:** run the rule over the 25 seed weeks. The account 6 spike must flag, and
  normal weeks should rarely flag. This is a sanity check, not a tuning exercise.
- **AI:** validator tests (a number or location not in the payload is rejected, fallback on error or
  timeout) with a fake provider. No test needs a key.
- **Frontend:** component tests for the main states, plus a typecheck.
- **Quality gate:** a single `make check` (lint, typecheck, backend tests, frontend tests) must pass
  before merge.

## 10. Engineering principles

- **Proportional architecture:** sync SQLAlchemy 2.0, no task queues, no extra state libraries, no
  abstractions without a second use.
- **Pure domain logic:** the statistics have no I/O, so they are easy to test and read.
- **Business rules are configuration, not constants.** The baseline window, minimum history, `z_min`
  and `min_abs` live in a typed settings module (pydantic-settings). Defaults are in code and can be
  overridden by environment variables. Feature flags such as `LLM_SUMMARY_ENABLED` live alongside them.
- **Defaults are pragmatic,** sanity-checked by the backtest, not statistically optimized. Tuning is
  not the focus.
- **The API echoes the parameters it used,** so UI copy follows the config instead of hard-coding it.
- **Timezone and time:** per-account IANA zones, no fixed offsets, an injectable as-of, never `now()`
  for the reporting week.
- **Secrets and keys** come from the environment (`.env`, not committed). The app runs fully with no
  API key.
- **Workflow:** one ticket at a time, plan before code, conventional commits, merge commits.

## 11. Where would an LLM fit?

- **Use case:** a short written summary of the week for the admin. It is generated from the
  already-computed report: the account verdict plus the top flagged locations. It saves the admin
  reading the table, and it does not decide anything.
- **Trust boundary:** the deterministic logic decides what is anomalous. The LLM only receives the
  computed payload for the current account (never raw rows, never other accounts) and returns text.
  It has no tools and no database access.
- **Verification of nondeterministic output:** the model returns structured claims, each citing a
  location and a metric. The server checks every cited location and number against the payload and
  renders the numbers itself. Anything that does not match is rejected.
- **Failure handling:** on a validation failure, an error or a timeout, the response falls back to a
  deterministic template summary built from the same payload. The feature is off by default
  (`LLM_SUMMARY_ENABLED`) and needs a per-request opt-in.
- **Cost and latency:** one small call per opt-in request, with a timeout and a small input. The
  summary can be cached per account and week, because the data is static for a given as-of.
- **Provider:** a provider interface, a deterministic mock as the default, and a real adapter
  (key in `.env`) as the last optional sub-ticket. CI never needs a key.
- **Before production:** an evaluation set of payloads with expected claims, logging and redaction
  policy, per-tenant rate limits and budget caps, a prompt-injection review (location names are
  free text), a review of what customer data may be sent to a provider, and monitoring of fallback
  rate.
- **Deliberately not built:** a tool-calling chat. It widens the trust boundary (account scoping,
  injection through data), needs an evaluation effort for open-ended questions, adds cost and
  latency, and doesn't fit a ticket whose answer is deterministic. We also don't let the LLM judge
  anomalies, because that result couldn't be reproduced or tested.

## 12. Open questions and working assumptions

I'm not sending these now. They stay here until someone can answer.

| # | Question | Working assumption | Impact if wrong |
|---|---|---|---|
| 1 | Is the 2026-06-03 spike for account 6 a known event (campaign, backfill) or an artifact? | Real data, kept in; the median baseline limits its influence | If it is an artifact, exclude it or the week would show as a false "high" and bias account 6's baseline for 12 weeks |
| 2 | Are weeks Monday–Sunday in the account's timezone? | Yes | Different week boundaries; only ~8 seed events move, but real data would differ |
| 3 | Does "messy data" refer to what the profile found, or are other issues expected? | Only what the profile found (data-profile §13.2) | More cleaning rules and tests needed |
| 4 | Is account 18's `UTC` timezone real or a default? | Real | Wrong week bucketing for that account's Sunday-evening events |
| 5 | Are "Site A…" labels stable identifiers? Can a location be renamed or merged? | Stable; keyed by `(account_id, name)` | A rename would look like one location stopping and another starting with no history |
| 6 | Do low weeks matter as much as high ones? | Yes, flagged neutrally | Direction-specific rules or wording needed |
| 7 | Are the 12 duplicates known double-inserts? | Yes, safe to drop | If they are legitimate coincident events, counts are 0.1% low |
| 8 | Is account 20 a new customer, or should it have data? | New customer, empty state is right | If data is missing, the empty state hides an ingest problem |
| 9 | Is production "as-of" just the wall clock? | Yes, through an injectable clock; seed uses the data anchor | Reporting week logic would need a different anchor |

## 13. Risks

- **Low location volume (4–10 events/week):** verdicts are inherently noisy. Mitigation: the
  Poisson floor, the minimum absolute difference, and the 8-week minimum history.
- **Multiple comparisons:** many locations mean a few false flags per week even with good rules.
  Mitigation: a single conservative tier, plus the backtest sanity check.
- **Account 6 spike dominates the story** for the weeks around 2026-06-03, and all 15 locations
  flag together. Mitigation: the account-level verdict; a dedicated banner is deferred.
- **Migrations vs. the provided DDL:** the adapted migration must stay faithful to `schema.sql`.
  Mitigation: a test that loads the seed and checks row counts (20 accounts, 12,626 events).
- **Untested real-provider path:** the real LLM adapter is only smoke-tested manually. Mitigation:
  it is optional, off by default, and the mock and fallback cover the logic.
- **Time budget:** the AI work comes after docs and final verification (ticket 6) and is time-boxed.
  If time runs out, the AI ticket is cut and section 11 stands as the design.
- **Timezone/DST mistakes:** a single conversion in the view, with tests across the 2026-03-08 DST
  change and a Phoenix (no-DST) account.
