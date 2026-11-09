# T2: Backend core

Status: **APPROVED**. Q1–Q9: recommendations accepted as written.
Source: PLAN.md §2, §3, §8 (ticket 2), §9, §10; decisions D-02, D-03, D-06, D-08; T1 plan §9 Q9. Data facts: docs/data-profile.md.
Branch: `feat/T2-backend-core` (exists, checked out). No commits until asked.

**In:** pure domain logic (baseline, verdict, ranking, week arithmetic) with tests first; the typed
report settings; zero-filled weekly-series queries (account and location level) over `clean_events`.
**Out (all T3):** endpoints, `get_current_account`, response models, the backtest. Also out: frontend, AI,
per-type verdicts, any change to `data/`, `PLAN.md` or the migrations.

## 1. Design

```
backend/app/domain/__init__.py
backend/app/domain/models.py    Verdict, JudgeParams, Baseline, Judgement, WeekCounts, Series (frozen dataclasses)
backend/app/domain/stats.py     median, mad, spread
backend/app/domain/verdict.py   judge(history, x, params, *, has_events=True) -> Judgement
backend/app/domain/ranking.py   rank(items) -> list
backend/app/domain/weeks.py     last_complete_week, first_complete_week  (the only timezone code in T2)
backend/app/series.py           SQL: fetch_bounds, fetch_series (zero-filled), history_and_x helper
backend/app/settings.py         + ReportSettings (existing Settings untouched)
.env.example                    + the REPORT_* variables, commented
```

No I/O in `app/domain/`: it imports nothing from SQLAlchemy, settings or the DB. `app/series.py` imports
the domain dataclasses. Return types are dataclasses, not Pydantic (T3 maps them to API models), because
nothing here crosses a trust boundary (agreed in the pre-plan discussion).

### 1a. Statistics and verdict (pure)

- `median(v)`: sorted; odd → middle; **even → mean of the two middle values**.
- `mad(v) = median(|v_i − median(v)|)`, raw (no 1.4826 inside).
- `spread(v) = max(1.4826·MAD, √median, 1)`.
- `judge(history, x, params, *, has_events=True) -> Judgement`. `history` = prior complete weekly totals,
  oldest → newest, zero-filled, **all** the caller has; `judge` keeps the last `baseline_weeks` of them
  (the single place that trims). Precedence, first match wins:
  1. `not has_events` → `NO_ACTIVITY` (account with no events at all; baseline `None`).
  2. `len(window) < min_history_weeks` → `NOT_ENOUGH_HISTORY` (baseline `None`, `z None`).
  3. `median(window) < min_baseline_median` → `TOO_QUIET` (baseline present, `z None`). **Decided by the
     baseline median only, never by `x`.**
  4. `z = (x − median) / spread`, `d = x − median`. Flagged iff `|z| ≥ z_min` **and** `|d| ≥ min_abs`
     (both inclusive). Flagged → `HIGHER` if `d > 0`, else `LOWER`. Otherwise `NORMAL`.
- `Judgement(verdict, x, history_weeks, baseline: Baseline | None, z: float | None, diff: float | None)`.
- `Baseline(median, mad, spread, weeks_used, band_low, band_high)`. The band is the no-flag region:
  half-width `h = max(z_min·spread, min_abs)`, `band = (median − h, median + h)`; a week is normal iff
  `band_low < x < band_high`. Included so T3 doesn't reinvent it (Q7).
- `JudgeParams(baseline_weeks, min_history_weeks, z_min, min_abs, min_baseline_median)`, built from
  `ReportSettings.judge_params()`. Floats are compared directly; fixtures use exactly representable values at the
  boundaries (6/3.0 = 2.0).

### 1b. Ranking (pure)

`rank(items: Sequence[tuple[str, Judgement]]) -> list[tuple[str, Judgement]]`. Judged items (those with
`z is not None`, i.e. NORMAL/HIGHER/LOWER) first, ordered by `|z|` desc, then `|diff|` desc, then location
name asc. Unjudged (NOT_ENOUGH_HISTORY, TOO_QUIET) after, by name asc. Plain `sorted` with a key, no
stability tricks.

### 1c. Week arithmetic (pure, `zoneinfo`)

Inputs are naive UTC datetimes (what the DB returns). Aware inputs raise `ValueError`.

- `last_complete_week(as_of_utc, tz) -> date`: convert to local time (`replace(tzinfo=UTC).astimezone(ZoneInfo(tz))`),
  take the Monday of the local week containing it, **minus 7 days**. A week is complete once the instant
  Monday 00:00:00 local has arrived (D-03: "ended on or before as-of").
- `first_complete_week(data_start_utc, tz) -> date`: the Monday of the local week containing `data_start`,
  **plus 7 days unless `data_start` is exactly Monday 00:00:00 local** (then that Monday). Same conversion; Q1.
- Both are per account (its tz). **Inputs are injectable**: callers pass `as_of` and `data_start`; defaults come
  from `fetch_bounds` = `min/max(occurred_at)` over all of `clean_events` (global, not per account). Production
  would pass the wall clock for `as_of`.
- No other timezone logic anywhere in T2: series bucket only on `clean_events.local_week`.

### 1d. Series queries (`app/series.py`)

`fetch_bounds(conn) -> tuple[datetime | None, datetime | None]`: `min`, `max` of `occurred_at` in `clean_events`.

`fetch_series(conn, account_id, week, first_complete_week, lookback_weeks) -> AccountSeries`. `week` and
`first_complete_week` must be Mondays (`ValueError` otherwise, SQ15). SQL builds the weekly counts; **no statistics in
SQL** (no `percentile_cont`).

```sql
WITH ev AS (   -- the account's events, bucketed by the view's local_week; nothing here converts time
    SELECT location, local_week, event_type
    FROM clean_events WHERE account_id = :account_id
),
loc AS (       -- a location exists only through events (no locations table)
    SELECT location, GREATEST(min(local_week), :first_week) AS start_week
    FROM ev GROUP BY location
    HAVING GREATEST(min(local_week), :first_week) <= :week          -- no future data
),
grid AS (      -- zero-filled grid; window = last `lookback_weeks` prior weeks plus the selected week
    SELECT l.location, l.start_week, w::date AS week
    FROM loc l
    CROSS JOIN LATERAL generate_series(
        GREATEST(l.start_week, :week - (:lookback_weeks * 7)), :week, interval '7 days') AS w
)
SELECT g.location, g.start_week, g.week,
       count(*) FILTER (WHERE e.event_type = 'call_received')    AS call_received,
       count(*) FILTER (WHERE e.event_type = 'lead_created')     AS lead_created,
       count(*) FILTER (WHERE e.event_type = 'appointment_set')  AS appointment_set,
       count(*) FILTER (WHERE e.event_type NOT IN ('call_received','lead_created','appointment_set')) AS unknown
FROM grid g
LEFT JOIN ev e ON e.location = g.location AND e.local_week = g.week
GROUP BY g.location, g.start_week, g.week
ORDER BY g.location, g.week;
```

`LEFT JOIN` with `count(*) FILTER` counts only matched rows, so an empty week is a row of zeros. The account
series is the per-week sum of the location rows, computed in Python from the same result (so the account row is
always the sum of its locations); its `start_week` is the earliest location start. The function runs the series query
plus one `EXISTS` query for `has_events`. It
is zero-filled from there too. `AccountSeries(account_id, has_events: bool, account: Series | None, locations: tuple[Series, ...])`.
`has_events` = the account has any clean event at all (an `EXISTS`), and feeds `judge(has_events=…)`. `account` is `None` when
no location exists at W, which covers both "no events at all" (`has_events False`) and "events exist but all start after W"
(`has_events True`, open question Q8).

- Existence rule (decision 3): a location takes part in week W only if `start_week <= W`;
  `start_week = max(first event week, first_complete_week)`, so an event in the partial first week can't push the
  start before the first complete week. A location with 0 events in W **stays in the list** (zero row).
- Window: the grid starts at `max(start_week, W − lookback_weeks·7 days)` and ends at W; weeks before the
  start are never present (not zero). The last element is W (`x`), the rest is `history`. `judge` re-trims
  to `baseline_weeks` (equal to `lookback_weeks` when called with settings; the redundancy is deliberate and tested).
- Totals count only the 3 known types; `WeekCounts.unknown` carries the week's unknown-type count so T3 can
  show a data-quality warning (T1 plan, Q9). Nothing is dropped silently. A location whose only events are unknown-type still
  exists (existence is by any clean event), with total 0.
- `history_and_x(series) -> (list[int], int)`: `[w.total for w in weeks[:-1]]`, `weeks[-1].total`. If W is before the series
  start the location isn't returned, so this never sees an empty series.
- The selected account's data only: the query is always filtered by `account_id`.

### 1e. Settings (`ReportSettings`, separate class, `env_prefix="REPORT_"`)

The existing `Settings` has unprefixed `DATABASE_URL` etc. and compose sets them, so a global prefix would rename
them. A second class avoids that (Q4).

| Field | Env var | Default | Validation |
|---|---|---|---|
| `baseline_weeks` | `REPORT_BASELINE_WEEKS` | 12 | int ≥ 1 |
| `min_history_weeks` | `REPORT_MIN_HISTORY_WEEKS` | 8 | int ≥ 1 and ≤ `baseline_weeks` (model validator) |
| `z_min` | `REPORT_Z_MIN` | 2.0 | float > 0 |
| `min_abs` | `REPORT_MIN_ABS` | 3.0 | float ≥ 0 |
| `min_baseline_median` | `REPORT_MIN_BASELINE_MEDIAN` | 4.0 | float ≥ 0 |

Invalid values fail at start-up (pydantic `ValidationError`), not at first request. `judge_params()` returns the
`JudgeParams`. Module-level `report_settings = ReportSettings()`, same pattern as `settings`.

### 1f. Choosing the defaults (reasoning, not tuning)

All medians below are from read-only queries on the seeded dev DB (per-location zero-filled medians over the 12
weeks before 2026-07-20, 69 locations).

- **`min_abs = 3`:** PLAN §2 says a 2-event wobble must not be abnormal. 3 is the smallest integer above 2.
- **`z_min = 2.0`:** the constraint is that a silent week must be flaggable, as D-02 intends. With `x = 0`,
  `|z| = median / spread ≤ median/√median = √median`, so a "lower" flag needs `median ≥ z_min²`. `z_min = 2` → silence
  is flaggable from median 4. `z_min = 2.5` would need median ≥ 6.25 and `z_min = 3` median ≥ 9, so many locations in this
  seed could never flag a silent week (counts from the histogram below).
- **`min_baseline_median` (`too_quiet`) = 4 = `z_min²`:** below it a zero week cannot reach `z_min` even with the Poisson floor,
  so "normal" would say nothing about silence. At the median it works: median 4, `x = 0`: spread √4 = 2, `z = −4/2 = −2.0`,
  `d = 4 ≥ 3` → flagged (when the √median floor is the spread, i.e. 1.4826·MAD ≤ 2; V7). Median 3.5: spread √3.5 = 1.871, `z = −3.5/1.871 = −1.87` → not flaggable → `too_quiet`.
  Derived, then stored as its own setting so it can move independently.

Median distribution the choice rests on (floor of the median, locations):

| median | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |
|---|---|---|---|---|---|---|---|---|---|
| locations | 2 | 8 | 11 | 16 | 11 | 9 | 9 | 2 | 1 |

The two below 4 are account 18 Site A (median 3) and account 6 Site M (median 3.5): they become `too_quiet` for 2026-07-20.
For `z_min = 2.5` (threshold 6.25) at least 2+8+11 = 21 locations (medians 3 to 5.5) would be below it; for 3.0 (threshold 9)
2+8+11+16+11+9 = 57 would. So 2.0.

**Zero-week locations (profile §10):** their 12-week medians for W = 2026-07-20 are account 6 Site G **4.5**
(`6,4,3,7,5,57,4,5,3,0,4,6`), Site N **4** (`3,3,6,4,4,72,5,7,4,2,5,3`), account 18 Site C **4**
(`3,3,1,6,4,6,6,8,6,1,4,4`). All are ≥ 4, so they are **not** `too_quiet` for W = 2026-07-20. Only Site G's zero (2026-06-29) falls inside
that window; Site N's (02-23) and Site C's (03-23) are older. I computed W = 07-20 only; their effect at other W (e.g. Site C's zero
inside the window for W = 03-30 … 06-15) is not computed here and is left to the tests and the T3 backtest. A zero week in the
baseline counts as 0 and the median absorbs it. Site G example for W = 07-20 with a hypothetical silent week: sorted
`0,3,3,4,4,4,5,5,6,6,7,57` → median (4+5)/2 = 4.5; |dev| sorted `0.5×5, 1.5×4, 2.5, 4.5, 52.5` → MAD (1.5+1.5)/2 = 1.5;
spread = max(2.224, √4.5 = 2.121, 1) = 2.224; for `x = 0`, `z = −4.5/2.224 = −2.02`, `d = 4.5` → `LOWER`.

**Expected flag rate (idealized, Poisson with the √median floor, MAD ignored):** median 7 → half-width `max(3, 2·2.646) = 5.29`,
flag at `x ≥ 13` or `x ≤ 1`: P ≈ 2.70% + 0.73% = 3.4% per location-week, about 2.4 of 69 locations per week; median 4.5 → 5.1%.
A larger MAD only widens the band. This is a sanity number, not a target; the T3 backtest looks at the real rate and we don't tune
to it.

## 2. Tests, written first

Domain tests need no DB. Expected values below were recomputed with an independent stdlib script (`statistics.median`, `zoneinfo`)
while writing this plan. `tests/domain/` has its own tests; none touches shared state.

### 2a. `test_stats.py`

| # | Input | Arithmetic | Expected |
|---|---|---|---|
| S1 | odd `[1,3,10]` | sorted `1,3,10` → median 3; deviations `2,0,7` → sorted `0,2,7` → MAD 2 | median 3, MAD 2 |
| S2 | **even** `[2,4,6,8]` | middle two 4,6 → mean **5**; deviations `3,1,1,3` → sorted `1,1,3,3` → MAD = (1+3)/2 = **2** | median 5, MAD 2 |
| S3 | single `[7]` | median 7; deviation `0` | median 7, MAD 0 |
| S4 | empty | | `ValueError` |
| S5 | spread, **√median wins**: `[9]*12` | MAD 0 → `max(0, √9 = 3, 1)` | 3.0 |
| S6 | spread, **floor 1 wins**: `[0]*8` | MAD 0, √0 = 0 → `max(0, 0, 1)` | 1.0 |
| S7 | spread, **1.4826·MAD wins**: `[2,4,6,8]` | `1.4826·2 = 2.9652` vs √5 = 2.236 vs 1 | 2.9652 |
| S8 | spread, median 0.5: `[0,1]` | median 0.5, deviations `0.5,0.5` → MAD 0.5, `1.4826·0.5 = 0.7413`, √0.5 = 0.7071 | 1.0 (floor wins above both) |

### 2b. `test_verdict.py` (defaults: window 12, min history 8, `z_min` 2, `min_abs` 3, quiet 4)

| # | history → x | Arithmetic | Expected |
|---|---|---|---|
| V1 | `[9]*12`, x = 15 | median 9, MAD 0, spread 3; z = 6/3 = **2.0**, d = 6 | `HIGHER`; boundary: `z == z_min` flags |
| V2 | `[9]*12`, x = 14 | z = 5/3 = 1.667 | `NORMAL` |
| V3 | `[9]*12`, x = 3 | z = −6/3 = −2.0, d = −6 | `LOWER` |
| V4 | `[9]*12`, x = 15, `min_abs = 7` | z = 2.0 ≥ 2 but d = 6 < 7 | `NORMAL` (the abs guard acts alone) |
| V5 | `[9]*12`, x = 15, `min_abs = 6` | d = 6 ≥ 6 | `HIGHER` (boundary on `min_abs`) |
| V6 | `[6]*12`, x = 0 (silent week) | spread √6 = 2.449; z = −6/2.449 = −2.449, d = −6 | `LOWER` |
| V7 | `[4]*12`, x = 0 | median 4 (not < 4), spread 2, z = −2.0, d = −4 | `LOWER` (median exactly N is judged) |
| V8 | `[3,4]*6`, x = 0 | sorted 6×3, 6×4 → median (3+4)/2 = 3.5 < 4 | `TOO_QUIET`, `z None` |
| V9 | `[2]*12`, x = 50 | median 2 < 4 | `TOO_QUIET` (x never decides) |
| V10 | `[0]*8`, x = 3, `min_baseline_median = 0` | median 0, spread 1 (floor wins); z = 3.0, d = 3 | `HIGHER` (floor of 1 reachable only when quiet is lowered) |
| V11 | 7 prior weeks `[5]*7`, x = 5 | 7 < 8 | `NOT_ENOUGH_HISTORY`, baseline `None` |
| V12 | 8 prior weeks `[5]*8`, x = 5 | 8 ≥ 8, window = 8 weeks; median 5 | `NORMAL`, `weeks_used == 8` |
| V13 | 11 prior weeks `[5]*11` | uses all 11 | `weeks_used == 11` |
| V14 | `[100,100] + [5]*12` (14 weeks), x = 5 | window = last 12 → median 5; older 100s ignored | `NORMAL`, `weeks_used == 12`, median 5 |
| V15 | `[]`, `has_events=False` | | `NO_ACTIVITY` (precedence 1) |
| V16 | `[1]*7`, x = 0, `has_events=True` | 7 < 8 and median 1 < 4 | `NOT_ENOUGH_HISTORY` (precedence 2 before 3) |
| V17 | `[]`, x = 0, `has_events=True` | 0 < 8 | `NOT_ENOUGH_HISTORY` (account that starts after W) |
| V18 | band: `[9]*12`, defaults | h = max(2·3, 3) = 6 → band (3, 15) | `band_low 3.0`, `band_high 15.0`; x = 15 is outside (flagged), x = 14 inside |
| V19 | band: `[6]*12`, `min_abs` 3 | h = max(2·2.449 = 4.899, 3) | band (1.101, 10.899) |

### 2c. `test_ranking.py`

Hand-built `Judgement`s (exact `z`/`diff` values, no float arithmetic).

| # | Items (name: z, diff) | Expected order |
|---|---|---|
| R1 | A: −3.0, −6 · B: 2.0, 5 · C: 0.5, 1 | A, B, C (|z| desc, sign ignored) |
| R2 | A: 3.0, 5 · B: −3.0, −6 | B, A (tie on |z|, larger |diff|) |
| R3 | D: 2.0, 4 · C: 2.0, 4 · E: 2.0, 4 | C, D, E (full tie → name asc) |
| R4 | judged X: 0.1, 1 · unjudged NOT_ENOUGH_HISTORY "A" · unjudged TOO_QUIET "B" | X, A, B (unjudged after, by name) |
| R5 | input permuted 5 ways | identical output (deterministic) |
| R6 | empty | `[]` |

### 2d. `test_weeks.py` (fixtures reuse T1's arithmetic; offsets: Chicago CST −6 / CDT −5, DST began 2026-03-08 08:00 UTC)

| # | as_of UTC (naive), tz | Arithmetic | Expected |
|---|---|---|---|
| L1 | 2026-02-09 05:59:59, Chicago | −6 h → Sun 02-08 23:59:59; Monday of week 02-02; −7 | **2026-01-26** (week 02-02 not complete yet) |
| L2 | 2026-02-09 06:00:00, Chicago | −6 h → Mon 02-09 00:00:00; Monday 02-09; −7 | **2026-02-02** |
| L3 | 2026-03-09 04:59:59, Chicago | CDT −5 → Sun 03-08 23:59:59; Monday 03-02; −7 | 2026-02-23 |
| L4 | 2026-03-09 05:00:00, Chicago | −5 → Mon 03-09 00:00:00; Monday 03-09; −7 | 2026-03-02 (a fixed −6 would give 03-08 23:00 → 02-23: wrong) |
| L5 | 2026-07-27 03:00:00, Los Angeles | PDT −7 → **Sun 07-26** 20:00 (UTC date is Mon 07-27); Monday 07-20; −7 | 2026-07-13 (UTC logic gives 07-20) |
| L6 | 2026-07-26 19:00:00, Kolkata | +5:30 → **Mon 07-27** 00:30 (UTC date is Sun 07-26); Monday 07-27; −7 | 2026-07-20 (UTC logic gives 07-13) |
| L7 | seed as-of 2026-07-27 22:20:34 × the 6 zones | local Mon 07-27 at Chicago 17:20:34, New York 18:20:34, Denver 16:20:34, LA 15:20:34, Phoenix 15:20:34, UTC 22:20:34; Monday 07-27; −7 | **2026-07-20** for all six |
| L8 | aware datetime | | `ValueError` |
| L9 | invalid tz name | | `ZoneInfoNotFoundError` |
| F1 | data start 2026-02-01 10:57:44 × the 6 zones | local Sun 02-01 at Chicago 04:57:44, NY 05:57:44, Denver 03:57:44, LA 02:57:44, Phoenix 03:57:44, UTC 10:57:44; Monday 01-26; +7 | **2026-02-02** for all six |
| F2 | 2026-02-09 06:00:00, Chicago | exactly Mon 00:00:00 local | 2026-02-09 (no +7) |
| F3 | 2026-02-09 06:00:01, Chicago | Mon 00:00:01 | 2026-02-16 |

### 2e. `test_series.py` (integration, `conn` fixture: a rolled-back transaction on `relay_test`, tables empty between tests)

Setup: accounts A1 Chicago (id 1), A2 Denver (id 2). Mondays: 02-02, 02-09, 02-16, 02-23. `first_week = 2026-02-02`,
`lookback = 12` and the selected week `W = 02-09` unless stated. Rows are `(id, account, location, type, occurred_at UTC)`; Chicago CST −6 in February, so
`local = UTC − 6 h`.

| # | Fixture | Arithmetic | Expected |
|---|---|---|---|
| SQ1 | zero-fill: A1 Site A calls at 02-03 15:00 and 02-04 15:00 (week 02-02), 02-18 15:00 (week 02-16); W = 02-23 | weeks 02-02, 02-09, 02-16, 02-23 = 2, 0, 1, 0 | Site A totals `[2,0,1,0]`: history `[2,0,1]`, x = 0, and Site A is still present |
| SQ2 | location starting mid-series: Site B first event 02-17 10:00 UTC (Tue, week 02-16); W = 02-23 | start week 02-16; weeks 02-16, 02-23 | Site B weeks `[02-16, 02-23]` only; at W = 02-09 Site B is **absent** (future data guard) |
| SQ3 | partial first week: Site C events 02-01 16:00 UTC (Chicago Sun 10:00 → week 01-26) and 02-03 15:00 | the 01-26 event is outside the grid; start = max(01-26, 02-02) = 02-02 | Site C week 02-02 total 1; no 01-26 row |
| SQ3b | Site D whose only event is 02-01 16:00 UTC (partial week) | start clamped to 02-02 | Site D present, all zeros from 02-02 |
| SQ4 | by type + unknown: week 02-02: 2 `call_received`, 1 `lead_created`, 1 `appointment_set`, 1 `phone_call`, 1 `' Call_Received '` | view normalizes the padded type to call_received | calls 3, leads 1, appts 1, unknown 1, **total 5** (unknown excluded) |
| SQ5 | account sum, W = 02-23: Site A `[2,0,1,0]` (SQ1) + Site B (SQ2) weeks 02-16: 1 event, 02-23: 0 | per week: 02-02 2+(none)=2, 02-09 0, 02-16 1+1 = 2, 02-23 0+0 = 0 | account `[2,0,2,0]`, account start 02-02 |
| SQ6 | local bucketing: A1 event 2026-02-09 05:59:59 UTC (Chicago Sun 23:59:59) and 06:00:00 (Mon 00:00:00) | T1 W1/W2 | the first counts in week 02-02, the second in 02-09 (no extra tz code needed) |
| SQ7 | isolation: A2 has events in the same weeks/locations | | A1 series unchanged; A2 series contains only its own events |
| SQ8 | account with no events | | `has_events False`, `account is None`, `locations == ()` |
| SQ13 | account whose only events are in week 02-23, W = 02-09 | start 02-23 > W | `has_events True`, `account is None`, `locations == ()` |
| SQ14 | `fetch_bounds` on empty tables, then with events at 2026-02-01 10:57:44 and 2026-07-27 22:20:34 UTC | | `(None, None)`, then the (min, max) pair |
| SQ9 | exact duplicate row (same columns, ids 1 and 2) | view keeps the lowest id | counted once |
| SQ10 | lookback: Site A events every week from 02-02 to 05-18 (16 weeks), W = 05-18, lookback 12 | grid starts at W − 84 days = 02-23 | 13 rows, first week 02-23, last 05-18; the start is still computed from all-time events |
| SQ11 | events after W (week 02-23 when W = 02-16) | | not in the series, and no location appears only because of them |
| SQ12 | unknown-only location: Site E with one `phone_call` in week 02-02 | exists by any clean event | Site E present, totals 0, `unknown` 1 |
| SQ15 | `fetch_series` with `week` or `first_week` not a Monday (e.g. 2026-02-04) | a misaligned grid would silently produce wrong weeks | `ValueError` |

### 2f. `test_settings.py`

Defaults 12 / 8 / 2.0 / 3.0 / 4.0; `REPORT_Z_MIN=2.5` via `monkeypatch.setenv` overrides; `judge_params()` maps every field. Invalid
(each raises `ValidationError`): `baseline_weeks=0`; `min_history_weeks=0`; `min_history_weeks=13` with baseline 12; `z_min=0`;
`z_min=-1`; `min_abs=-1`; `min_baseline_median=-1`. Valid combination: baseline 6, min history 4.

### 2g. `test_seed_anchors.py` (integration on the real seed)

A **separate module** with a module-scoped fixture `seeded_conn`: one connection, `BEGIN`, `load_seed(conn)`, yield, `ROLLBACK`. It
must not share a module with tests that use `conn`: the seed's `TRUNCATE` takes `ACCESS EXCLUSIVE` locks on both tables until the
rollback, and a second connection would block. Other modules run after this one finishes. The dev DB is not touched.

All inputs come from the view; the verdict is computed by the T2 code. Hand-computed values (and the psql queries in the Appendix so they can be
rechecked independently):

| # | Anchor | Arithmetic | Expected |
|---|---|---|---|
| A1 | **Account 6, W = 2026-06-01**, account series. 12 prior weeks 03-09 … 05-25: `84,81,71,82,76,55,64,86,68,78,62,53`, x = **880** | sorted `53,55,62,64,68,71,76,78,81,82,84,86`; median (71+76)/2 = **73.5**; |dev| `10.5,7.5,2.5,8.5,2.5,18.5,9.5,12.5,5.5,4.5,11.5,20.5` → sorted `2.5,2.5,4.5,5.5,7.5,8.5,9.5,10.5,11.5,12.5,18.5,20.5` → MAD (8.5+9.5)/2 = **9.0**; spread = max(1.4826·9 = 13.343, √73.5 = 8.573, 1) = 13.343; z = (880 − 73.5)/13.343 = **60.44**, d = 806.5 | `HIGHER`, `weeks_used 12`, z ≈ 60.44 |
| A2 | **Account 1 Site A, W = 2026-07-20.** 12 prior (04-27 … 07-13): `8,7,6,6,5,7,9,11,7,10,7,9`, x = 9 | sorted `5,6,6,7,7,7,7,8,9,9,10,11` → median (7+7)/2 = 7; |dev| `1,0,1,1,2,0,2,4,0,3,0,2` → sorted `0,0,0,0,1,1,1,2,2,2,3,4` → MAD (1+1)/2 = 1; spread = max(1.4826, √7 = 2.646, 1) = 2.646; z = 2/2.646 = 0.756, d = 2 < 3 | `NORMAL`, z ≈ 0.756 |
| A3 | **Account 20** (no events) | `has_events False`, `account is None` | `NO_ACTIVITY` |
| A4 | **Not enough history:** account 1 Site A, W = 2026-03-23, then W = 2026-03-30 | complete weeks start 02-02: before 03-23 there are 02-02 … 03-16 = **7**; before 03-30 there are **8** | 03-23 `NOT_ENOUGH_HISTORY`; 03-30 judged (`weeks_used 8`, not NEH) |
| A5 | **Last complete week, all accounts:** `fetch_bounds` → as-of 2026-07-27 22:20:34, data start 2026-02-01 10:57:44; for every account tz | L7 and F1 for the 6 zones | `last_complete_week == 2026-07-20` and `first_complete_week == 2026-02-02` for all 20 accounts, including 2 and 8 (no events in the partial week) and 20 (no events) |
| A6 | Zero-filled real series: account 6 Site G, W = 2026-07-13 | 12 prior weeks 04-20 … 07-06; 06-29 = 0, 06-01 = 57 | the series contains an explicit `0` for 06-29 |
| A7 | All 69 locations are present at W = 2026-07-20 | profile §1, §6, §10 | 69 location series (account 6: 15), each with 13 weeks |
| A8 | Unknown types in the seed | profile §5; T1 DQ test | `sum(unknown) == 0` over every series |
| A9 | **Account 6 Site G, W = 2026-07-20**, location series (from the aggregation-reviewer). History `6,4,3,7,5,57,4,5,3,0,4,6`, x = 6 | sorted `0,3,3,4,4,4,5,5,6,6,7,57` → median 4.5; |dev| sorted `.5×5,1.5×4,2.5,4.5,52.5` → MAD 1.5; spread = max(2.2239, √4.5 = 2.121, 1) = 2.2239; z = 1.5/2.2239 = 0.674, d = 1.5 < 3 | `NORMAL`, z ≈ +0.674 |
| A10 | **Account 9 Site B, W = 2026-05-04**, location series (from the aggregation-reviewer). History `11,10,8,4,8,7,9,9,9,8,14,10`, x = 3 | sorted `4,7,8,8,8,9,9,9,10,10,11,14` → median 9; |dev| sorted `0,0,0,1,1,1,1,1,2,2,5,5` → MAD 1; spread = max(1.4826, √9 = 3, 1) = 3.0; z = −6/3.0 = **−2.0 exactly**, d = −6 | `LOWER`; boundary case for the `>=` flag rule |

The input series of A1 and A2 were read from the seeded dev DB with read-only queries (Appendix) and the statistics redone by hand and
with a stdlib script; A4 is calendar arithmetic. The profile's 881 for account 6 is raw, the view gives 880. Whether the
**independent** recompute agrees is a Done-when item, not claimed here.

## 3. Make targets / commands

No new targets. `make check` stays `lint` (`ruff check .` + `ruff format --check .`), `typecheck` (`mypy`, strict, `app` + `tests`),
`test` (`pytest -q`), all in the api container. New domain tests need no DB; the series and anchor tests use `relay_test` as in T1.
Config: `.env.example` gains the commented `REPORT_*` variables; `docker-compose.yml` is unchanged (defaults are in code).

Implementation order (tests first, each red before green): `stats` → `verdict` → `ranking` → `weeks` → `ReportSettings`
→ `series` (needs Postgres) → seed anchors → decisions log → reviewer subagent (at close).

## 4. Decision-log entries (written in the same change)

- **D-14:** verdict parameters and `too_quiet`: defaults `z_min 2.0`, `min_abs 3`, `min_baseline_median 4` with the §1f reasoning;
  alternatives: higher `z_min`, `too_quiet` by `x` or by a fixed volume threshold, no `too_quiet` tier.
- **D-15:** pure statistics in Python, SQL only builds the zero-filled series; location existence rule (no future data, silent
  week stays); injectable as-of and `last_complete_week` / `first_complete_week` as the only timezone code.
  Alternatives: `percentile_cont` in SQL, a per-account `max(local_week) − 1`, a locations table.
- **D-16:** unknown event types: totals count the 3 known types, the series carries the unknown count; update the "T2 input" lines in
  D-06 and D-08 consequences to point here.

## 5. Done when

- [ ] Every row of §2 exists as a test and passes; `make check` is green (ruff, ruff format, mypy strict, pytest) — record the pass count.
- [ ] `app/domain/` imports nothing from `sqlalchemy`, `app.settings` or the DB (checked with `grep`, no `percentile_cont` anywhere in `app/`).
- [ ] Seed anchors A1–A8 pass against the seeded test DB.
- [ ] **Independent check of the anchors by John:** recomputes A1, A2 and A4 in psql (queries in the Appendix) and compares with §2g.
- [ ] **Independent check by the `aggregation-reviewer` subagent** (`.claude/agents/aggregation-reviewer.md`, built at T2 close): clean context,
  read-only Bash (`psql`) plus Read/Grep, instructed (not technically enforced) not to read `tests/` or §2 of this plan. It gets PLAN §2 and the view definition, **no expected
  values**, and recomputes from `clean_events` on its own: account 6 at 2026-06-01, two (account, location, week) cases of its choice
  (one with a zero week in the baseline), and each account's last complete week. Its numbers are compared with the tests' by me afterwards, and
  it also reads `app/domain/` against PLAN §2 for deviations. Findings are pasted into the ai-log.
- [ ] `ReportSettings` rejects every invalid case in §2f; defaults match §1e.
- [ ] D-14, D-15, D-16 added to `docs/decisions.md`; D-06 and D-08 "T2 input" lines updated.
- [ ] `git diff --exit-code main -- data/ PLAN.md backend/migrations/` is empty; no endpoint, no `get_current_account`, no response model added.
- [ ] Nothing committed without your say-so.

## 6. Open questions (decision needed)

| # | Issue | Recommendation | Trade-off |
|---|---|---|---|
| Q1 | **The partial first week needs a lower bound too.** Your rule "partial weeks never enter any series" has no source for the first one: `max(local_week)`-style tricks fail (profile §3: only 8 of the 19 accounts with data have an event in week 01-26, so for the other 11 `min(local_week)` of the account is 02-02 or later), and the earliest week per account is not the data start. | Add `first_complete_week(data_start_utc, tz)` next to `last_complete_week`, with `data_start = min(occurred_at)` over the view (global). Same `zoneinfo` conversion, so it **widens "the only timezone code" from one function to two** (same module, same rule). Gives 2026-02-02 for all 6 zones (F1). | Alternative with no tz code: `min(local_week)` over the whole view + 7 days. Works on the seed, but it assumes the first week is always partial, the same assumption you rejected for the last one. |
| Q2 | **Sunday 23:59:59 as the as-of.** With the default `as_of = max(occurred_at)`, data ending Sunday 23:59:59 makes that week "not complete" (L1: it ends at Monday 00:00:00). Your `last_complete_week` is right by D-03's definition, but it differs from "the data covers the whole week" if the last tick is 23:59:59. | Keep the strict definition; `max(occurred_at)` is a lower bound of the true clock and the wall clock in production has no such gap. | None here: on the seed the as-of is Monday 22:20:34 UTC. |
| Q3 | **`too_quiet` N.** PLAN never defines it. | `median < min_baseline_median`, default **4 = z_min²** (the smallest median where a zero week can reach `z_min`, §1f), a separate setting. For 2026-07-20 it marks 2 of 69 locations (account 18 Site A, median 3; account 6 Site M, 3.5). The three zero-week locations have medians 4.5 / 4 / 4 at that week: not `too_quiet`. Account-level medians for that week: lowest non-empty is 7 (account 16), so no account is `too_quiet`; account 20 is 0 but is `no_activity` first. | A fixed N = z_min² moves with `z_min`; making it separate means a bad combination (N < z_min²) is possible but only costs a verdict that can never fire. No cross-validation added. |
| Q4 | **Env var prefix.** `Settings` is unprefixed (`DATABASE_URL`) and PLAN §10 names `LLM_SUMMARY_ENABLED` unprefixed. | `REPORT_` for the five report parameters, separate class. The AI flag keeps its PLAN name later. | Two naming styles. A global prefix would rename `DATABASE_URL` in compose. |
| Q5 | **PLAN §2: the floor of 1 in `spread` is dead code in the verdict path.** `√median < 1` only for median < 1, and `too_quiet` (N ≥ 1) catches those first. | Keep the floor per PLAN (and test it directly, S6/S8, and through V10 with N = 0). | A formula term that can't fire with default settings; it only matters if someone lowers N below 1. |
| Q6 | **Existence by any clean event, clamped to the first complete week** (SQ3, SQ3b, SQ12). A location whose only events are in the partial first week, or are unknown-type, still exists (zero history). | Yes: existence = any clean event, and the clamp avoids pre-data weeks. | Such a location would show as `not_enough_history` or `lower` rather than vanish. Doesn't occur in the seed (profile §6). |
| Q7 | **`Baseline.band` in T2.** PLAN §6 has `baseline{median, band}`, and the band must equal the verdict's no-flag region to not contradict it. | Define it here: `median ± max(z_min·spread, min_abs)` (V18). T3 only serializes it. | Slight scope add (4 lines); avoids T3 inventing a second definition. |
| Q8 | **Account that starts after W** (no events ≤ W, but some later). Not `no_activity` (events exist). | `AccountSeries.has_events True`, `account None` (SQ13) → `NOT_ENOUGH_HISTORY` with 0 weeks (V17); T3 decides whether such a week is selectable at all. | The empty state for "no events at all" stays account-level only. |
| Q9 | **`z_min = 2.0`, `min_abs = 3` rest on arithmetic, not a backtest.** Idealized flag rate ≈ 3.4% per location-week at median 7 (≈2.4 of 69 per week). | Accept as defaults; the T3 backtest only checks (account 6 spike flags, ordinary weeks rarely do). | If the real rate is too high, raising `z_min` costs silent-week detection (§1f); we change the setting, not the code. |

## Appendix: queries for the independent recompute (read-only, `make psql`)

```sql
-- A1: account 6, account-level totals per week 2026-03-09 .. 2026-06-01 (last value is x)
SELECT w::date, count(e.id) FROM generate_series('2026-03-09'::date,'2026-06-01','7 days') w
LEFT JOIN clean_events e ON e.account_id = 6 AND e.local_week = w::date GROUP BY 1 ORDER BY 1;
-- A2: account 1 Site A, weeks 2026-04-27 .. 2026-07-20 (last value is x)
SELECT w::date, count(e.id) FROM generate_series('2026-04-27'::date,'2026-07-20','7 days') w
LEFT JOIN clean_events e ON e.account_id = 1 AND e.location = 'Site A' AND e.local_week = w::date GROUP BY 1 ORDER BY 1;
-- A4: complete weeks before 2026-03-23 / 2026-03-30 (first complete week = 2026-02-02)
SELECT count(*) FROM generate_series('2026-02-02'::date,'2026-03-16','7 days') w;   -- 7
SELECT count(*) FROM generate_series('2026-02-02'::date,'2026-03-23','7 days') w;   -- 8
```

## Deviations

- `docker-compose.yml` (plan §3 said unchanged): the five `REPORT_*` variables are passed through the `x-api` environment with no default, so `.env` and shell overrides reach the container and defaults live only in `ReportSettings` (approved in the batch 1 review).
- A9, A10 added from the aggregation-reviewer's independent cases.
