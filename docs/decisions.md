# Decision log

Lightweight ADRs: one entry per design decision with real alternatives.
Details live in the linked PLAN.md / plans/ sections.

## D-01: Stack: Python (FastAPI, SQLAlchemy, Alembic) + PostgreSQL
- **Context:** the brief asks for the stack I'm strongest in. I've worked with Node,
  Java and Python.
- **Decision:** Python. I've built production APIs and endpoints with PostgreSQL
  and MongoDB at a SaaS company, and for a data-heavy backend its tooling fits best:
  Alembic for real migrations, Pydantic for typed settings and response models, pytest,
  and first-class LLM SDKs for the optional AI piece. It's also the stack of the role.
- **Alternatives:** Node (strong experience; viable, but weaker migration/validation
  story for this kind of service); Java (solid, but the extra ceremony would cost
  time better spent on verification within 4–6 hours).
- **Consequences:** evaluated against Python idioms: strict mypy, ruff, typed models.
- **Source:** my own call; see README.

## D-02: Baseline: trailing 12 complete weeks before the selected week, median center
- **Context:** location volume is low and noisy (4–10 events/week, CV about 0.4), and account 6's spike
  sits inside the window for that account ([data-profile §10, §11](data-profile.md)). The week
  selector must not leak future data into older weeks.
- **Decision:** the baseline is the 12 complete weeks before the selected week. It never includes the
  selected week or later ones. Zero-activity weeks count as 0. The center is the median, and the
  spread is `max(1.4826·MAD, √median, 1)` (the `√median` Poisson floor covers MAD ≈ 0).
  A location with fewer than 8 prior weeks is "not judged".
- **Alternatives:** the options listed in the profile: all 25 weeks; a shorter trailing window
  (4, 8 or 13 weeks); mean ± k·stddev (distorted by the account 6 spike); median with IQR;
  same-season weeks (only one year of data, so not available).
  Why 12 weeks: about a quarter. That is enough points for a stable median/MAD at 4–10 events/week,
  recent enough to follow real changes, and it leaves enough judgeable weeks in the 25 for the backtest.
  Why zero weeks count as 0: a silent week is real information (e.g. a closed site) that an admin
  wants flagged; excluding them would inflate the baseline and hide it.
- **Consequences:** older weeks are judged without future data (the "before the selected week" rule
  was accepted in session 02). The window, minimum history, `z_min` and `min_abs` are typed
  configuration, not constants. Defaults are sanity-checked by a lightweight backtest, not tuned.
- **Source:** [PLAN.md §2, §10](../PLAN.md); [notes.md, session 02](../ai-log/notes.md); [D-14](#d-14-verdict-parameters-and-the-too_quiet-rule); [plans/T2-backend-core.md §1e–§1f](../plans/T2-backend-core.md).

## D-03: Complete weeks only, as-of anchored to the data
- **Context:** the seed ends 2026-07-27 (a Monday, with 79 events), about 15 weeks before today, so
  a "current week" taken from the wall clock would be empty. The first and last weeks are partial
  ([data-profile §2, §3](data-profile.md)).
- **Decision:** the reporting week comes from an injectable clock whose default is `max(occurred_at)`
  (2026-07-27), never `now()`. Only complete weeks are judged (a week that ended on or before as-of);
  the default is the last complete week, 2026-07-20. The partial first and last weeks are excluded
  from everything.
- **Alternatives:** the wall clock (empty results on the seed); `max(occurred_at)` per account instead
  of globally; pro-rating partial weeks; comparing week-to-date with the same elapsed time in
  earlier weeks (deferred: complete weeks answer the Monday-morning question, PLAN §4).
- **Consequences:** a partial week never biases a baseline or a verdict. In production the as-of would
  be the wall clock through the same injectable clock. Whether that is the right production anchor is
  still an open assumption (PLAN §12 #9).
- **Source:** [PLAN.md §2, §4, §12](../PLAN.md); [CLAUDE.md data rules](../CLAUDE.md).

## D-04: Weeks are Monday–Sunday in the account's timezone
- **Context:** `occurred_at` is a naive UTC timestamp and each account has an IANA timezone
  that observes (or, for Phoenix, doesn't observe) DST. Only 8 of 12,626 events change week between
  local and UTC bucketing in this seed ([data-profile §4](data-profile.md)). In session 01 the
  agent proposed a single `AT TIME ZONE tz`, which converts in the wrong direction.
- **Decision:** bucket in account-local time using the double conversion
  `(occurred_at AT TIME ZONE 'UTC') AT TIME ZONE accounts.timezone`, never a fixed offset.
  `clean_events` exposes `local_ts` and `local_week` (`date_trunc('week')`, ISO Monday), so the
  timezone logic lives in exactly one place.
- **Alternatives:** UTC bucketing (simpler, differs for 0.06% of this seed); a precomputed local-week
  column; Sunday-start or rolling 7-day weeks; a per-location timezone (not in the data).
- **Consequences:** covered by hand-computed fixtures across the 2026-03-08 DST change, a
  Phoenix-vs-Denver contrast and the Sunday/Monday edges, each with a flag showing whether the UTC
  week would differ. Still open assumptions: Monday–Sunday is the right week (PLAN §12 #2) and
  account 18's `UTC` zone is real (PLAN §12 #4).
- **Source:** [PLAN.md §2, §3](../PLAN.md); [plans/T1-scaffold-db.md §3, §6b](../plans/T1-scaffold-db.md);
  [notes.md, session 01](../ai-log/notes.md).

## D-05: `clean_events` is a plain view, not a materialized view
- **Context:** aggregations read only from the cleaning view (PLAN §3). The seed has 12.6k rows.
- **Decision:** a plain SQL view. At this size it is computed in milliseconds and can never be stale.
- **Alternatives:** a materialized view, which adds a refresh policy and a risk of silent staleness
  (serving old numbers without anyone noticing). At production scale: pre-aggregate weekly counts per
  location, refreshed on ingest.
- **Consequences:** every query re-runs the dedupe window. That is fine here and would stop being
  fine at scale, which is when the pre-aggregation above replaces it. The `(account_id, occurred_at)`
  index is "what a real table would have", not a performance claim at 12k rows (PLAN §7).
- **Source:** [PLAN.md §3, §7](../PLAN.md); [plans/T1-scaffold-db.md §3](../plans/T1-scaffold-db.md).

## D-06: Cleaning rules in the view: exact-duplicate dedupe after light normalization
- **Context:** the profile found 12 exact duplicate pairs (consecutive ids, 7 accounts), no text
  variants, and no clean signal for near-duplicates ([data-profile §5–§8](data-profile.md)).
  Every `lead_created` and `appointment_set` row has a NULL `duration_seconds`.
- **Decision:** drop rows whose columns other than `id` are all equal, keeping the lowest `id`. The
  comparison is made after normalization: `btrim` of the text fields, `lower()` on `event_type` only,
  and `location` is trimmed but never case-folded, so distinct sites can't merge. NULLs compare as equal
  (`PARTITION BY`), and NULL vs a value stays distinct. Near-duplicates are kept. Unknown
  `event_type` values pass through (a data-quality test fails on them rather than the view dropping them).
- **Alternatives:** dedupe at ingest or leave it at about 0.1% noise (profile §7); a uniqueness
  constraint (the seed would not load, and it can drop legitimate coincident events); flagging
  near-duplicates within a time window (no clean signal, profile §8); dedupe before normalization (PLAN's
  "exact" wording); a self-join on `=`, which would keep NULL-bearing duplicates because
  `NULL = NULL` is unknown.
  Why in the view rather than at ingest: cleaning in the view keeps the raw data auditable and the
  rules reversible. If a rule changes or the 12 pairs turn out to be legitimate (PLAN §12 #7), we
  change the view and nothing is reloaded. The brief also forbids modifying the seed.
- **Consequences:** `clean_events` has 12,614 rows (12 fewer than the raw table), and account 6's spike
  week is 880 in the view versus 881 raw. The assumption that the 12 pairs are double-inserts is
  unconfirmed (PLAN §12 #7: if they are legitimate, counts are 0.1% low). Unknown event types at query
  time: see D-16.
- **Source:** [PLAN.md §3](../PLAN.md); [plans/T1-scaffold-db.md §3, §9 (Q2, Q4, Q9)](../plans/T1-scaffold-db.md).

## D-07: Migration 1 stays faithful to `data/schema.sql`
- **Context:** the brief wants a real schema with migrations, and `schema.sql` is immutable. In session
  02 the agent proposed that Alembic create only the view and that docker-compose load `schema.sql`
  directly.
- **Decision:** Alembic creates `accounts` and `activity_events`, expressed as operations with named
  constraints plus the `(account_id, occurred_at)` index. `schema.sql` is already valid PostgreSQL 16,
  so no type needed translating. Ids are plain `INTEGER` primary keys (`autoincrement=False`), and
  `occurred_at` stays `TIMESTAMP WITHOUT TIME ZONE`. Not added: any constraint that would stop the
  unmodified seed loading or hide a data problem (unique payload, `CHECK` on `event_type`, `NOT NULL` on
  `outcome`/`duration_seconds`, a timezone check, a `locations` table). A test loads `schema.sql` into a
  scratch schema and compares it with the migrated tables.
- **Alternatives:** loading `schema.sql` directly (rejected: it breaks the brief's "real schema +
  migrations" requirement and the starter README); identity/serial ids (they conflict with the seed's
  explicit ids, or need a `setval`, and ingest is out of scope); `timestamptz` (would change what the stored
  value means and invert the conversion in CLAUDE.md).
- **Consequences:** the faithfulness test is the guard against drift. The one allowed difference is
  the extra index. A future ingest path would need an id strategy.
- **Source:** [PLAN.md §7](../PLAN.md); [plans/T1-scaffold-db.md §2, §9 (Q1, Q5)](../plans/T1-scaffold-db.md);
  [notes.md, session 02](../ai-log/notes.md).

## D-08: One metric (total events) and a single-tier verdict
- **Context:** per-location counts are 4–10 events/week, and per-type counts about 1–5, so most
  of that variation is noise ([data-profile §10](data-profile.md)). "Normal" means a location compared with
  its own recent history, plus an account rollup, never locations against each other.
- **Decision:** the metric is total events per week across the 3 event types. Per-type counts are shown
  as a breakdown only, and `duration_seconds` and `outcome` are ignored. A week is flagged only if
  `|z| ≥ z_min` **and** `|x − median| ≥ min_abs`, direction-neutral. Locations are ranked by standardized
  score `|z|`, ties broken by absolute difference, rather than raw difference.
- **Alternatives:** per-type verdicts and a second ("strong") tier, both deferred; a raw-difference
  ranking (small locations get buried and a 2-event wobble tops the list: accepted as the reason in
  session 02); outcome- or duration-based metrics (about 3% NULL outcomes, and durations are unreliable,
  profile §5 and §9).
- **Consequences:** many locations mean a few false flags per week even with good rules, which a single
  conservative tier and a lightweight backtest mitigate (PLAN §13). Totals count only the 3 known
  event types and unknown types are reported separately: see D-16.
- **Source:** [PLAN.md §2, §4, §13](../PLAN.md); [notes.md, session 02](../ai-log/notes.md).

## D-09: Account 6's 2026-06-03 spike stays in as real data
- **Context:** 805 events in one day for account 6 (about 60x a typical Wednesday), all 15 locations,
  normal mix and hour-of-day curve, not made of duplicate rows. It cannot be told apart from a real
  surge by the data alone ([data-profile §11](data-profile.md)).
- **Decision:** treat it as real. The median-based baseline limits its influence.
- **Alternatives:** exclude outlier weeks automatically or manually; winsorize extreme weeks; confirm
  with the data owner (cannot be resolved from the data, so it is an open question, PLAN §12 #1).
  Why keep it: the data can't tell a real surge from an artifact. Excluding it would silently remove
  a possibly real event the customer would want to see, and the median already limits its
  influence, so excluding buys little. Capping needs an arbitrary threshold, and a manual flag needs
  the data owner's answer (still open).
- **Consequences:** the weeks around 2026-06-03 will show all 15 account 6 locations flagged together,
  which the account-level verdict covers (a dedicated banner is deferred). If it was an artifact, the
  week would show as a false "high" and bias account 6's baseline for 12 weeks. The backtest
  expects this week to flag.
- **Source:** [PLAN.md §3, §9, §12, §13](../PLAN.md).

## D-10: LLM trust boundary: the model summarizes, it never decides
- **Context:** the optional AI piece is a short written summary of a week for the admin (PLAN §11).
- **Decision:** deterministic logic decides what is anomalous. The model receives only the computed
  payload for the current account (no raw rows, no other accounts), has no tools and no database access,
  and returns structured claims that cite a location and a metric. The server checks every cited
  location and number against the payload and renders the numbers itself. On a validation failure, an
  error or a timeout the response falls back to a deterministic template. The feature is off by default
  and needs a per-request opt-in. The provider sits behind an interface with a deterministic mock as the
  default, so no test and no CI run needs a key.
- **Alternatives:** a tool-calling chat over the data (not built: it widens the trust boundary, needs an
  evaluation effort for open-ended questions, adds cost and latency, and doesn't fit a ticket whose answer
  is deterministic); letting the LLM judge anomalies (the result couldn't be reproduced or tested).
- **Consequences:** built last and time-boxed, after docs and verification (T6 before T5); if time runs
  out, PLAN §11 stands as the design. A list of what must exist before production (evaluation set,
  redaction policy, rate limits, prompt-injection review) is in PLAN §11.
- **Source:** [PLAN.md §8, §11](../PLAN.md).

## D-11: Protect `data/` with native deny rules, not a custom hook
- **Context:** `data/` is immutable (CLAUDE.md), and an instruction alone is something the agent
  chooses to follow. The first plan was a PreToolUse hook script with unit tests.
- **Decision:** `permissions.deny` rules for `Edit(/data/**)` and `Write(/data/**)` in the committed
  `.claude/settings.json`, verified by one live attempt in a fresh session. No script, no tests.
- **Alternatives:** the custom hook script plus about a dozen unit tests (dropped as too much for the
  time budget, given the read-only mount and the `git diff` check that already exist); relying on
  CLAUDE.md alone.
- **Consequences:** in the live check the agent's first attempt was refused by the agent itself, citing
  CLAUDE.md, so the permission layer was never exercised. With an explicit override the Edit tool returned
  "File is in a directory that is denied by your permission settings", and reads still worked. The rules
  do not cover Bash (`sed -i`, redirects, `git checkout`), other tools or MCP servers, edits outside
  Claude Code, or someone editing the rules. Backstops: the `./data:/data:ro` compose mount and
  `git diff --exit-code main -- data/`.
- **Source:** [notes.md, T1 skeleton review](../ai-log/notes.md); [plans/T1-scaffold-db.md §9 (Q12), §10](../plans/T1-scaffold-db.md).

## D-12: Migrations in a separate `migrate` service; seed by truncate and reload
- **Context:** the whole app runs under docker-compose, and a reviewer needs only Docker and make.
- **Decision:** a one-shot `migrate` service runs `alembic upgrade head`, and `api` starts only after it
  completes successfully. The seed script truncates both tables and loads `data/seed.sql` unmodified in
  one transaction: `load_seed(conn)` is caller-managed, and the CLI wraps it in `engine.begin()`, so a
  failure rolls back the TRUNCATE too and a rerun ends in the identical state. The test database
  `relay_test` is created by `conftest.py` (not an init script) and migrated from scratch each run;
  the migration round trip uses its own throwaway database.
- **Alternatives:** running migrations in the api command or entrypoint (rejected; if `up --wait` had
  been flaky the fallback was a two-step `make up`, not the entrypoint); skip-the-seed-if-non-empty
  (it can't detect a partial or edited table); a Postgres init script for the test DB (only runs on a
  fresh volume).
- **Consequences:** `make up --wait` works with the exiting one-shot service, so the fallback isn't
  needed. The seed is destructive to dev data by design. The seed part of this entry is planned and
  lands in the next step of T1.
- **Source:** [plans/T1-scaffold-db.md §4, §5, §9 (Q3, Q7)](../plans/T1-scaffold-db.md);
  [notes.md, T1 skeleton review](../ai-log/notes.md).

## D-13: The whole app runs under docker-compose from T1
- **Context:** the brief asks for a run of about 15 minutes from a clean clone.
- **Decision:** `make up` (db + api, migrations on startup), `make seed`, and `make check` (lint,
  typecheck, tests in the api container) from the first ticket, so a reviewer needs only Docker and make.
  A local venv is optional, for editor support only.
- **Alternatives:** compose for the database only, with the API run locally. Rejected because a
  reviewer would need Python and uv installed, and the 15-minute run path wouldn't be exercised
  until T6.
- **Consequences:** the run path is exercised on every ticket instead of being found broken in T6.
- **Source:** [notes.md, "Before T1: run path"](../ai-log/notes.md); [plans/T1-scaffold-db.md §5, §7](../plans/T1-scaffold-db.md).

## D-14: Verdict parameters and the `too_quiet` rule
- **Context:** PLAN §2 names `z_min`, `min_abs` and "too quiet" but gives no values or definition. Location
  medians over the 12 weeks before 2026-07-20 (69 locations, read from the seeded DB) run from 3 to 11 events
  per week; by floor of the median: 3: 2 locations, 4: 8, 5: 11, 6: 16, 7: 11, 8: 9, 9: 9, 10: 2, 11: 1.
- **Decision:** `z_min = 2.0`, `min_abs = 3`, `min_baseline_median = 4` (all `REPORT_*` settings). `min_abs` is the
  smallest integer above PLAN's "2-event wobble". For a silent week (`x = 0`), `|z| = median / spread` and the spread is
  at least `√median`, so a "lower" flag needs `median ≥ z_min²`: `z_min = 2` makes silence flaggable from median 4
  (`z = −4/2 = −2.0`, `d = 4 ≥ 3`), while 2.5 would need 6.25 (at least 21 locations below it) and 3 would need 9
  (57 below it). `too_quiet` means the baseline median is below 4 = `z_min²`: below that a silent week cannot reach
  `z_min`, so "normal" would say nothing about silence. It is decided by the baseline median only, never by the
  selected week's value. For 2026-07-20 it marks 2 of 69 locations (account 18 Site A, median 3; account 6 Site M, 3.5).
- **Alternatives:** a higher `z_min` (silent weeks could not flag for most locations); deciding `too_quiet` from the
  selected week; a fixed volume threshold unrelated to `z_min`; no `too_quiet` tier (a median of 3 would read "normal"
  for any week, including silence).
- **Consequences:** `min_baseline_median` is a separate setting, so it can drift from `z_min²` (a smaller value only
  costs a verdict that can never fire). The floor of 1 in `spread` cannot fire with the default settings, because
  `√median < 1` only for a median below 1 and `too_quiet` catches that first. The idealized flag rate
  (Poisson, √median floor, MAD ignored) is about 3.4% per location-week at median 7, about 2.4 of 69 locations per
  week. That is a sanity number, not a target; the T3 backtest checks the real rate and the defaults are not tuned.
- **Source:** [PLAN.md §2](../PLAN.md); [plans/T2-backend-core.md §1f, §6 (Q3, Q5, Q9)](../plans/T2-backend-core.md).

## D-15: Statistics in Python, SQL builds the zero-filled series; location existence and week bounds
- **Context:** PLAN §10 wants pure domain logic and PLAN §2 wants zero-filled series, an injectable as-of and
  baselines that never see future data. There is no locations table (profile §1, §6).
- **Decision:** SQL only builds the weekly counts (`app/series.py`, over `clean_events.local_week`, with a
  `generate_series` grid and `LEFT JOIN`); median, MAD, z, verdict and ranking are Python pure functions in
  `app/domain/`. A location exists only through its events: it starts at its first event week, never before the first
  complete week, and takes part in week W only if it starts on or before W. A location with 0 events in W stays in the
  list. The reporting week comes from `last_complete_week(as_of, tz)` (the Monday of the local week containing as-of,
  minus 7 days) and the first usable week from `first_complete_week(data_start, tz)`; both take injectable inputs
  (defaults: `min`/`max(occurred_at)` over the view) and are the only time-zone code outside the view.
- **Alternatives:** `percentile_cont` in SQL (two implementations of the statistics, one untestable without a
  DB); the per-account `max(local_week) − 1` (drops the injectable clock and assumes the last week is always partial);
  `min(local_week) + 1` for the start (assumes the first week is always partial); a `locations` table (not in the seed).
- **Consequences:** the statistics are tested without a database. `first_complete_week` widens the time-zone code from
  one function to two. A location whose only events are in the partial first week, or are of unknown types, still
  exists (zero history); the seed has none. Data ending exactly at Sunday 23:59:59 leaves that week incomplete,
  because a week is complete once its local Sunday is over.
- **Source:** [PLAN.md §2, §10](../PLAN.md); [plans/T2-backend-core.md §1c, §1d, §6 (Q1, Q2, Q6, Q8)](../plans/T2-backend-core.md).

## D-16: Unknown event types: not counted, reported separately
- **Context:** the view passes unknown `event_type` values through (D-06), and a data-quality test fails on them
  rather than the app dropping them silently. Whether they count toward "total events" was left to T2.
- **Decision:** totals and the per-type breakdown count only `call_received`, `lead_created` and `appointment_set`.
  Every weekly row also carries `unknown`, the count of events of other types in that week, so T3 can show a
  data-quality warning. Nothing is dropped silently. A location with only unknown-type events still exists, with a
  total of 0.
- **Alternatives:** counting unknown types in the total (the metric would silently change meaning); filtering them
  out in the view (hides them from the data-quality test and from the warning).
- **Consequences:** the seed has none (profile §5), so no number changes today. T3 decides how the warning is shown. T3 exposes it as `data_quality.unknown_events_in_window`, summed over the baseline weeks plus the selected week (a baseline undercount matters too); the name says it is not the selected week only.
- **Source:** [plans/T1-scaffold-db.md §9 (Q9)](../plans/T1-scaffold-db.md); [plans/T2-backend-core.md §1d](../plans/T2-backend-core.md).

## D-17: `Baseline.band` is the verdict's no-flag region, defined in T2
- **Context:** PLAN §6 has `baseline{median, band}` and does not define the band. The band must not contradict the
  verdict.
- **Decision:** `band = median ± max(z_min·spread, min_abs)`, the exact region where the verdict is not flagged. It is
  computed in T2 next to `judge`; T3 only serializes it.
- **Alternatives:** a band of `median ± z_min·spread` only, which would disagree with the verdict whenever `min_abs`
  dominates; letting T3 define it.
- **Consequences:** one definition shared by the verdict and the chart; T3 only serializes it.
- **Source:** [plans/T2-backend-core.md §6 (Q7)](../plans/T2-backend-core.md).

## D-18: `REPORT_` prefix and a separate settings class for the report parameters
- **Context:** `Settings` is unprefixed (`DATABASE_URL`), and PLAN §10 names `LLM_SUMMARY_ENABLED` unprefixed.
- **Decision:** the five report parameters (`baseline_weeks`, `min_history_weeks`, `z_min`, `min_abs`,
  `min_baseline_median`) use a `REPORT_` prefix in their own `ReportSettings` class. They reach the container through
  `docker-compose.yml` with no default there, so defaults live only in code. The AI flag keeps its PLAN name later.
- **Alternatives:** a global prefix, which would rename `DATABASE_URL` in compose.
- **Consequences:** two naming styles in the environment.
- **Source:** [plans/T2-backend-core.md §6 (Q4)](../plans/T2-backend-core.md).

## D-19: The aggregation-reviewer reads the database read-only through `PGOPTIONS`, with no DB role
- **Context:** the reviewer subagent recomputes verdicts from `clean_events` and must not be able to change data.
- **Decision:** read-only transactions via `PGOPTIONS='-c default_transaction_read_only=on'` on a fixed `psql` command
  prefix, against the dev database. No dedicated role.
- **Alternatives:** a dedicated Postgres role with `SELECT` only, rejected because it needs a DB change (a migration or
  an init script) for a dev-only tool.
- **Consequences:** `PGOPTIONS` is enough because the dev DB is re-seedable in seconds with `make seed` and every query
  was approved by hand. It blocks writes at the session level but is not a privilege boundary. The reviewer's
  instruction not to read `tests/` or §2 of the plan is also not technically enforced (the plan says so).
- **Source:** `.claude/agents/aggregation-reviewer.md`; [plans/T2-backend-core.md §5](../plans/T2-backend-core.md).

## D-20: One report service behind thin endpoints; injectable inputs; one error shape
- **Context:** the endpoints and the PLAN §9 backtest must exercise the same code, and PLAN §2 forbids `now()` and
  future data. PLAN §6 leaves the JSON shapes and the error handling to the T3 plan.
- **Decision:** `app/report.py` holds `build_weeks`, `build_report` and `build_history`, which map `fetch_series` →
  `judge` → `rank` into the Pydantic models of `app/schemas.py`. `app/api.py` only parses and calls. The backtest calls
  `build_report`, so it tests what the API serves. The as-of and data bounds (`get_bounds`), the verdict parameters
  (`get_judge_params`) and the connection (`get_conn`) are dependencies that tests override; the defaults read
  `fetch_bounds` over the view and `ReportSettings`, never `now()`. Every non-2xx has one body,
  `{"error": {"code", "message"}}`: 404 `account_not_found`, 404 `location_not_found`, 422 `invalid_week`, 422
  `invalid_request` (the `X-Account-Id` header, the only source of a validation error), 404 `not_found` and
  `http_error` for other HTTP errors. `week` is taken as a string and parsed strictly (`YYYY-MM-DD`) in
  `resolve_week`, so one place raises `invalid_week`. `no_activity` is a 200 empty state, never an error. Floats are
  returned unrounded.
- **Alternatives:** logic in the route functions; a backtest that calls the domain directly (it could pass while the
  API maps something wrongly); FastAPI's default 422 body, or mapping `RequestValidationError` to different codes by
  inspecting `loc`.
- **Consequences:** the service module is the unit to test and to review. The frontend has one error shape to handle.
  `GET /api/accounts` is the one endpoint that is not account-scoped (D-22).
- **Source:** [plans/T3-backend-api.md §1a to §1d, §7](../plans/T3-backend-api.md).

## D-21: Selectable weeks are per account and judgeable only; a location absent at W is a 404
- **Context:** PLAN §6 says `/api/weeks` returns "the selectable complete weeks". Complete weeks start at 2026-02-02,
  but a week with fewer than `min_history_weeks` prior weeks can only be `not_enough_history`. T2 left open what an
  account that starts after W gets (T2 plan Q8), and `no_activity` already means "the account has no events at all"
  (T2 precedence 1).
- **Decision:** per account, in its own time zone, the selectable weeks run from the account's first week
  (`max(first event week, first complete week)`) plus `min_history_weeks` weeks, through its last complete week. On the
  seed that is 17 weeks per account, 2026-03-30 to 2026-07-20, default 2026-07-20. A week outside the list, a non-Monday
  or a non-date is 422 `invalid_week`; no account-level verdict is `not_enough_history` inside the range. An account
  with no events gets `weeks []`, `default_week null` and a 200 `no_activity` report. An account with events but no
  judgeable week gets the same shape with `not_enough_history`. A location exists at W only through events up to W
  (the T2 rule): history for a location that never had events, belongs to another account, or starts after W is 404
  `location_not_found`, never a 200. The week is checked before the location.
- **Alternatives:** all complete weeks, the early ones returning `not_enough_history`; a global range; a 200
  `no_activity` for an absent location (it changes the verdict's meaning, and a 200 for a location that starts after
  W leaks future data).
- **Consequences:** the first 8 complete weeks are never selectable, so PLAN §9's "25 seed weeks" becomes 17 for
  the backtest. Locations that start later than their account are judged `not_enough_history` inside the range; the
  seed has none.
- **Source:** [plans/T3-backend-api.md §1c, §7 (Q2, Q4)](../plans/T3-backend-api.md); [D-15](#d-15-statistics-in-python-sql-builds-the-zero-filled-series-location-existence-and-week-bounds).

## D-22: Account from an `X-Account-Id` header with a demo default (account 15); `GET /api/accounts` is unscoped
- **Context:** PLAN §1 wants a `get_current_account` dependency with a demo default or a header, and a UI account
  switcher that stands in for login. PLAN §6 has no endpoint that lists accounts.
- **Decision:** `get_current_account` reads `X-Account-Id`. A missing header uses `settings.demo_account_id`
  (env `DEMO_ACCOUNT_ID`, default **15**); an unknown id is 404, a non-integer or an id below 1 is 422. The account
  never comes from a path or query parameter, and every query takes its id. `GET /api/accounts` returns
  `[{id, name, timezone}]` for the switcher. **Account 15 was picked only because it is the only account with a flagged
  location at 2026-07-20** (Site C `higher`, z 2.7716, 12 events against a median of 5.5, in an otherwise normal
  account), so the first screen answers "which location should I look at?". That is a demo choice and a setting, not a
  property of the data. Account 6 (15 locations, the spike at `week=2026-06-01`) is one switcher click away.
- **Alternatives:** the account in the path; no default (a request without the header fails); another default, such as
  account 6, whose last complete week shows only a `too_quiet` location.
- **Consequences:** `GET /api/accounts` lists every account name to any caller, acceptable for a demo stand-in for
  login and replaced by auth later. A missing header silently selects the demo account, so a client that forgets the
  header sees account 15's data, not an error.
- **Source:** [plans/T3-backend-api.md §1a, §7 (Q1, Q3)](../plans/T3-backend-api.md).

## D-23: Backtest assertions and result (not tuned)
- **Context:** PLAN §9 asks for a sanity check, not a tuning exercise: the account 6 spike must flag and ordinary weeks
  should rarely flag. D-14 gave an idealized flag rate of 3.4 % per location-week at median 7 and 5.1 % at median 4.5.
- **Decision:** `tests/api/test_backtest.py` calls `build_report` for every account with events and every selectable week
  (19 accounts × 17 weeks = 323 reports). Assertions fixed before the first run: B1 account 6 at 2026-06-01 is `higher`
  at account level (total 880, z ≈ 60.44); B2 every judged location of account 6 at 2026-06-01 is `higher` (the
  counts are recorded, not asserted to be 15 of 15); B3 the flag rate over judged location-weeks, excluding only account
  6's 15 location-weeks of 2026-06-01, is at most **8.0 %**; B4 no account-level `not_enough_history` inside the
  selectable range; B5 no exception and `history_weeks` never above `baseline_weeks`. Ran once, parameters used (the
  defaults, no `REPORT_*` override): `baseline_weeks=12, min_history_weeks=8, z_min=2.0, min_abs=3.0,
  min_baseline_median=4.0`. **Result: all five assertions passed. The parameters and the ceiling were not tuned.**
  - 1,158 location-weeks outside the spike week: 1,115 judged, 55 flagged, **rate 4.93 %**; 42 `higher` and 13
    `lower`; 43 unjudged, all `too_quiet`.
  - Account level (same exclusion of the spike cell): 322 judged, 14 flagged, 4.35 %.
  - Account 6 at 2026-06-01: 15 locations, 12 judged, 12 flagged `higher`, 3 unjudged (Sites C, H and O, all `too_quiet`).
- **Alternatives:** a ceiling closer to D-14's idealized rate (it fails for the wrong reason on noisy weeks); no
  ceiling (it proves nothing); tuning `z_min` or `min_abs` until the rate looks right.
- **Consequences:** the actual rate (4.93 %) sits inside D-14's idealized 3.4 to 5.1 % band, and the 3.2 : 1 split
  between `higher` and `lower` is consistent with the idealized 2.70 % against 0.73 %. A read-only breakdown after the
  run (no code, no assertion) found no week with a cluster of flags: 1 to 6 location flags per week (at most 6 of 65
  judged, spread over 6 different accounts), 4 flags at the first selectable week (2026-03-30) and 1 at the last
  (2026-07-20), and none of the 14 account-level flags falls on either edge. Account 6's account-level `higher` at
  2026-06-08 (z 2.136) was already anticipated by [data-profile §11](data-profile.md) ("the following week ... is also
  slightly high, 102 vs. median 76"). 2026-03-08 is never a selected week; the weeks around it only enter the baselines
  of the first selectable weeks, so the backtest says nothing about DST bucketing, which is covered by T1's view tests.
  Account 12 has 10 of the 55 location flags, all `higher`, against about 10 % of the location-weeks; its account-level
  weekly totals show no trend (32 to 68 events over the 25 complete weeks, no direction; one account-level flag,
  2026-06-29 at 68), so the 10 location flags are not a trailing-baseline lag on a growing account; their cause at
  location level was not investigated. If the ceiling ever fails, we discuss; we do not move a parameter.
- **Source:** [plans/T3-backend-api.md §2d, §7 (Q8)](../plans/T3-backend-api.md); [D-14](#d-14-verdict-parameters-and-the-too_quiet-rule).

## D-24: The aggregation-reviewer compares with the running API through a prefix-scoped `curl`
- **Context:** the T2 reviewer recomputed verdicts from the database and read `app/domain/`. At T3 the code that serves the numbers is the API
  mapping, and the domain can be right while the API maps it wrongly. Its last-complete-week check also was not blind, because PLAN §2 states
  2026-07-20.
- **Decision:** the reviewer derives each account's first and last complete week from the data and ignores any calendar date in PLAN. It may read the
  API mapping and `series.py` (the latter added after the first run could not read it), and, only after its own recompute is written, it calls
  `/api/weeks`, `/api/report` and `/api/locations/{location}/history` and compares totals, median, MAD, z, verdict, order and the weeks. Its tool is
  `Bash(curl -s http://127.0.0.1:8000/api/:*)`; the examples pass the week with `-G -d` and an unquoted URL so they match the prefix. The prompt allows
  only `-s`, `-G`, `-d` (the week) and `-H` (`X-Account-Id`), one URL per call.
- **Alternatives:** no HTTP step (the domain could be right while the API maps it wrongly); a wrapper script with a fixed URL allow-list, which would
  be enforced and not just instructed, rejected for the time budget, since the API is GET-only and the prefix plus the prompt are enough for a
  dev-only tool.
- **Consequences:** a prefix rule cannot forbid trailing flags such as `-o` or `--next`, so that part is instructed, not enforced, at the same level as
  D-19's ban on reading `tests/`. The permission syntax was not tested before the first run, which completed without a permission stop. The first run
  could not read `series.py`, so zero-fill and location start were checked through the API outputs only.
- **Source:** [plans/T3-backend-api.md §6, §7 (Q9), Deviations](../plans/T3-backend-api.md); `.claude/agents/aggregation-reviewer.md`;
  `ai-log/T3-aggregation-review.md`.

## D-25: API tests: a module-scoped seeded connection and dependency overrides
- **Context:** the seed tests load the seed inside a transaction that is rolled back, and its `TRUNCATE` holds `ACCESS EXCLUSIVE` locks until then,
  so a test using `conn` cannot run in the same module. The contract tests need both tiny fixtures and the real seed.
- **Decision:** the API tests live in `tests/api/` with their own `conftest.py`: a module-scoped `seeded_conn` (the pattern of
  `test_seed_anchors.py`) and a `make_client` that overrides `get_conn` (and optionally the parameters and bounds) and clears every override on
  teardown. The endpoints run on that one connection and never commit. Fixture tests use `conn`, seed tests and the backtest use `seeded_conn`, and no
  module mixes the two.
- **Alternatives:** seed once per session, which collides with the seed tests' `TRUNCATE` locks (found by reading `conftest.py` before planning); a
  throwaway database per module, which works but adds a database create and drop to every run when the `test_seed_anchors.py` pattern already solves it.
- **Consequences:** `TestClient` runs the sync endpoints in a worker thread, and the single connection is used by one request at a time, so this is
  safe. A new test module must pick one of the two fixtures.
- **Source:** [plans/T3-backend-api.md §2](../plans/T3-backend-api.md); `backend/tests/api/conftest.py`.

## D-26: The frontend is a Vite dev server in docker-compose, not static files served by FastAPI
- **Context:** D-13 wants a reviewer to need only Docker and make, so `make up` must bring up the whole app. T3 left open how the
  browser reaches the API (no CORS).
- **Decision:** a `web` service (`node:22-alpine`, `npm ci` in the image, the Vite dev server on `127.0.0.1:5173`) that proxies `/api` to
  `api:8000`. The browser sees one origin, so the backend gets no CORS middleware and no change. `./frontend` is bind-mounted over `/app`,
  and an anonymous volume keeps the image's `node_modules`; `make up` runs `up -V` so a changed `package.json` is never shadowed by an old
  volume. Frontend checks run with `docker compose run --rm --no-deps web ...` so they do not start api and db.
- **Alternatives:** `vite build` and serving `dist` from FastAPI (one origin and one container, but it couples the backend image to the
  frontend build and loses HMR); installing `node_modules` outside `/app`, like the backend's `/opt/venv` (Vite's `fs.allow` may then refuse
  files outside the project root; kept as the fallback); bind-mounting only `src` and the config files.
- **Consequences:** the Vite dev server is a dev tool, not a production serving story (README, T6). Each `make up` leaves the previous
  anonymous volume behind (11 to 13 volumes over two runs, measured in CP1a); `make reset` removes the current one, `docker volume prune` the
  rest (it removes every unused volume of every project on the machine, not just this one). Docker also creates an empty `frontend/node_modules` directory on the host as the mount point; it is git-ignored and holds nothing.
  `"node"` in `tsconfig` `types` makes `process` type-check in browser code too (known limit).
- **Source:** [plans/T4-frontend.md §1a, §7 (Q4)](../plans/T4-frontend.md); [D-13](#d-13-the-whole-app-runs-under-docker-compose-from-t1).

## D-27: URL reconciliation rules and the header-less bootstrap
- **Context:** the URL holds `account`, `week` and `location` (PLAN §5) and any of them can be stale or hand-edited. The UI cannot know
  the server's demo account (D-22) and must not hard-code 15.
- **Decision:** three pure stages in `frontend/src/reconcile.ts`, each applied when the data it needs has arrived. Account: no param means a
  header-less `/api/weeks`, and the account the server answered for is adopted into the URL (`replaceState`); a param that is not
  `String(id)` of a listed account is an error state, with no request sent and no fallback. Week: not in `/api/weeks` (malformed, a
  non-Monday, outside the range) falls back to `default_week` with a visible notice; no selectable weeks (account 20) removes the param.
  Location: exact match against the report's rows, otherwise dropped, with no history request. Corrections use `replaceState`, user changes
  `pushState` (an account change pushes `?account=B` alone, and B's default week is added by a `replaceState`), and `popstate` re-runs the
  same path. A late response of a superseded request is ignored, and an aborted request never renders an error.
- **Alternatives:** defaulting to the first listed account; falling back to the demo account on an unknown id (it would hide the error and
  show another account's data); showing the API's 422 for a stale week (the UI already has the week list, so it would send a request that
  can only fail); one `reconcile` over all data at once (the week and the location are only known after later requests).
- **Consequences:** the request waterfall is sequential on purpose. With an `account` param: `/api/accounts` first, then `/api/weeks` only if
  `reconcileAccount` returns `ok` (an unknown id never reaches an account-scoped endpoint), then `/api/report`, then
  `/api/locations/{location}/history`. With no `account` param: `/api/accounts` and the header-less `/api/weeks` in parallel (there is no id to
  validate), then report, then history. The account is only known to exist after `/api/accounts`; the week to request is only known after
  `/api/weeks` (so no request carries a stale week and no 422 comes from a URL); the location is only known to exist after `/api/report` (so
  no history request can 404 from a URL). The cost is four sequential round trips on a cold load with an `account` param (three without
  one); at demo size each is milliseconds, and parallel guessing would send requests that can fail and need cleanup. The bootstrap makes
  exactly one `/api/weeks` call. A missing header would silently select account 15 (D-22), so every request after the bootstrap carries it.
- **Source:** [plans/T4-frontend.md §1c, §2b, §2e](../plans/T4-frontend.md); [D-20](#d-20-one-report-service-behind-thin-endpoints-injectable-inputs-one-error-shape);
  [D-21](#d-21-selectable-weeks-are-per-account-and-judgeable-only-a-location-absent-at-w-is-a-404);
  [D-22](#d-22-account-from-an-x-account-id-header-with-a-demo-default-account-15-get-apiaccounts-is-unscoped).

## D-28: Presentation in T4: plain CSS, a glossary built from the API's parameters, the chart kept
- **Context:** the plan had styling out of T4 and the SVG chart as the first cut. Looking at the working screen,
  the numbers alone did not answer "is this normal for us?" at a glance, and terms like median, normal range and
  z-score are unfamiliar to most customer admins.
- **Decision:** (1) one plain `styles.css` (~100 lines, no class names, `[data-verdict]` selectors, the dataviz
  skill's surface/text tokens and status colors, checked with its validator in light mode); metrics as horizontal
  stat tiles, the only markup change being `<div>` wrappers around `<dt>/<dd>` pairs. (2) A collapsed glossary
  (`<details>`) above the location table, with the same one-line definitions as `title` on the table headers;
  every number in it comes from `report.parameters`, never a literal. (3) The chart (13 weeks against the selected
  week's band, native `<title>` per point, Y from 0 rounded up to a whole number) is no longer a cut item.
  `higher` and `lower` share one flag color: the flag is direction-neutral (PLAN §2), the text says the direction.
- **Alternatives:** Tailwind (a dependency, config and a lockfile change for one screen, no second use, PLAN §10);
  no styling ("function over form" in the brief); `title` attributes only (not reachable by touch or keyboard);
  a JS tooltip layer on the chart (the dataviz skill's default; the weeks table already carries the exact
  numbers); a per-row sparkline in the location table (deferred: /api/report has no per-location series, so it
  needs a backend change or one extra request per location); a chat over the data (rejected in D-10).
- **Consequences:** the copy follows configuration (R6, R14), so a changed `REPORT_*` value never makes the
  explanation contradict the rule. The glossary states a backend rule (edges count as unusual, D-17); if D-17
  changes, the copy must change. A single flag color may read as "bad" for a week that is higher than usual,
  which can be good news; a direction-specific treatment is an open product question (PLAN §12 #6). No dark mode,
  no responsive redesign.
- **Source:** [plans/T4-frontend.md §4 (CP3b, CP3c), Deviations](../plans/T4-frontend.md);
  [notes.md, T4 scope changes](../ai-log/notes.md).

## D-29: AI summary: an always-visible card backed by the template, id-only claims plus a validated headline
- **Context:** the optional AI summary (PLAN §11, D-10) is built before the docs ticket (T5 before T6, John's call). PLAN §6 says the endpoint is a 404 when the flag is off and needs a per-request opt-in; PLAN §11 says the model returns claims and no text is model-written.
- **Decision:** (1) The card is always visible. `POST /api/summary` returns 200 with the template and `reason: "disabled"` when the flag is off, and `nothing_to_summarize` for a null week (checked before the flag, the provider is never called). The opt-in is the user's click on the button; there is no body field and nothing runs on load. (2) The model returns near-enum claims (scope, a listed location id, metric `total`, the payload's verdict) **and a headline** of one or two sentences. The prompt carries locations as ids `L1`..`L5` with their numbers and **no names at all**, so a hostile location name never reaches the model. The headline may cite locations only as `[L1]`..`[L5]` tokens (the server substitutes the name), at most 200 characters, no digits, and a small direction lexicon rejects a sentence whose wording contradicts the verdict of a cited location or, for a sentence with no token, the account verdict when it is higher or lower. Any failure falls back to the template (`validation_failed`). The fact lines are always rendered by the server from the payload; a valid AI response differs from the template only by the headline and the order of the location lines. (3) `SUMMARY_PROVIDER=mock|anthropic`, mock by default; a missing key (or an adapter not built yet) falls back to the mock with a warning and the response reports the **effective** provider, so mock output is never labeled as a model's. The prompt is a versioned file (`prompts/summary-v1.md`, `PROMPT_VERSION` is its stem). The UI label shows source and provider (`AI summary · preview (mock provider)`, `Template summary — <reason>`).
- **Alternatives:** hide the card or return 404 when the flag is off; free-text claims, or numbers written by the model; claims only with a server-rendered text (a valid AI summary would equal the template, a gratuitous model call); location names in the prompt as delimited data; the flag alone choosing the provider; the opt-in as a body field; a framework such as LangChain (a single structured call with no tools or retrieval does not need it, and it would hide the validation inside the library; it would fit if the feature grew to multi-step or RAG).
- **Consequences:** **the headline's direction check is heuristic, and that is exactly why numbers never come from the model**: a wrong headline can mislead in tone but cannot show a wrong figure. It does not catch a sentence that swaps two locations' directions, number words ("twelve"), "nothing stands out" while locations are flagged, or direction words in a sentence with no token when the account is `normal`; the word "up" can also cause false rejections ("follow up on [L1]"), which fail safe to the template. Comparatives and superlatives (for example "largest gap") are not checked; the model only sees the listed locations, so such a claim is unverified beyond them. PLAN §6's 404 and per-request opt-in, and PLAN §11's "no model-written text", are superseded here (PLAN.md is not edited). `provider` is reported on template responses too, as a configuration fact. PLAN §13 says all 15 locations flag at account 6's spike; the seed shows 12 of 15 at 2026-06-01. The real adapter (`SUMMARY_PROVIDER=anthropic`) uses stdlib `urllib`, not `httpx` (a dev-only dependency: using it at runtime would change `pyproject.toml` and `uv.lock`), reads the answer by block type, asks for `effort: low`, and treats `max_tokens` and `refusal` stops as provider errors; it is smoke-tested by hand only. How to enable it: the README section "AI summary: status".
- **Source:** [plans/T5-ai-summary.md §0, §1, §5](../plans/T5-ai-summary.md).
