# T4: Frontend

Status: **APPROVED**, with these review changes applied: (1) CP1 split into CP1a (run path only) and CP1b (client, URL logic, shell); (2) R11's expected row count is calendar arithmetic, not read from the fixture; (3) Done-when (g) became a CP1a step that records the real status and body of the empty-DB probe; (4) D-27 states the request waterfall; (5) Q4 to Q9 accepted as recommended (Q5 left to T6, Q6 copy as proposed, Q9 yes).
Source: PLAN.md §1, §4, §5, §6, §8 (ticket 4), §9, §10; decisions D-13, D-17, D-20 to D-22; plans/T3-backend-api.md (§1b, §1d, §7); T1 plan §9 Q10 (frontend checks join `make check` here). Data facts: docs/data-profile.md (via the T3 anchors).
Branch: `feat/T4-frontend` (created, checked out). No commits until asked.
Pre-plan decisions (John): header-less bootstrap, unknown account = error state, global `fetch` stub, no ESLint, no auto-select of a location, CLAUDE.md edit limited to the Stack line and the Commands section, decision log limited to D-26 and D-27.

**In:** the single screen (PLAN §5): account switcher (labeled as a demo stand-in for login), week selector, account summary, location table in API order with unjudged rows and their reason, location detail (about 12 weeks plus the selected week against one band), URL state, the states loading / error / `no_activity` / `not_enough_history` / data-quality warning; a `web` service in docker-compose; Vitest + React Testing Library + `tsc --noEmit` inside `make check`.
**Out:** AI summary, per-type verdicts, styling work, ESLint, a production build or static serving, auth, **any change to `backend/`**, `data/`, `PLAN.md`. The only non-frontend files touched: `docker-compose.yml`, `Makefile`, `CLAUDE.md` (Stack line + Commands only), `docs/decisions.md` (D-26, D-27), this plan.
No backend change is needed: the Vite proxy removes CORS, and the demo account is learned from `/api/weeks` (D-22), so nothing new is exposed.

## 1. Design

```
frontend/
  Dockerfile              node:22-alpine, `npm ci` in the image, CMD npm run dev
  .dockerignore           node_modules, dist
  package.json            scripts: dev, typecheck (tsc --noEmit), test (vitest run)
  package-lock.json       generated in a container (§3)
  tsconfig.json           strict, noUncheckedIndexedAccess, noEmit; includes src + vite.config.ts
  vite.config.ts          server {host 0.0.0.0, port 5173, strictPort, proxy /api -> process.env.API_URL}; test {jsdom, setup}
  index.html
  src/main.tsx  App.tsx
  src/api/types.ts        hand-mirrored from backend/app/schemas.py (Q1)
  src/api/client.ts       typed fetch client + ApiError
  src/urlState.ts         pure: parseUrl, buildUrl, next* transitions
  src/reconcile.ts        pure: reconcileAccount, reconcileWeek, reconcileLocation
  src/format.ts           pure: fmtNum, fmtZ, fmtDiff, displayBand, fmtBand, fmtAsOf, copy helpers
  src/chart.ts            pure: chartGeometry            (CP3b, first to be cut)
  src/hooks/useAsync.ts   one small hook: key + abortable fetch -> {status, data, error}
  src/hooks/useUrlState.ts   URLSearchParams <-> history, popstate
  src/components/         AccountSwitcher, WeekSelector, AccountSummary, LocationTable, LocationDetail,
                          WeeksTable, WeekChart (CP3b), ErrorBox, Notice, DataQualityWarning
  src/test/               setup.ts, mockFetch.ts, fixtures/*.json + README.md (§2, capture commands)
```

No router, no state library, no data-fetching library, no CSS framework. Function over form: semantic HTML, a few inline layout rules.

### 1a. Run path (D-26)

`docker-compose.yml` gets a `web` service: `build: ./frontend`, env `API_URL: http://api:8000`, `ports: 127.0.0.1:5173:5173`, `volumes: ./frontend:/app` plus the anonymous `/app/node_modules`, `depends_on: api (service_healthy)`, and a healthcheck (`wget -qO- http://127.0.0.1:5173/ >/dev/null`; **cut item 2**). `make up` becomes `docker compose up -d --build --wait -V`.

The node_modules trap and its handling: `npm ci` runs in the image, the bind mount would hide `/app/node_modules`, so an anonymous volume keeps the image's copy. Compose reuses anonymous volumes across recreates, so after a `package.json` change the old modules would shadow the new image; `-V` (`--renew-anon-volumes`) discards them on every `make up`. `-V` touches no named volume (`pgdata` stays); verified in Done-when. No packages are ever installed on the host. Docker does create an **empty** `frontend/node_modules` directory on the host as the mount point of the anonymous volume whenever `web` runs (git-ignored, and not removable while the container exists); it holds nothing. The lockfile is generated in a throwaway copy of `package.json` and `package-lock.json`, never on the bind mount (see CP1a evidence).
The proxy forwards `X-Account-Id` unchanged. The browser sees one origin, so the backend gets no CORS middleware. The Vite dev server is a dev tool, not a production serving story (README, T6).

### 1b. Client (`api/client.ts`)

```
class ApiError extends Error { status: number; code: string }     // body {error:{code,message}} -> its code/message
getAccounts(signal)                                  GET /api/accounts                      never sends the header
getWeeks(account: string | null, signal)             GET /api/weeks                         header only if account != null
getReport(account: string, week: string | null, signal)    GET /api/report[?week=]          always the header
getHistory(account: string, location: string, week: string, signal)
                                                     GET /api/locations/{encodeURIComponent(location)}/history?week=
```
Errors: non-2xx with the T3 shape -> `ApiError(code, message)`; a non-2xx without it (the proxy's 502 when the api is down) -> `ApiError("unexpected_response", "Unexpected response (HTTP 502)")`; a rejected fetch -> `ApiError("network_error", ...)`; `AbortError` is rethrown untouched. Types: dates and `as_of` are `string`, `Verdict` is the union of the six values, floats `number`.

### 1c. URL state and reconciliation (D-27)

State `{account, week, location}`, each `string | null`; `""` counts as absent. The account never goes into a request except as the header (D-22).

`urlState.ts` (pure): `parseUrl(search)`, `buildUrl(state)` (`URLSearchParams`; order account, week, location; nulls omitted; unknown params are dropped on rebuild; a space becomes `+`), and the user transitions: `nextOnAccount(state, id)` -> `{account: id, week: null, location: null}`; `nextOnWeek(state, week)` keeps account and location; `nextOnLocation(state, loc)`.

`reconcile.ts` (pure, three stages, because each needs data that arrives after the previous one; this is the `reconcile` of the pre-plan, split):

| Stage | Input | One behavior per case |
|---|---|---|
| `reconcileAccount(urlAccount, accounts)` | param, `/api/accounts` | `null` -> `{kind: "default"}` (header-less bootstrap). A param equal to `String(id)` of a listed account -> `{kind: "ok", id}`. Anything else (unknown, `abc`, `0`, `-1`, `015`, empty list) -> `{kind: "error", code: "unknown_account", message}`; no account-scoped request is sent, the URL is untouched, the switcher stays usable. No fallback to the demo account. |
| `reconcileWeek(urlWeek, weeksOut)` | param, `/api/weeks` | in `weeks` -> same, no correction. `null` -> `default_week`, corrected (adopt, no notice). Not in `weeks` (malformed, a non-Monday, outside the range) -> `default_week`, corrected, **with a notice** naming both weeks. `weeks == []` (account 20, or no judgeable week) -> `null`; a stale param is removed, no notice (the empty state explains). A 422 `invalid_week` therefore never comes from a URL. |
| `reconcileLocation(urlLocation, report)` | param, `/api/report` | exact match (no case folding, D-06) in `report.locations` -> same. Otherwise `null`, corrected, no notice; no history request. Also applies when a week change removes the location (it starts later) and when `report.locations` is empty. |

Corrections use `replaceState`; user changes use `pushState`; `popstate` re-runs the same path. **Bootstrap:** no `account` -> `getWeeks(null)` (no header), adopt `weeks.account.id` by `replaceState`, no second `/api/weeks`. **Account change:** `pushState ?account=B` only; weeks load, then `replaceState` adds B's default week. Back returns to account A with its week and location. Week change keeps the location if the new report has it. A location click is a `pushState`; no location is auto-selected, the detail shows a hint.

Flow (each step an effect keyed on its inputs, through `useAsync`): `/api/accounts` once; then `/api/weeks`; then `/api/report` per (account, reconciled week); then `/api/locations/…/history` per (account, week, location). The first two depend on the URL: **with an `account` param**, `/api/weeks` starts only after `/api/accounts` has returned and only if `reconcileAccount` returned `ok` (so `?account=999` never produces a request carrying `X-Account-Id: 999`); **with no `account` param**, `/api/accounts` and the header-less `/api/weeks` run in parallel (there is no id to validate). `useAsync` aborts the previous request on a key change and ignores late results, so a slow response for account A cannot overwrite account B.

### 1d. Rendering rules (no statistics in the UI)

- The UI renders the API's `verdict`, `z`, `diff`, `baseline`, `by_type`, order and parameters as given. It never sorts, never regroups (no divider where unjudged rows start) and never computes a verdict, median or band. Layout arithmetic (chart scale) is the only computing.
- Formats (`en-US`, fixed so tests are deterministic): `fmtNum` up to 1 decimal (`5.5`, `19`, `880`); `fmtZ` 2 decimals with U+2212 for negatives and no negative zero (`−0.004` -> `0.00`); `fmtDiff` signed, 1 decimal (`+6.5`, `−4.5`, `0`); `null` -> `—`. Floats are formatted only here, at render time.
- `displayBand(baseline)` clips `band_low` at 0 and is the one function used by both the text and the chart; the data is never changed. The chart's band is the selected week's band (D-17) drawn across all weeks, and is labeled so (baseline points outside it are not flags).
- Copy comes from the API: "compared with the last N weeks" uses `baseline.weeks_used`; the `too_quiet` reason uses `baseline.median` and `parameters.min_baseline_median`; the `not_enough_history` reason uses `history_weeks` and `parameters.min_history_weeks`. Nothing hard-codes 12, 8 or 4. Wording is direction-neutral ("higher / lower than usual").
- Dates stay strings (`new Date("2026-07-20")` is UTC and shifts a day in US zones): week shown as `Week of 2026-07-20`, `as_of` as `2026-07-27 22:20 UTC` via a regex. No `new Date`, no `Date.now` anywhere in `src` (checked in Done-when).
- Each of the six verdicts has text. Account level: `no_activity` (week `null`, 200) is its own empty state; `not_enough_history` with `week null` (events but no judgeable week; none in the seed) gets its own message, not the `no_activity` one.
- `data_quality.unknown_events_in_window > 0` shows a warning at account level and in the detail, worded "in the baseline window plus this week", not "this week".
- Errors: `ErrorBox` renders `{code, message}` from `ApiError`, for any of the four requests.

### 1e. Deliberately not done

ESLint (Q3), a production build in `make check`, snapshot tests, per-type verdicts, styling, a location auto-select, re-ranking or grouping, caching of responses, rounding on the server, any backend change.

## 2. Tests, written first

Vitest (`vitest run`, never watch), jsdom, React Testing Library, `@testing-library/jest-dom`. No database, no network, no real API. Isolation: every test starts with `history.replaceState(null, "", "/")`; `fetch` is replaced by `vi.stubGlobal` with a small router (`mockFetch.ts`: path + `X-Account-Id` -> a fixture, call log recorded) and `vi.unstubAllGlobals()` after each; fixtures are read-only JSON, tests that change one use `structuredClone`. No test shares state with another. `tsc --noEmit` also covers `src/test`.

**Fixtures (real output).** Captured from the seeded dev API (`make up && make seed`) into `frontend/src/test/fixtures/`, with these exact commands (also in `fixtures/README.md`, for regeneration when the API changes):

```bash
B=http://127.0.0.1:8000/api; F=frontend/src/test/fixtures
curl -s $B/accounts                                                              > $F/accounts.json
curl -s -H 'X-Account-Id: 15' $B/weeks                                           > $F/a15-weeks.json
curl -s -H 'X-Account-Id: 15' "$B/report?week=2026-07-20"                        > $F/a15-report-0720.json
curl -s -H 'X-Account-Id: 15' "$B/locations/Site%20C/history?week=2026-07-20"    > $F/a15-history-siteC-0720.json
curl -s -H 'X-Account-Id: 6'  $B/weeks                                           > $F/a6-weeks.json
curl -s -H 'X-Account-Id: 6'  "$B/report?week=2026-06-01"                        > $F/a6-report-0601.json
curl -s -H 'X-Account-Id: 6'  "$B/report?week=2026-07-20"                        > $F/a6-report-0720.json
curl -s -H 'X-Account-Id: 6'  "$B/locations/Site%20G/history?week=2026-06-01"    > $F/a6-history-siteG-0601.json
curl -s -H 'X-Account-Id: 20' $B/weeks                                           > $F/a20-weeks.json
curl -s -H 'X-Account-Id: 20' $B/report                                          > $F/a20-report.json
curl -s -H 'X-Account-Id: 999' $B/weeks                                          > $F/err-account-not-found.json
curl -s -H 'X-Account-Id: 15' "$B/report?week=2026-01-05"                        > $F/err-invalid-week.json
```

The expected values are the T3 anchors (T3 plan §2c S5, S6, S7, S11, S15, S16), redone below. Cases with no seed example (account-level `not_enough_history`, a location `not_enough_history`, `unknown_events_in_window > 0`, a location absent at another week, changed `parameters`) are **mutated copies** of a real fixture made inside the test (`structuredClone` + one field), never stored.

### 2a. `urlState.test.ts` (pure)

| # | Input | Expected |
|---|---|---|
| P1 | `parseUrl("?account=15&week=2026-07-20&location=Site%20C")` | `{15, 2026-07-20, "Site C"}` |
| P2 | `parseUrl("")`; `parseUrl("?account=&week=")` | all `null`; `account` and `week` `null`, `location` `null` |
| P3 | `parseUrl("?location=Site+C")` | `location "Site C"` (`+` is a space) |
| P4 | `buildUrl({15, 2026-07-20, "Site C"})` | `?account=15&week=2026-07-20&location=Site+C` |
| P5 | `buildUrl({account "15", null, null})`; all `null` | `?account=15`; `""` |
| P6 | location `A+B`: build -> parse. Also `A&B=1` | `+` is 0x2B -> `location=A%2BB` -> parses back to `A+B`; `&` 0x26, `=` 0x3D -> `A%26B%3D1` -> back to `A&B=1` |
| P7 | `parseUrl("?account=15&utm=x")` then `buildUrl` | `utm` is not kept: `?account=15` |
| P8 | `nextOnAccount({15, W, "Site C"}, "6")`; `nextOnWeek(same, W2)`; `nextOnLocation(same, "Site A")` | `{6, null, null}`; `{15, W2, "Site C"}`; `{15, W, "Site A"}` |

### 2b. `reconcile.test.ts` (pure; weeks `[2026-03-30, 2026-04-06, 2026-04-13]`, default `2026-04-13`; accounts ids 1, 2, 15)

| # | Call | Expected |
|---|---|---|
| RA1 | account `null` | `{kind: "default"}` |
| RA2 | `"15"` | `{ok, id 15}` |
| RA3 | `"999"`; `"abc"`; `"0"`; `"-1"`; `"015"` | each `{error, unknown_account}`: none equals `String(id)` of 1, 2, 15 |
| RA4 | `"15"` with `accounts = []` (DB not seeded) | `{error, unknown_account}` |
| RW1 | `"2026-04-06"` | same week, `corrected false`, no notice |
| RW2 | `null` | `2026-04-13`, `corrected true`, no notice |
| RW3 | `"2026-01-05"` (Monday before the range) | `2026-04-13`, `corrected true`, notice contains `2026-01-05` and `2026-04-13` |
| RW4 | `"abc"`; `"2026-04-07"` (a Tuesday) | same as RW3 |
| RW5 | `null`, `weeks = []` | `null`, `corrected false`, no notice |
| RW6 | `"2026-04-06"`, `weeks = []` | `null`, `corrected true`, no notice |
| RL1 | `null` | `null`, `corrected false` |
| RL2 | `"Site C"` in the report | `"Site C"`, `corrected false` |
| RL3 | `"site c"` | `null`, `corrected true` (exact match, D-06) |
| RL4 | `"Nope"`; any location with `report.locations = []` | `null`, `corrected true` |

### 2c. `format.test.ts` and `chart.test.ts` (pure)

Arithmetic from the T3 anchors (spread = max(1.4826·MAD, √median, 1); half-width h = max(z_min·spread, min_abs)).

| # | Call | Arithmetic | Expected |
|---|---|---|---|
| F1 | `fmtZ(2.7716)`, `(0.1686)`, `(-1.2141)`, `(60.4427)` | rounded to 2 decimals | `2.77`, `0.17`, `−1.21` (U+2212), `60.44` |
| F2 | `fmtZ(-0.004)`; `fmtZ(null)` | rounds to −0.00, shown without the sign | `0.00`; `—` |
| F3 | `fmtNum(5.5)`, `(19)`, `(73.5)`, `(10.1904)`, `(0.8096)`, `(880)` | 1 decimal at most | `5.5`, `19`, `73.5`, `10.2`, `0.8`, `880` |
| F4 | `fmtDiff(6.5)`, `(-4.5)`, `(0)` | | `+6.5`, `−4.5`, `0` |
| F5 | `displayBand({band_low: -1.4304, band_high: 10.5})` and `fmtBand` of it | low clipped to 0 | `{low 0, high 10.5}`, `0 to 10.5` |
| F6 | `fmtBand` of `{0.8096, 10.1904}` (account 15 Site C) | | `0.8 to 10.2` |
| F7 | `fmtAsOf("2026-07-27T22:20:34Z")`; `null` | regex date + HH:MM | `2026-07-27 22:20 UTC`; `—` |
| F8 | `baselineSentence(weeks_used 12)`, `(9)`, `(1)` | the number comes from the argument | `compared with the last 12 weeks`, `…9 weeks`, `…1 week` |
| F9 | `reasonText(too_quiet, median 3.5, min_baseline_median 4)`; `(not_enough_history, history_weeks 5, min_history_weeks 8)` | | text containing `3.5` and `4`; containing `5` and `8` |
| C1 | `chartGeometry`: width 300, height 100, padding 10 on every side (inner 280 × 80); totals `[2,4,6]`, band `{-1, 5}` | yMax = max(6, 5) = 6; x = 10 + i·280/2 = 10, 150, 290; y = 10 + 80·(1 − v/6): 2 → 63.333, 4 → 36.667, 6 → 10. Band low clipped to 0 → y 90; high 5 → y 23.333; rect y 23.333, height 90 − 23.333 = 66.667 | as computed (`toBeCloseTo`) |
| C2 | same totals, band `{1, 5}` | low 1 → y = 10 + 80·5/6 = 76.667; height 76.667 − 23.333 = 53.333 | rect y 23.333, height 53.333 |
| C3 | totals `[1,2]`, band `{2, 8}` | yMax = 8 (band above the data); y(1) = 10 + 80·7/8 = 80; y(2) = 70; band y(8) = 10 → y(2) = 70, height 60 | ys `[80, 70]`, rect y 10, height 60 |
| C4 | one point, total 3, no band | n = 1 → x = 10 + 280/2 = 150; yMax 3 → y 10 | xs `[150]`, ys `[10]`, no rect |
| C5 | totals `[0,0]`, no band | yMax = max(0, 1) = 1 (no division by 0); y = 10 + 80 = 90 | ys `[90, 90]` |
| C6 | no points | | empty arrays, no rect |

### 2d. `client.test.ts` (global `fetch` stubbed)

| # | Case | Expected |
|---|---|---|
| K1 | `getAccounts()` | request `/api/accounts` with **no** `X-Account-Id` |
| K2 | `getWeeks(null)`; `getWeeks("15")` | no header; header `X-Account-Id: 15` |
| K3 | `getReport("15", null)`; `getReport("15", "2026-07-20")` | `/api/report`; `/api/report?week=2026-07-20`; header on both |
| K4 | `getHistory("15", "Site C", "2026-07-20")` | path `/api/locations/Site%20C/history?week=2026-07-20` |
| K5 | `getHistory` with location `A/B` | `A%2FB` in the path |
| K6 | 404 body from `err-account-not-found.json`; 422 from `err-invalid-week.json` | `ApiError` with that `code` and `message` |
| K7 | a 502 with an HTML body | `ApiError` code `unexpected_response` |
| K8 | `fetch` rejects with `TypeError`; with `AbortError` | `network_error`; the `AbortError` itself |

### 2e. `App.test.tsx` (React Testing Library, fixtures)

| # | Scenario | Expected |
|---|---|---|
| A1 | **Reload restores state.** URL `?account=15&week=2026-07-20&location=Site+C` | exactly four requests: `/api/accounts` (no header), `/api/weeks`, `/api/report?week=2026-07-20`, `/api/locations/Site%20C/history?week=2026-07-20` (the last three with header 15); asserted order: `/api/accounts` **before** `/api/weeks` (the URL has an account, so weeks waits for `reconcileAccount`), then report after weeks, then history after report; URL unchanged; the screen shows account 15, week 2026-07-20, and the detail heading `Site C` |
| A2 | **Header-less bootstrap.** URL `/` | `/api/accounts` and `/api/weeks` (no header) both requested, in either order (no account to validate, so they run in parallel); exactly one `/api/weeks`; then the URL is `replaceState`d to `?account=15&week=2026-07-20` (`history.length` unchanged); `/api/report?week=2026-07-20` with header 15; every request after the first weeks call carries the header |
| A3 | **Unknown account.** `?account=999`; `?account=abc` | error state "unknown account", the switcher is present; only `/api/accounts` was requested; URL unchanged |
| A4 | **Stale week.** `?account=15&week=2026-01-05`; `?week=abc`; `?week=2026-07-21` (a Tuesday) | notice naming both weeks; URL replaced with `week=2026-07-20`; `/api/report?week=2026-07-20` requested; **no** request ever carries the stale week |
| A5 | **Location not in the report.** `?account=15&week=2026-07-20&location=Nope` | URL replaced without `location`; detail shows the hint; no history request |
| A6 | **Account 20.** `?account=20` | report requested without `week`; URL has no `week`; `no_activity` empty state; the week selector is disabled |
| A7 | **Account switch.** From A1's state choose account 6 | `pushState` `?account=6` (history length +1); `/api/weeks` with header 6, then report with 6's default week; location cleared; then `history.back()` restores account 15, week and location (if jsdom's traversal is flaky, dispatch `popstate` by hand) |
| A8 | **Week change.** From account 6 week 2026-07-20 choose 2026-06-01 | `pushState` keeps `location` if present in `a6-report-0601`; with a copy of the report whose locations lack it, the location is dropped by `replaceState` |
| A9 | **Late response ignored.** Account 15's weeks response held back, account 6 chosen, 15's response released | the screen shows account 6; 15's data never appears |
| A10 | **Loading and error.** Report pending; then report fails with `err-invalid-week.json`; then the network fails | a loading text first; then `ErrorBox` with code and message; then a `network_error` message |

### 2f. `render.test.tsx` (components with fixtures)

Expected displayed strings, redone by hand from T3 §2c.

| # | Fixture | Arithmetic | Expected on screen |
|---|---|---|---|
| R1 | `a15-report-0720`, account summary | total 20; median 19; MAD 4; spread max(5.9304, 4.359, 1) = 5.9304; z = 1/5.9304 = 0.1686; h = max(11.8608, 3) → band 7.1392 … 30.8608 | `20`, normal `19`, range `7.1 to 30.9`, `0.17`, verdict normal |
| R2 | `a15-report-0720`, locations | Site C: total 12, median 5.5, spread √5.5 = 2.3452 (> 1.4826·1), z = 6.5/2.3452 = 2.7716, diff 6.5, h = 4.6904 → 0.8096 … 10.1904 | first row is Site C with higher-than-usual, `12`, `5.5`, `0.8 to 10.2`, `2.77`, `+6.5` |
| R3 | `a6-report-0601`, account summary | median 73.5, MAD 9, spread 13.3434, z = 806.5/13.3434 = 60.44; h = 26.6868 → 46.8132 … 100.1868 | `880`, `73.5`, `46.8 to 100.2`, `60.44`, higher |
| R4 | **Order as given.** `a15-report-0720` with its locations reordered to `[Site B, an unjudged row, Site C, Site A]` | no sort by `|z|` (B before C), by name (B, U, C, A) or by unjudged-last yields it | DOM rows in exactly that order |
| R5 | `a6-report-0720`, unjudged rows | Site M median 3.5 < 4 (`too_quiet`, T3 S11) | the row shows the reason with `3.5` and `4` (from `baseline.median` and `parameters.min_baseline_median`); `z` shows `—` |
| R6 | R5 with `parameters.min_baseline_median` set to 5 and a `weeks_used` of 9 in a clone | the text follows the data | the phrases `below 5` and `last 9 weeks` appear; `below 4` and `last 12 weeks` do not (whole phrases, not bare digits) |
| R7 | clone of a location with `not_enough_history`, `history_weeks 5`, `min_history_weeks 8` | | reason with `5` and `8`; no band |
| R8 | the four verdicts `normal`, `higher`, `lower`, `too_quiet` on a location row (clones) and `no_activity`, `not_enough_history` on the account summary (`a20-report`; a clone with `week null` and `not_enough_history`) | | one distinct text each; `no_activity` and account-level `not_enough_history` differ |
| R9 | `a15-report-0720` clone with `unknown_events_in_window = 3` at account and at location | | warning with `3` and "baseline window"; with `0` (the original) no warning |
| R10 | `a6-history-siteG-0601` | `band_low` is −1.4304 (T3 S16) | band text starts `0 to `; the text `−1.4` appears nowhere |
| R11 | `a15-history-siteC-0720` | Expected count by calendar arithmetic, not from the fixture: the first complete week is 2026-02-02 (T2 F1); 2026-07-20 − 12 weeks = 84 days = **2026-04-27**, which is on or after 2026-02-02, so the window is full (Site C has 12 prior values, T3 S6): 12 baseline weeks (04-27 … 07-13) + the selected 07-20 = **13** rows; last role `selected` | a weeks table with that many rows, the last marked selected; the chart note says the band is the selected week's |
| R12 | location row click | | `pushState` with `location=…`; row marked current |
| R13 | (CP3b) `a15-history-siteC-0720` | | an `<svg>` with one point per week and one band rect |

## 3. Make targets / commands

```
WEB := docker compose run --rm --no-deps web      # --no-deps: do not start api and db for a frontend check
make up         docker compose up -d --build --wait -V          (db, migrate, api, web)
make lint       unchanged: ruff check . ; ruff format --check .   (no frontend lint, Q3)
make typecheck  $(RUN) mypy ; $(WEB) npm run typecheck           (tsc --noEmit)
make test       $(RUN) pytest -q ; $(WEB) npm test                (vitest run)
make check      lint typecheck test, stopping at the first failure   ← runs ruff, mypy strict, pytest, tsc, vitest
```

`make seed`, `down`, `reset`, `migrate`, `psql`, `logs` are unchanged (`make reset` is expected to drop the anonymous volumes of the removed containers as well; checked at CP1a). `help` lists the same targets. The web app is served at http://127.0.0.1:5173.
One-time setup commands (recorded in the ai-log): the lockfile is generated in a throwaway directory, never on the bind mount: copy `package.json` and `package-lock.json` to it, run `docker run --rm -v "$TMP":/app -w /app node:22-alpine npm install --package-lock-only [--save[-dev] <pkgs>]` there, copy the two files back; dependency versions are the latest stable at that time and are fixed by the lockfile.
`CLAUDE.md`: the Stack line `Frontend (planned, T4)` becomes `Frontend: React + TypeScript (strict) + Vite, Vitest + React Testing Library`; the Commands section gains the web URL and says `make check` also runs the frontend typecheck and tests. Nothing else in CLAUDE.md changes.

## 4. Checkpoints (one review and one commit each; tests first inside each)

- **CP1a: run path only.** No application logic. Steps, in this order:
  1. `frontend/` skeleton: `package.json`, `tsconfig.json` (strict), `vite.config.ts` (proxy, host, port, jsdom test config), `index.html`, a placeholder `src/main.tsx`, `Dockerfile`, `.dockerignore`; the lockfile (§3 command).
  2. Compose `web` service and the Makefile (`up` with `-V`, `WEB` with `--no-deps`, `typecheck` and `test` extended). One trivial Vitest test (a smoke test that proves jsdom and the runner work, to be deleted or kept as the setup check) and `tsc --noEmit` wired into `make check`; `make check` green.
  3. **Empty-DB probe, before seeding** (`make reset && make up`, no `make seed`): `curl -si http://127.0.0.1:8000/api/accounts` and `curl -si http://127.0.0.1:8000/api/weeks` (no header). Record the **real** status line and body of both in this plan under "Deviations / CP1a evidence". Nothing is assumed: the expectation (200 `[]` for accounts; 404 `account_not_found` for weeks, because the demo account 15 is absent) is checked, not presumed. **If either is a 500, say so and stop**; do not start CP1b. Also load `http://127.0.0.1:5173/` in the browser to confirm the dev server and proxy answer (`/api/accounts` through :5173 returns the same body as :8000).
  4. `make seed`, then the fixtures captured with the §2 commands.
  5. The `up -V` and `pgdata` check: `make up` twice after the seed, `select count(*) from activity_events` still 12626. The `package.json` check: add a dependency, `make up`, confirm it is importable in the container (a throwaway change, reverted). `make reset` drops the anonymous volume (checked with `docker volume ls`). HMR works on the macOS bind mount (a throwaway edit shows in the browser; else `server.watch.usePolling`).
  6. The web healthcheck, last (cut item 2).
  Review and commit.
- **CP1b: client, URL logic, shell.** `types.ts`, `client.ts`, `urlState.ts`, `reconcile.ts`, `useAsync`, `useUrlState`; App shell with the account switcher, week selector, loading, `ErrorBox`, the unknown-account error, the week notice, and the `no_activity` / `not_enough_history` empty states. A1 and A7 need the report and the history request, so CP1b also has a **minimal** location list (names as buttons) and a **minimal** `LocationDetail` (fetches the history, shows the heading and `ErrorBox`); CP2 and CP3a replace them. Tests: §2a, §2b, §2d, A1 to A10. `make check` green. D-26, D-27, the CLAUDE.md edit (Stack line and Commands section only). Review and commit.
- **CP2: summary and location table.** `format.ts` (+ §2c F1 to F9), `AccountSummary`, `LocationTable` (API order, reasons), `DataQualityWarning`. Tests R1 to R9, R12.
- **CP3a: location detail.** `LocationDetail`, `WeeksTable`, the band text with `displayBand`, the hint when nothing is selected. Tests R10, R11.
- **CP3b: SVG chart.** `chart.ts` (C1 to C6) and `WeekChart` over the same data, the weeks table stays beneath it. Test R13.

**If time runs out, cut in this order:** (1) **CP3b**, the SVG chart: the detail already shows the weeks table and the band text (CP3a), which is the "weeks table against the band" fallback, so nothing is rewritten; (2) the **web healthcheck**: `make up --wait` treats a service without one as started. **Never cut:** `reconcile` and its tests (§2b, A1 to A9), the client header tests (§2d), the `make check` wiring, D-26 and D-27, the close verification. A third cut is not pre-agreed: if both are not enough, stop and ask.

## 5. Decision-log entries (same change)

- **D-26: dev server in compose, not static files from FastAPI.** Alternative: `vite build` and serve `dist` from the API (one origin and one container, but it couples the backend image to the frontend build and loses HMR). Consequences: the Vite proxy removes CORS; the `node_modules` anonymous volume and `up -V`; the dev server is not a production story.
- **D-27: URL reconciliation rules and the header-less bootstrap.** The table in §1c, the account-change flow, and why the account is adopted from `/api/weeks` (no hard-coded 15 in the UI, D-22). Alternatives: default to the first listed account; fall back to the demo account on an unknown id; show the 422 for a stale week.
  Consequences must state the **request waterfall**: with an `account` param, `/api/accounts` first, then `/api/weeks` only if `reconcileAccount` returns `ok` (an unknown id never reaches an account-scoped endpoint, A3); with no `account` param, `/api/accounts` and the header-less `/api/weeks` in parallel; then `/api/report`; then `/api/locations/{location}/history`. The steps are sequential on purpose: the account is only known to exist after `/api/accounts` (when the URL names one); the week to request is only known after `/api/weeks` (the URL week is validated against its list, so no request carries a stale week and no 422 comes from a URL); the location is only known to exist after `/api/report` (the URL location is validated against its rows, so no history request can 404 from a URL). The cost is four sequential round trips on a cold load with an `account` param (three without one); at demo size each is milliseconds, and parallel guessing would send requests that can fail and need cleanup. A bootstrap without `account` still makes one `/api/weeks` call (no header) and no second one after the account is adopted.
- No D-28: hand-written types and the fetch-mock boundary are Q1 and Q2 below.

## 6. Done when

- [ ] **CP1a:** `make check` green with `tsc` and the smoke test; the empty-DB probe (status and body of `/api/accounts` and `/api/weeks`, no header) recorded in this plan; fixtures captured; the `up -V` / `pgdata` and `package.json`-change checks done.
- [ ] Every row of §2 exists as a test and passes; `make check` is green (ruff, ruff format, mypy strict, pytest, `tsc --noEmit`, vitest). Record the pass counts (backend and frontend).
- [ ] The fixtures reproduce: after `make reset && make up && make seed`, the §2 commands run into a temporary directory and `diff -r` against `frontend/src/test/fixtures` is empty.
- [ ] `git diff --exit-code main -- data/ PLAN.md backend/` is empty; `git diff --name-only main` lists only `frontend/`, `docker-compose.yml`, `Makefile`, `CLAUDE.md`, `docs/decisions.md`, `plans/T4-frontend.md`.
- [ ] `grep -rnE "new Date|Date\.now|Intl\.DateTimeFormat" frontend/src` finds nothing outside `src/test`; no `.sort(` over report data in `frontend/src` outside `src/test` (checked by grep).
- [ ] `make up` twice after `make seed` leaves the data intact (`select count(*) from activity_events` = 12626), proving `up -V` leaves `pgdata` alone; `make up` after a `package.json` change picks the new dependency.
- [ ] D-26 and D-27 in `docs/decisions.md`; the CLAUDE.md Stack line and Commands section updated, nothing else in it.
- [ ] **Verification by John in the browser** after `make reset && make up && make seed`: (a) `http://127.0.0.1:5173/` opens on account 15, week 2026-07-20, and the URL becomes `?account=15&week=2026-07-20`; Site C `higher` is the top row; (b) account 6 at `2026-06-01` shows the spike (total 880); (c) account 20 shows the empty state; (d) a reload keeps account, week and location; (e) the back button walks account switches and week changes; (f) `?account=999`, `?week=2026-01-05` (notice and default week) and `?location=Nope` (dropped) behave as in §1c; (g) before `make seed`, the page loads and shows the API's error message instead of crashing (the status and body to expect are the ones recorded by the CP1a probe, not an assumption); (h) displayed numbers equal the `curl` values on the same endpoints, formatted by the §1d rules. The unknown-events warning cannot be seen in the seed (zero unknown events); it is covered by R9 only.
- [ ] Nothing committed without your say-so (one commit per checkpoint when you say so).

## 7. Open questions

Decisions (review): Q1 to Q3 as recorded in the pre-plan. **Q4 to Q9: the recommendations are accepted as written** (Q5 left to the T6 docs ticket; Q6 copy as proposed: "Normal range: 3 to 15 (the edges count as unusual)"; Q9 yes, account 20 is listed). Q4's risks are checked in CP1a.

| # | Issue | Recommendation | Trade-off |
|---|---|---|---|
| Q1 | **Hand-written API types, no codegen** (decided in the pre-plan). | Keep: mirror `schemas.py` by hand in `types.ts`. Real `curl` fixtures are the drift check (§2 regeneration, Done-when). | A backend field rename is not caught by `tsc`; it shows up as a failing fixture test only after the fixtures are regenerated. Codegen needs a running API at build time. |
| Q2 | **Test boundary: stub global `fetch`, keep the real client** (decided in the pre-plan). | Keep. It tests the header, the path encoding and the error mapping, which mocking the client module would skip. | The stub router must mirror the real paths; K1 to K8 and A1 to A10 use it with recorded calls. |
| Q3 | **No ESLint** (decided; reason recorded here). | Skip. `tsc` strict plus `noUncheckedIndexedAccess` covers most defects, and the config would cost time in a short ticket. | We lose `react-hooks/exhaustive-deps`. Mitigation: all fetching goes through one `useAsync(key, fn)` with the stale-response test A9, and effects elsewhere are kept trivial. |
| Q4 | **`node_modules` handling:** anonymous volume plus `up -V` (agreed), versus installing to a root `/node_modules` (the backend's `/opt/venv` pattern) or bind-mounting only `src` and the configs. | Anonymous volume + `-V`. Risks to verify at CP1: `compose run --rm` creates and removes its own copy; `-V` leaves `pgdata`; HMR works on the macOS bind mount (if not, `server.watch.usePolling`). | `-V` recreates the web container on every `make up`. The root `/node_modules` variant avoids the trap but Vite's `fs.allow` may then 403 files outside the project root, so it is the fallback only. |
| Q5 | **PLAN gaps (PLAN.md not edited).** PLAN §6 lacks `GET /api/accounts`, `z`/`diff`, and the `week null` shapes that T3 added (T3 plan Q2); PLAN §9 says 25 seed weeks while 17 are selectable (D-21). The UI follows the T3 shapes. | Leave to the T6 docs ticket, as T3 did. | Until then T3's plan and D-20 to D-22 are the source of the frontend's types. |
| Q6 | **Band edges.** The band is an open interval (D-17: `band_low < x < band_high`), so a total exactly at an integer edge is flagged (median 9, h 6: band 3 to 15, total 15 is `higher`). A line "Normal range 3 to 15" next to that looks contradictory. | Label it "Normal range: 3 to 15 (the edges count as unusual)". | The copy states a rule that lives in the backend; if D-17 changes, the copy must change. |
| Q7 | **Selected-week label.** The API gives only the Monday. | Show `Week of 2026-07-20` plus the account's `timezone`; no end date computed (no `Date` arithmetic). | No "Jul 20 – Jul 26" range, which would need date arithmetic or a library. |
| Q8 | **Node image and package versions** are not chosen here (`node:22-alpine` is the proposal; Vite, React, Vitest are "latest stable" at install). | Pin the Node major in the Dockerfile and let the lockfile fix the rest; record the versions in the ai-log. | A later `npm install` can move minor versions; `npm ci` and the lockfile prevent it for reviewers. |
| Q9 | **A switcher entry for account 20** (no events) is listed like the others. | Yes: it is the empty-state demo (verification c). | None. |

## Deviations / CP1a evidence

**Run path checks (CP1a step 2 review).** With the stack up: `curl -si http://127.0.0.1:5173/api/health` -> `HTTP/1.1 200 OK`, `server: uvicorn`, body `{"status":"ok","db":"ok"}`; `curl -si -H 'X-Account-Id: 6' http://127.0.0.1:5173/api/weeks` -> `HTTP/1.1 200 OK`, body `account` = `{'id': 6, 'name': 'Metro Collision Centers', 'timezone': 'America/New_York'}` (the header passes through the proxy); `curl -si http://127.0.0.1:5173/` -> `200 OK`, `Content-Type: text/html`, Vite's HMR client injected, `<div id="root">` and `/src/main.tsx` present.

**Deviation: host `frontend/node_modules`.** The first lockfile generation ran `npm install --package-lock-only` on the bind mount and left `frontend/node_modules/.package-lock.json` on the host (cause: npm writes its hidden lockfile there even with `--package-lock-only`). It was deleted. The directory itself came back: Docker creates an empty `frontend/node_modules` as the mount point of the anonymous volume each time `web` starts (confirmed: stopped `web`, `rmdir` worked, `docker compose start web` recreated it, 0 entries); while the container exists, `rm -rf` on it fails with "Permission denied". It is git-ignored and empty. The plan sentences (§1a, §3) were corrected, and the lockfile is now generated in a throwaway copy.

**Deviation: `@types/node`.** It was first installed as `^26.6.6` (latest), newer than the `node:22` image; it is pinned to `^22` (lockfile: 22.20.5), regenerated in a container in a throwaway copy. Needed because `vite.config.ts` reads `process.env.API_URL` (TS2591 without it).

**Known limit (not fixed):** `"node"` in `tsconfig` `types` applies to every file under `src`, so `process` and other Node globals also type-check in browser code. A reference to `process` in `src` would compile and then fail in the browser. Accepted for now; the alternative is a separate `tsconfig.node.json` for `vite.config.ts`.

**CP1a step 3: empty-DB probe** (`make reset && make up`, no `make seed`; run 2026-11-09, no header on either call):

```
$ curl -si http://127.0.0.1:8000/api/accounts
HTTP/1.1 200 OK
server: uvicorn
content-length: 2
content-type: application/json

[]

$ curl -si http://127.0.0.1:8000/api/weeks
HTTP/1.1 404 Not Found
server: uvicorn
content-length: 76
content-type: application/json

{"error":{"code":"account_not_found","message":"account 15 does not exist"}}
```

Result: neither is a 500. It matches the expectation of step 3 (200 `[]`; 404 `account_not_found`, the demo account 15 being absent), and it is the one error shape (D-20). Through the Vite proxy on :5173 both calls return the same status and body. So on an unseeded DB the page gets an empty account list and an `account_not_found` error; Done-when (g) means the UI must render that message.

**CP1a steps 4 to 6 (run 2026-11-09).**

- **Fixtures (step 4).** `make seed` -> `seed loaded: 20 accounts, 12626 events`; the 12 files were captured with the §2 commands into `frontend/src/test/fixtures/` (plus a `README.md` with the same commands). Sanity check, not a source of expected values: `a15-report-0720` first location `Site C`, verdict `higher`; `a15-history-siteC-0720` has 13 weeks (2026-04-27 … 2026-07-20), last role `selected` (matches R11's arithmetic); `a6-report-0601` account total 880, `higher`; `a20-report` verdict `no_activity`, `week` null; `a20-weeks` `[]` / `null`; `a6-history-siteG-0601` `band_low` -1.4303999999999997 (S16's −1.4304), `higher`; the two error fixtures carry the expected codes `account_not_found` and `invalid_week`. Regeneration into a temp dir and `diff -r` against the committed fixtures: empty.
- **`up -V` and pgdata (step 5).** After `make seed`, `make up` twice: `select count(*) from activity_events` = 12626. `-V` replaced `web`'s `/app/node_modules` volume (a new volume name each time) and left `pgdata` alone.
- **`package.json` change (step 5).** Throwaway: `ms` added in a throwaway copy of `package.json` and `package-lock.json`, copied back, `make up`: the node_modules volume was renewed and `require('ms')` worked in the container (`7200000` for `'2h'`). Reverted from a backup, `make up`: `ms` is gone. The SHA-256 of `package.json` (`a51c97ee…`) and `package-lock.json` (`18b06d66…`) are identical before and after, and `cmp` against the backup is clean. `git diff` is empty for both files only trivially, because `frontend/` is still untracked until the CP1a commit; the checksums are the proof.
- **`make reset` (step 5).** It removed `web`'s anonymous volume (the volume name no longer exists, and the volume count went 13 -> 11, the other one being `relay_pgdata`).
- **Finding, not fixed: `up -V` leaves the replaced volumes behind.** Each `make up` creates a new anonymous node_modules volume and the previous one is not removed; across two `make up` runs the volume count went 11 -> 13, and `docker volume ls -f dangling=true` listed 8 dangling anonymous volumes (some may belong to other projects). They stay until `make reset` (for the current one) or `docker volume prune`. `make check` does not leak volumes (13 before and after). Cost: disk, one node_modules copy per `make up`; no correctness effect.
- **Web healthcheck (step 6).** `wget -qO /dev/null http://127.0.0.1:5173/`, interval 3s, timeout 3s, retries 15. `docker compose ps`: `relay-web-1 ... Up 3 seconds (healthy)`, api and db healthy too. This is cut item 2: removing the `healthcheck:` block from the `web` service undoes it.
- **`make check` after step 6:** exit 0; ruff "All checks passed!", "41 files already formatted", mypy "no issues found in 38 source files", pytest "274 passed", `tsc --noEmit` clean, vitest "1 passed".
- **Left for John:** the HMR check in the browser (instructions in the session).

