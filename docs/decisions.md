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
- **Source:** [PLAN.md §2, §10](../PLAN.md); [notes.md, session 02](../ai-log/notes.md); T2 plan (parameter values, pending).

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
  unconfirmed (PLAN §12 #7: if they are legitimate, counts are 0.1% low). What happens to unknown
  event types at query time is a T2 input.
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
  conservative tier and a lightweight backtest mitigate (PLAN §13). Whether totals count only the 3
  known event types, plus a visible data-quality warning when others appear, is a T2 decision.
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
