# T3: Backend API

Status: **APPROVED**, with these review changes applied: (1) S8 window wording fixed (history 04-27 … 07-13, x = 9 is 07-20);
(2) the field is `unknown_events_in_window` (window sum, Q5 kept); (3) `week` is `str | None` parsed in `resolve_week`, so `RequestValidationError`
only covers the header (`invalid_request`); (4) D-23 (error shape) folded into D-20, S14 dropped, the backtest entry is now D-23;
(5) D-22 states plainly that account 15 is the only one with a flagged location at 2026-07-20, a configurable demo choice.
Source: PLAN.md §1, §2, §6, §8 (ticket 3), §9, §10; decisions D-02, D-03, D-08, D-14 to D-19; T2 plan §1c, §1d, §6 (Q8). Data facts: docs/data-profile.md.
Branch: `feat/T3-backend-api` (created, checked out). No commits until asked. `ai-log/notes.md` was already modified
when the branch was created; it is not part of T3 and stays out of the plan commit unless you say otherwise.

**In:** FastAPI endpoints, the `get_current_account` dependency, Pydantic response models, one error shape, one service
module (`build_report`) used by the endpoints **and** the backtest, the lightweight backtest (PLAN §9), the
`aggregation-reviewer` change for T3 (§6).
**Out:** frontend, AI summary, per-type verdicts, CORS/Vite proxy (T4 decision), auth, any change to `data/`, `PLAN.md`,
migrations or the T2 domain code. If T2 code looks wrong it becomes an open question, it is not fixed here.
`app/series.py` gets one new query function (`fetch_account_start`, §1c); nothing existing in it changes.

## 1. Design

```
backend/app/errors.py     ApiError(status, code, message); handlers -> {"error": {"code", "message"}}
backend/app/schemas.py    Pydantic v2 response models (§1b)
backend/app/deps.py       get_conn, get_judge_params, get_bounds, get_current_account
backend/app/report.py     pure helpers (weeks_range, resolve_week) + build_weeks / build_report / build_history
backend/app/api.py        APIRouter(prefix="/api"): accounts, weeks, report, location history; thin, no logic
backend/app/main.py       include_router, register error handlers (health stays as is)
backend/app/settings.py   Settings += demo_account_id: int = 15   (env DEMO_ACCOUNT_ID; Settings otherwise untouched)
backend/app/series.py     += fetch_account_start(conn, account_id, first_complete_week) -> date | None
```

Sync `def` endpoints, sync SQLAlchemy, no CORS middleware (T4 decides how it reaches the API).

### 1a. Dependencies (`deps.py`)

- `get_conn(engine) -> Iterator[Connection]`: `with engine.connect() as c: yield c`. Endpoints only read, nothing commits;
  the connection is rolled back on close. Tests override this one dependency.
- `get_judge_params() -> JudgeParams`: `report_settings.judge_params()`. Overridable.
- `get_bounds(conn) -> Bounds(data_start, as_of)`: `fetch_bounds(conn)`, both `None` on an empty view. **Never `now()`.** Overridable.
- `get_current_account(conn, x_account_id: Header(ge=1) | None) -> Account(id, name, timezone)`: header `X-Account-Id`;
  missing → `settings.demo_account_id` (15, Q1); id not in `accounts` → 404 `account_not_found`; non-integer or < 1 → 422
  `invalid_request`. The account never comes from a path or query parameter; every query takes `account.id`.

### 1b. Endpoints and response models

| Endpoint | Returns |
|---|---|
| `GET /api/accounts` | `[{id, name, timezone}]` ordered by id. Demo switcher only; the one endpoint that is not account-scoped (Q3). |
| `GET /api/weeks` | `{account, weeks: [date], default_week: date \| null, as_of}` |
| `GET /api/report?week=` | `Report` |
| `GET /api/locations/{location}/history?week=` | `History` |

```
Parameters   baseline_weeks, min_history_weeks, z_min, min_abs, min_baseline_median       (the 5 REPORT_* values)
ByType       call_received, lead_created, appointment_set
BaselineOut  median, mad, spread, weeks_used, band_low, band_high                         (D-17; floats unrounded)
DataQuality  unknown_events_in_window: int   sum of `unknown` over the series window (baseline weeks + selected week), D-16;
             deliberately not `unknown_events`: `total` is the selected week only, this field is not
Summary      total: int | null, verdict, z: float | null, diff: float | null, history_weeks: int,
             baseline: BaselineOut | null, by_type: ByType | null, data_quality: DataQuality
LocationRow  Summary + location: str
Report       account{id,name,timezone}, week: date | null, as_of: datetime | null, parameters,
             account_summary: Summary, locations: [LocationRow]   (rank order)
History      account, location, week, as_of, parameters, verdict, z, diff, baseline | null,
             weeks: [{week, total, by_type, role: "baseline" | "selected"}], data_quality
```

- `z`, `baseline` are `null` when unjudged; `verdict` says why (`not_enough_history`, `too_quiet`, `no_activity`).
- `as_of` is serialized as UTC (`2026-07-27T22:20:34Z`); `null` only on an empty view. Floats are never rounded.
- `by_type` and `total` are those of the selected week (`weeks[-1]`); unknown-type events are in neither (D-16).
- `locations` order = `rank()` from T2 (judged by `|z|`, then `|diff|`, then name; unjudged after, by name). No sorting in `api.py`.
- PLAN §6 names a location `score`; it is not defined anywhere. The API returns `z` and `diff`, and the order is the ranking (Q2).

### 1c. Selectable weeks, week validation, `build_*` (`report.py`)

Per account (its own timezone):

```
start      = fetch_account_start(conn, account.id, first_complete_week(data_start, tz))
           = GREATEST(min(local_week) over the account's clean events, first complete week)      (None: no events)
last       = last_complete_week(as_of, tz)                                                        (T2, injectable as_of)
first_sel  = start + min_history_weeks * 7 days
weeks      = every Monday from first_sel to last, inclusive; [] if start is None, bounds are None or first_sel > last
default_week = last if weeks else None
```

`first_sel` is exactly the first week where the **account** series has `min_history_weeks` prior weeks, so an account
verdict is never `not_enough_history` inside the range (backtest check B4). Locations that start later are
`not_enough_history` inside the range; a location that starts after W is absent (404 on history, not listed in the report).

`resolve_week(week | None, weeks)`: `None` → `default_week` (may be `None`). Given: must be in `weeks`, else 422 `invalid_week`
with the message `week must be a Monday in the selectable range 2026-03-30 .. 2026-07-20` (or `no selectable weeks for this account`).
A Tuesday and an out-of-range Monday get the same code and the range in the message.

`build_report(conn, account, week, params, bounds) -> Report`:
1. weeks/default as above. `week is None` (no selectable week): account has no events → `account_summary.verdict = no_activity`
   (the T2 meaning: no events at all); has events but no judgeable week → `not_enough_history`. Both `200`, `week = null`,
   `total/baseline/by_type = null`, `locations = []`.
2. Otherwise `fetch_series(conn, account.id, week, first_complete_week, params.baseline_weeks)`; `history_and_x` +
   `judge(history, x, params, has_events=...)` for the account series and every location; `rank` over the locations; map to `Report`.
3. `parameters` and `as_of` always echoed.

`build_history(conn, account, location, week, params, bounds)`: week check first (422), then the same `fetch_series`,
then the location by **exact** name (D-06 no case folding). Not in the series (never had events, other account's name,
or starts after W) → 404 `location_not_found` (T2 existence rule: a location exists at W only through events up to W; a 200
for a location that starts after W would leak future data). `weeks` = the series window (up to `baseline_weeks` prior weeks
clipped at the location's start, plus the selected week); the prior ones are `role: baseline`, the last `selected`. **One** band: the
selected week's `Baseline.band` (D-17); no per-week rolling bands (deferred).
If the week is omitted and the account has no selectable week, 404 `location_not_found` (no location can exist).

Location in the path is a plain `{location}` (names with `/` are not supported; none in the data, Q7).

### 1d. Error contract (`errors.py`)

One body for every non-2xx the API produces: `{"error": {"code": str, "message": str}}`, via handlers for `ApiError`,
`RequestValidationError` and Starlette's `HTTPException`. (FastAPI's default 422 body is replaced.) `week` is declared `str | None` and parsed
in `resolve_week`, which raises `invalid_week`; so `RequestValidationError` can only come from the `X-Account-Id` header and always maps to `invalid_request`
(no inspection of `loc`).

| Case | Status | `code` |
|---|---|---|
| `X-Account-Id` unknown | 404 | `account_not_found` |
| `X-Account-Id` non-integer or < 1 | 422 | `invalid_request` |
| `week` not a date (parsed in `resolve_week`), not a Monday, outside the range, or the account has no selectable week | 422 | `invalid_week` |
| location unknown for the account, or starts after W | 404 | `location_not_found` |
| unknown route / other HTTP errors | their status | `not_found` / `http_error` |

Check order: account → week → location. `no_activity` is never an error: it is a 200 empty state for the account only.

### 1e. Deliberately not done

Rounding, per-week rolling bands, per-type verdicts, caching, a locations table, `readonly` connection options, `POST /api/summary`,
CORS, auth. The backtest result is recorded, never used to tune a parameter.

## 2. Tests, written first

**Isolation (read `tests/conftest.py`, `test_seed.py`, `test_seed_anchors.py`).** `relay_test` is recreated and migrated empty
each run; nothing commits data. `conn` is a rolled-back transaction per test. Seed tests load the seed inside a transaction on a
module-scoped connection and roll back at module end; their `TRUNCATE` holds `ACCESS EXCLUSIVE` locks until then, so a module
that uses `seeded_conn` never shares a module with one that uses `conn`. All new tests live in `tests/api/` with its own
`conftest.py`:

- `tests/api/conftest.py`: `client(conn_like)` fixture factory that sets `app.dependency_overrides[get_conn] = lambda: connection`
  (and clears **all** overrides on teardown, so `test_health` is unaffected), `seeded_conn` (module scope, same pattern as
  `test_seed_anchors.py`; defined here, the T2 module is not touched), and an `add_events` helper (rows inserted on the rolled-back
  connection; the endpoints run on that same connection, so they see uncommitted rows).
- `test_report_unit.py` (no DB), `test_api_fixture.py` (uses `conn`), `test_api_seed.py` (uses `seeded_conn`), `test_backtest.py`
  (uses `seeded_conn`). Four modules, run one after the other; none destroys state another needs, and no module mixes the two fixtures.
- `TestClient` runs sync endpoints in a worker thread; the single connection is used by one request at a time, so this is safe.

### 2a. `test_report_unit.py` (pure)

| # | Input | Arithmetic | Expected |
|---|---|---|---|
| U1 | start 2026-02-02, last 2026-07-20, min history 8 | first = 02-02 + 56 d = **03-30**; 03-30 … 07-20 = 112 d = 16 steps | 17 weeks, default 07-20 |
| U2 | start 2026-07-13, last 07-20, min history 8 | first = 09-07 > last | `[]`, default `None` |
| U3 | start 2026-02-02, last 02-23, min history 2 | first = 02-16 | `[02-16, 02-23]` |
| U4 | start `None` | no events | `[]`, `None` |
| U5 | `resolve_week`: `None` → default; a listed week → itself; Tuesday, week before first, week after last | | default; ok; three `ApiError(422, invalid_week)`, message contains `2026-02-16 .. 2026-02-23` |

### 2b. `test_api_fixture.py` (tiny hand-computed data)

Overrides: params `baseline_weeks 4, min_history_weeks 2, z_min 2.0, min_abs 3.0, min_baseline_median 4.0`; bounds
`data_start 2026-02-02 06:00:00`, `as_of 2026-03-02 06:30:00` (naive UTC). February/March until 03-07 is CST (−6) / MST (−7). Every event is
inserted on the Wednesday of its week at 15:00 UTC (Chicago 09:00, Denver 08:00), so the local week is the intended one.

Time arithmetic: Chicago: 06:30 UTC → Mon 03-02 00:30 → week 03-02, minus 7 → **02-23**. Denver: 06:30 − 7 h → Sun 03-01 23:30 → week 02-23,
minus 7 → **02-16** (a UTC-based week would give 02-23 for both). `data_start` 06:00 UTC: Chicago Mon 02-02 00:00 exactly → first complete week
02-02; Denver Sun 02-01 23:00 → week 01-26 + 7 → 02-02.

Accounts: **1** Acme (Chicago), **2** Bolt (Denver), **3** Empty (Chicago, no events), **4** Newco (Chicago). Weekly totals, weeks 02-02 / 02-09 / 02-16 / 02-23:

| Account / location | 02-02 | 02-09 | 02-16 | 02-23 | Types |
|---|---|---|---|---|---|
| 1 `Site A` | 5 | 5 | 5 | 11 | all calls, except 02-23: 6 calls, 3 leads, 2 appointments; plus one `phone_call` (unknown) in week 02-23 |
| 1 `Main St` | 6 | 4 | 6 | 6 | calls |
| 1 `Late` | 0 | 0 | 0 | 5 | calls (first event week 02-23) |
| 2 `Site A` | 4 | 4 | 4 | 4 | calls |
| 4 `Site A` | 0 | 0 | 0 | 5 | calls |

Account 1 rollup (known types only): 11, 9, 11, 22 (02-23: 11 + 6 + 5; calls 17, leads 3, appointments 2).

| # | Request | Arithmetic | Expected |
|---|---|---|---|
| W1 | `/api/weeks`, header 1 | start 02-02 → first = 02-02 + 14 d = 02-16; last 02-23 | `weeks [02-16, 02-23]`, default 02-23, `as_of 2026-03-02T06:30:00Z` |
| W2 | `/api/weeks`, header 2 (Denver) | last 02-16 (above); first 02-16 | `weeks [02-16]`, default 02-16 |
| W3 | header 3 (no events) | start `None` | `weeks []`, default `null` |
| W4 | header 4 (starts 02-23) | first = 02-23 + 14 d = 03-09 > last 02-23 | `weeks []`, default `null` |
| W5 | no header, `settings.demo_account_id` monkeypatched to 1 | | account id 1 (same body as W1) |
| W6 | no header, demo id left at 15 (not in the fixture) | | 404 `account_not_found` |
| W7 | `/api/accounts` | | the 4 accounts, ordered by id, with name and timezone |
| W8 | no events anywhere, real `get_bounds` (bounds `None`), header 3 | | `/api/weeks` `[]`/`null`, `/api/report` 200 `no_activity`, `as_of null` |
| R1 | `/api/report`, header 1, no week | default 02-23. Account history `[11, 9, 11]`, x = 22: sorted 9,11,11 → median 11; deviations 0,2,0 → sorted 0,0,2 → MAD 0; spread = max(0, √11 = 3.3166, 1) = 3.3166; z = 11/3.3166 = **3.3166**, diff 11; h = max(2·3.3166 = 6.6332, 3) → band **(4.3668, 17.6332)** | week 02-23; account `total 22`, `higher`, median 11, mad 0, spread 3.3166, z 3.3166, weeks_used 3, by_type 17/3/2, `unknown_events_in_window 1` |
| R2 | same | `Site A` history `[5,5,5]`, x 11: median 5, MAD 0, spread = max(0, √5 = 2.2361, 1) = 2.2361; z = 6/2.2361 = **2.6833**, diff 6 ≥ 3 → `higher`; h = max(4.4721, 3) → band (0.5279, 9.4721). `Main St` `[6,4,6]`, x 6: median 6, MAD 0 (deviations 0,2,0), spread √6 = 2.4495, z 0 → `normal`. `Late`: history `[]` (0 < 2) | `locations` order `[Site A, Main St, Late]`; Site A total 11, by_type 6/3/2, unknown 1; Main St total 6, z 0.0; Late `not_enough_history`, `history_weeks 0`, `z null`, `baseline null` (unjudged after judged) |
| R3 | header 1, `week=2026-02-16` | account history `[11, 9]`, x 11: median 10; deviations 1,1 → MAD 1; spread = max(1.4826, √10 = 3.1623, 1) = 3.1623; z = 1/3.1623 = **0.3162** → `normal`; band h = max(6.3246, 3) → (3.6754, 16.3246). `Site A` `[5,5]`, x 5: z 0. `Main St` `[6,4]`, x 6: median (4+6)/2 = 5, MAD 1, spread = max(1.4826, √5 = 2.2361, 1) = 2.2361, z = 1/2.2361 = **0.4472**. `Late` starts 02-23 > W | account total 11, `normal`, median 10, mad 1; locations `[Main St, Site A]` (|z| 0.4472 before 0); `Late` absent |
| R4 | any report | | `parameters` = `{4, 2, 2.0, 3.0, 4.0}`, `as_of` = `2026-03-02T06:30:00Z` |
| R5 | header 2, no week | default 02-16. `Site A` history `[4,4]`, x 4: median 4 (not < 4), spread √4 = 2, z 0. Its 02-23 events and account 1's data must not appear | week 02-16, account total 4 = the one location, `normal`, z 0.0 |
| R6 | header 3 | | 200, `week null`, `account_summary.verdict no_activity`, `total/baseline/by_type null`, `locations []`, `parameters` present |
| R7 | header 4 | has events, no selectable week | 200, `week null`, `not_enough_history`, `locations []` |
| H1 | `/api/locations/Site%20A/history`, header 1 | W = 02-23 (the name has a space). Window = start 02-02 … 02-23 (3 prior weeks, fewer than 4, clipped at start) | `weeks` totals `[5,5,5,11]`, roles `[baseline ×3, selected]`, verdict `higher`, z 2.6833, band (0.5279, 9.4721), unknown 1 |
| H2 | `Main%20St`, header 1 | | totals `[6,4,6,6]`, `normal`, z 0.0 |
| H3 | `Late`, header 1, W = 02-23 | start 02-23 ≤ W | `weeks` = one row (02-23: 5, `selected`), `not_enough_history`, `baseline null`, band absent |
| H4 | `Late`, header 1, `week=2026-02-16` | starts after W | 404 `location_not_found` (message names the week) |
| H5 | `Nope`; and `Main%20St` with header 2 | never an event / other account's name | 404 `location_not_found` both |
| H6 | `site%20a`, header 1 | exact match (D-06) | 404 `location_not_found` |
| H7 | `Site%20A`, header 3, no week | account has no selectable week | 404 `location_not_found` |
| H8 | `Site%20A`, header 1, `week=2026-02-09` | before first selectable | 422 `invalid_week` (week is checked before location) |
| E1 | `week=2026-02-17` (Tuesday), header 1 | | 422 `invalid_week`, message contains `2026-02-16 .. 2026-02-23` |
| E2 | `week=2026-02-09` (Monday before the range); `week=2026-03-02` (after last) | | 422 `invalid_week` both |
| E3 | `week=abc`; `week=2026-13-01` | not a date | 422 `invalid_week` |
| E4 | `week=2026-02-16` for header 3 | no selectable week | 422 `invalid_week`, `no selectable weeks` |
| E5 | header `abc`; header `0`; header `999` | | 422 `invalid_request`; 422 `invalid_request`; 404 `account_not_found` |
| E6 | `GET /api/nope` | | 404 `not_found` |
| E7 | every non-2xx above | | body is exactly `{"error": {"code": ..., "message": ...}}` (no FastAPI `detail`) |

### 2c. `test_api_seed.py` (the real seed through the API)

Real params, real `get_bounds`, real `get_current_account`; only `get_conn` is overridden. Expected values are the T2 anchors (arithmetic in
T2 plan §2g) or computed here from the series I read with the queries in the Appendix; the statistics were redone by hand.

| # | Request | Arithmetic | Expected |
|---|---|---|---|
| S1 | `/api/accounts` | profile §1 | 20 rows; 6 = Metro Collision Centers, America/New_York; 20 = Quiet Harbor Spa, America/Los_Angeles |
| S2 | `/api/weeks`, header 1 | all accounts start 02-02 (profile §3, §6); first = 02-02 + 56 d = 03-30 | 17 weeks 03-30 … 07-20, default 2026-07-20 |
| S3 | `/api/weeks` for each of the 19 accounts with events | same | 17 weeks, default 07-20, for all (the six time zones, A5/L7 through the API) |
| S4 | `/api/weeks`, header 20 | no events | `[]`, `null` |
| S5 | `/api/report`, no header, no week | demo account **15**, week 07-20. Account: history `15,16,25,23,15,33,23,14,24,16,19,19`, x 20 → sorted 14,15,15,16,16,19,19,23,23,24,25,33, median 19; deviations 4,3,6,4,4,14,4,5,5,3,0,0 → sorted 0,0,3,3,4,4,4,4,5,5,6,14, MAD 4; spread max(5.9304, √19 = 4.359, 1) = 5.9304; z = 1/5.9304 = **0.1686** | account total 20, `normal`, median 19, mad 4, z 0.1686 |
| S6 | same, locations | **Site C** history `5,4,4,6,4,5,10,4,6,6,7,6`, x 12: sorted 4,4,4,4,5,5,6,6,6,6,7,10 → median 5.5; deviations .5,1.5,1.5,.5,1.5,.5,4.5,1.5,.5,.5,1.5,.5 → six .5, five 1.5, one 4.5 → MAD (.5+1.5)/2 = **1.0**; spread max(1.4826, √5.5 = 2.3452, 1) = 2.3452; z = 6.5/2.3452 = **2.7716**, diff 6.5; h = max(4.6904, 3) → band (0.8096, 10.1904). **Site B** `3,7,8,9,4,14,4,5,12,3,6,10`, x 2: median (6+7)/2 = 6.5, MAD 2.5, spread 3.7065, z = −4.5/3.7065 = −1.2141, d 4.5 ≥ 3 but z < 2. **Site A** `7,5,13,8,7,14,9,5,6,7,6,3`, x 6: median 7, MAD 1.5, spread 2.6458, z = −1/2.6458 = −0.3780 | order `[Site C, Site B, Site A]` (|z| 2.7716 > 1.2141 > 0.3780); Site C `higher`, total 12; Site B, Site A `normal` |
| S7 | header 6, `week=2026-06-01` (anchor A1) | account history `84,81,71,82,76,55,64,86,68,78,62,53`, x 880: median 73.5, MAD 9, spread 13.3434, z = 806.5/13.3434 = **60.44** | account `higher`, total 880, median 73.5, mad 9.0, z ≈ 60.44, weeks_used 12 |
| S8 | `/api/locations/Site%20A/history`, header 1, `week=2026-07-20` (anchor A2) | history 04-27 … 07-13: `8,7,6,6,5,7,9,11,7,10,7,9`, x = 9 is 07-20: median 7, MAD 1, spread 2.6458, z = 2/2.6458 = **0.7559**, d 2 < 3; band h = max(5.2915, 3) → (1.7085, 12.2915) | 13 rows, last role `selected`; `normal`, z 0.7559, median 7, band as shown; the same numbers in `/api/report` header 1 for Site A |
| S9 | `/api/locations/Site%20G/history`, header 6, `week=2026-07-20` (anchor A9) | history `6,4,3,7,5,57,4,5,3,0,4,6` incl. the zero week 06-29 → median 4.5, MAD 1.5, spread 2.2239, x 6, z = 1.5/2.2239 = 0.6745 | the row for 2026-06-29 has `total 0` (zero-filled); `normal`, z 0.6745 |
| S10 | `/api/report`, header 20 | A3 | 200, `week null`, `no_activity`, `locations []` |
| S11 | header 6, week 07-20: Site M; header 18: Site A | D-14 (medians 3.5 and 3, read from the seed in T2) | `too_quiet`, `z null`, `baseline.median` 3.5 and 3.0; listed after the judged locations, by name |
| S12 | ranking invariant, header 6 at 06-01 and 07-20, header 12 at 07-20 | independent of `rank()` | judged locations first with `|z|` non-increasing, unjudged after in name order; and the order equals `rank()` applied to `judge` outputs computed in the test |
| S13 | `data_quality.unknown_events_in_window` | A8: profile §5 has no unknown types | 0 at account and location level for all 19 accounts at their default week |

### 2d. `test_backtest.py` (PLAN §9; assertions fixed before the first run)

Calls `build_report` (the service the endpoints call), with the real params, for every account that has events and every selectable week of
that account (19 accounts × 17 weeks = 323 reports; 69 locations × 17 = 1,173 location-weeks before removing unjudged ones; calendar arithmetic). Nothing is tuned.

| # | Assertion | Basis |
|---|---|---|
| B1 | account 6, W = 2026-06-01: account verdict `higher`, total 880, z ≈ 60.44 | S7 / anchor A1 |
| B2 | account 6, W = 2026-06-01, locations: **every judged location (z not null) is `higher`**; the number flagged and the number unjudged are recorded | profile §11: all 15 locations had 42–69 events on 06-03 alone vs. location medians of 3 to 11 (D-14 table, at 07-20). A location that is `too_quiet` at that week cannot be judged by design; I do not claim 15 of 15 before running |
| B3 | **Flag-rate ceiling: over all judged location-weeks outside account 6's spike week 2026-06-01 (15 location-weeks removed), `flagged / judged ≤ 8.0 %`.** Recorded, not asserted: the actual rate, the higher/lower split, the unjudged count, and the account-level flag rate | D-14's idealized rate is 3.4 % at median 7 and 5.1 % at median 4.5 (Poisson floor, MAD ignored; a real MAD only widens the band). 8 % is 1.6× the worst idealized figure and about 2.3× the median-7 figure; at roughly 1,100 judged location-weeks that is about 88 flags against about 40 expected. Account 6's later weeks stay in (the spike sits in its baselines for 12 weeks; the median absorbs it, that is the point of D-02) |
| B4 | no account-level `not_enough_history` for any selectable week | the §1c range rule |
| B5 | no exception, no report with a location whose `history_weeks` exceeds `baseline_weeks` | consistency |

If B3 fails, we stop and discuss; we do not move `z_min`, `min_abs` or the ceiling to make it pass. The actual numbers go into D-23.

## 3. Make targets / commands

No new targets, no compose change (`DEMO_ACCOUNT_ID` is optional and has a code default). `.env.example` gains a commented `DEMO_ACCOUNT_ID=15`.
After T3 `make check` still runs: `ruff check .` + `ruff format --check .` (lint), `mypy` strict over `app` + `tests` (typecheck), `pytest -q` (test),
all in the api container. `make up` serves the endpoints on http://127.0.0.1:8000 (smoke check by `curl`).

Implementation order, each red before green: `test_report_unit` → `weeks_range`/`resolve_week` → `errors` + `deps` → `report` + `schemas` →
`api` (W, R, H, E) → seed tests (S) → backtest (B) → decisions D-20 to D-23 → reviewer change and run (§6).

## 4. Decision-log entries (same change)

- **D-20:** one service module (`report.py`), thin endpoints, backtest and API share `build_report`; as-of, bounds and params are injectable dependencies.
  The error shape `{"error": {"code", "message"}}` and its code table are recorded here too (no real alternatives); `no_activity` is a 200 empty state.
  Alternatives: logic in route functions; a backtest that calls the domain directly.
- **D-21:** selectable weeks are per account and judgeable only (`start + min_history_weeks … last complete week`); outside = 422; a location absent at W = 404.
  Alternatives: all complete weeks with `not_enough_history`; a global range; 200 `no_activity` for an absent location (changes the verdict's meaning, leaks future data).
- **D-22:** account resolution: `X-Account-Id` with a demo default account 15, 404/422 rules, `GET /api/accounts` as the one unscoped endpoint.
  It must say plainly that 15 was picked because it is the only account with a flagged location at 2026-07-20 (Site C `higher`), a demo choice
  that is configurable (`DEMO_ACCOUNT_ID`), not a property of the data.
  Alternatives: account in the path; no default; a different default account.
- **D-23 (written after the backtest run):** backtest assertions B1–B5 as fixed here, the actual flag rate and the unjudged counts, "not tuned".

## 5. Done when

- [ ] Every row of §2 exists as a test and passes; `make check` is green (ruff, ruff format, mypy strict, pytest). Record the pass count.
- [ ] Every endpoint's default week, explicit week, bad week, unknown account, unknown location, a location name with a space, and account 20 are covered (§2b, §2c).
- [ ] Seed anchors through the API (S7 = A1, S8 = A2, S9 = A9; S5/S6 for the default account) match the T2 numbers.
- [ ] Ranking order in `/api/report` matches `rank()` and the independent invariant (R2, R3, S6, S12).
- [ ] Backtest B1–B5 pass; the actual flag rate, split and unjudged counts are in D-23. No parameter changed.
- [ ] One error shape for every non-2xx (E7).
- [ ] `git diff --exit-code main -- data/ PLAN.md backend/migrations/ backend/app/domain/` is empty; `git diff main -- backend/app/series.py` shows only the added function.
- [ ] `grep -rnE "now\(\)|datetime\.now|utcnow" backend/app` finds nothing outside tests.
- [ ] D-20 … D-23 in `docs/decisions.md`.
- [ ] **aggregation-reviewer** (§6) run against the endpoint output and the new code; its report compared with the tests by John and pasted into the ai-log.
- [ ] Nothing committed without your say-so.

## 6. Reviewer change (task in this ticket, not a silent edit)

`aggregation-reviewer.md` has no hardcoded date. The leak is that it must read PLAN §2, which states "the default view is the last complete week (2026-07-20)"
and the as-of "2026-07-27", so its part 3 ("each account's last complete week, according to PLAN section 2") is not blind. Proposed edit to
`.claude/agents/aggregation-reviewer.md`, made in this ticket and shown to you before it is used:

1. Part 3: derive the as-of from `max(occurred_at)` in `clean_events` and the data start from `min(occurred_at)`, then each account's last
   (and first) complete week in the account's timezone with its own SQL; it is told to **ignore any calendar date written in PLAN** and to
   report if a date in PLAN disagrees with what it derived.
2. Add the new files to what it may read: `backend/app/report.py`, `backend/app/schemas.py`, `backend/app/api.py`; it still must not read `tests/`, `plans/`,
   `docs/decisions.md`, `ai-log/`.
3. Add a read-only HTTP step **after** it has written its own recompute: it calls `GET /api/report` and `GET /api/locations/{location}/history` for the same
   cases and compares totals, median, MAD, z, verdict, order and the last complete week (`/api/weeks`) with its numbers. Tool added to its list:
   `Bash(curl -s:*)` restricted to `http://127.0.0.1:8000/api/` (exact permission string checked when I make the edit). It reads
   the new code for mapping deviations from PLAN §2/§6 (rounding, ordering, a verdict passed through wrongly).
4. The report gets a section "Endpoint vs recompute".

Alternative: leave the reviewer as is and say the date is an accepted limit. Not recommended: the as-of is the one input everything else depends on.

## 7. Open questions (decision needed)

| # | Issue | Recommendation | Trade-off |
|---|---|---|---|
| Q1 | **Default account.** I scored all 20 accounts at 2026-07-20 with the T2 code on the dev DB (read-only): only account 15 (Sierra Pest Solutions, Phoenix, 3 locations) has a flagged location in an otherwise normal account (Site C `higher`, z 2.7716, 12 vs median 5.5); account 6 (15 locations) shows only `too_quiet` Site M; the rest are all `normal`. Query for the Site C series: `SELECT w::date, count(e.id) FROM generate_series('2026-04-27'::date,'2026-07-20','7 days') w LEFT JOIN clean_events e ON e.account_id = 15 AND e.location = 'Site C' AND e.local_week = w::date GROUP BY 1 ORDER BY 1;` then `judge` | Default **15**: the first screen answers "which location should I look at?" with one clear answer. Account 6 stays one switcher click away for the spike (`week=2026-06-01`) | The demo opens on a mild flag, not the 60x spike; the default is a data choice, so it is a setting (`DEMO_ACCOUNT_ID`), not a hard-coded id |
| Q2 | **PLAN §6 gaps** (not edited here): `GET /api/accounts` is missing; `locations[].score` is undefined; `account_summary` has no `z`/`diff`/`history_weeks`; empty-state shapes (`week null`) are not described; the backtest says "25 seed weeks" but only 17 are selectable (8 weeks of history) | API returns `z` and `diff`, the order is the ranking; `week null` for the two account empty states; backtest runs over the 17 selectable weeks | The later docs ticket should update PLAN §6/§9; until then this plan and D-21/D-22 are the source |
| Q3 | **`/api/accounts` is unscoped** and lists every account name to any caller. | Accept for the demo switcher (PLAN §1 calls it a stand-in for login); record in D-22 | Real auth would replace it; out of scope |
| Q4 | **Account with events but no judgeable week** (starts after `last − 8 weeks`): 200 with `week null` and `not_enough_history` at account level, no location list. | Yes (§1c) | The locations of such an account are not shown at all; none in the seed |
| Q5 | **`unknown_events_in_window` is the sum over the window** (baseline weeks + selected week), not only the selected week. | Window: an unknown type in a baseline week also undercounts the baseline | A bigger number than "this week"; the seed has none (S13) |
| Q6 | **Floats are unrounded** and `as_of` is a UTC string with `Z`. | As decided; T4 formats | JSON has long floats such as `2.6833...`; tests compare with `approx` |
| Q7 | **Location path** is `{location}` (no `/` in names). | Keep; the data has none | A real location name with `/` would 404; `{location:path}` fixes it if it appears |
| Q8 | **Backtest ceiling 8 %** and B2's wording (every judged location flags; the number is recorded) are mine, fixed before any run. | Accept as written, or change them now | Too tight a ceiling fails for the wrong reason; too loose proves nothing. If it fails we discuss, we do not tune |
| Q9 | **Reviewer change** (§6) including `curl` against the local API. | Approve; the exact permission string is checked when it is made | The reviewer still is "instructed, not enforced" to avoid `tests/` (D-19); the HTTP tool is read-only GET |
| Q10 | **One connection for the whole request** with no `readonly` option and no explicit transaction. | Keep simple (CLAUDE.md: keep it simple); the endpoints only run SELECTs | Nothing at the DB level stops a future write from an endpoint; a `postgresql_readonly` execution option is cheap to add later |

## Appendix: queries behind the anchors (read-only, `make psql`)

```sql
-- S5: account 15 totals, 2026-04-27 .. 2026-07-20 (last value is x)
SELECT w::date, count(e.id) FROM generate_series('2026-04-27'::date,'2026-07-20','7 days') w
LEFT JOIN clean_events e ON e.account_id = 15 AND e.local_week = w::date GROUP BY 1 ORDER BY 1;
-- S6: one location of account 15 (Site A / B / C)
SELECT w::date, count(e.id) FROM generate_series('2026-04-27'::date,'2026-07-20','7 days') w
LEFT JOIN clean_events e ON e.account_id = 15 AND e.location = 'Site C' AND e.local_week = w::date GROUP BY 1 ORDER BY 1;
-- weeks range (S2): first judgeable week = first complete week + 8 weeks
SELECT date '2026-02-02' + 8 * 7;   -- 2026-03-30
```

## Deviations

- **S15, S16 added** from the aggregation-reviewer's independent cases (reviewer-sourced, like T2's A9 and A10): account 6 Site N at
  2026-04-27 (zero week in the baseline, `|diff|` exactly `min_abs`, `normal`) and account 6 Site G at 2026-06-01 (`higher`, `band_low` −1.4304,
  not clipped at 0). S14 stays dropped. The code agreed with every value.
- **H8b added** after mutation (d) survived: H8 uses a location that exists at the week it asks for, so it cannot tell whether the week or the
  location is checked first. H8b (`Late` at 2026-02-09: absent and not selectable, must be 422) fails under that mutation.
- **`series.py` gets three additions**, not one: `fetch_account_start` (plan §1c), `fetch_accounts` and the `AccountRow` dataclass (review fix:
  `api.py` stays parse and call only; `report.build_accounts` maps the rows). Nothing existing in `series.py` changed.
- **Reviewer change (§6) as built:** the permission is `Bash(curl -s http://127.0.0.1:8000/api/:*)`, and the examples pass the week with
  `-G -d week=...` and an unquoted URL so they match the prefix. This run **could not read `backend/app/series.py`** (it was not on the reviewer's
  list); the zero-fill and location-start logic were checked through the API outputs only. `series.py` is now on its allowed reads.
- **Backtest prints `PARAMS`** (the five values used), added before the one run, because `ReportSettings` reads `REPORT_*` from the
  environment; the assertions did not change.
- **`docker-compose.yml` (plan §3 said no compose change), fixed in T3 (compose pass-through, verified):** `DEMO_ACCOUNT_ID` was documented
  in `.env.example` but never reached the api container, the same bug class as T2's `REPORT_*`. It is now a pass-through line in the `x-api`
  environment with no default, so the default (15) lives only in `Settings.demo_account_id`. Verified end to end (api container recreated each time,
  `GET /api/weeks` with no header): no variable → unset in the container, account 15; `DEMO_ACCOUNT_ID=6` in `.env` → account 6; `.env=6` plus a shell
  `DEMO_ACCOUNT_ID=12` → account 12 (the shell wins); the shell variable alone → account 12; then `.env` removed (it did not exist before; it is
  gitignored) and the api recreated with nothing set → account 15 again.
