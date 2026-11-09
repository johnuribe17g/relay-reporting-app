# T4: Frontend

Status: **APPROVED**, with these review changes applied: (1) CP1 split into CP1a (run path only) and CP1b (client, URL logic, shell); (2) R11's expected row count is calendar arithmetic, not read from the fixture; (3) Done-when (g) became a CP1a step that records the real status and body of the empty-DB probe; (4) D-27 states the request waterfall; (5) Q4 to Q9 accepted as recommended (Q5 left to T6, Q6 copy as proposed, Q9 yes).
Source: PLAN.md §1, §4, §5, §6, §8 (ticket 4), §9, §10; decisions D-13, D-17, D-20 to D-22; plans/T3-backend-api.md (§1b, §1d, §7); T1 plan §9 Q10 (frontend checks join `make check` here). Data facts: docs/data-profile.md (via the T3 anchors).
Branch: `feat/T4-frontend` (created, checked out). No commits until asked.
Pre-plan decisions (John): header-less bootstrap, unknown account = error state, global `fetch` stub, no ESLint, no auto-select of a location, CLAUDE.md edit limited to the Stack line and the Commands section, decision log limited to D-26 and D-27.

**In:** the single screen (PLAN §5): account switcher (labeled as a demo stand-in for login), week selector, account summary, location table in API order with unjudged rows and their reason, location detail (about 12 weeks plus the selected week against one band), URL state, the states loading / error / `no_activity` / `not_enough_history` / data-quality warning; a `web` service in docker-compose; Vitest + React Testing Library + `tsc --noEmit` inside `make check`.
**Out:** AI summary, per-type verdicts, styling beyond the minimal plain CSS of CP3c (no responsive design, dark mode, animations, icons or redesign), ESLint, a production build or static serving, auth, **any change to `backend/`**, `data/`, `PLAN.md`. The only non-frontend files touched: `docker-compose.yml`, `Makefile`, `CLAUDE.md` (Stack line + Commands only), `docs/decisions.md` (D-26, D-27), this plan.
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
  src/format.ts           pure: fmtNum, fmtZ, fmtDiff, displayBand, fmtBand, fmtAsOf, copy helpers, glossary(parameters) (CP3c)
  src/chart.ts            pure: chartGeometry            (CP3b)
  src/styles.css          plain CSS, imported in main.tsx (CP3c, last part of CP3c, first to be cut)
  src/hooks/useAsync.ts   one small hook: key + abortable fetch -> {status, data, error}
  src/hooks/useUrlState.ts   URLSearchParams <-> history, popstate
  src/components/         AccountSwitcher, WeekSelector, AccountSummary, LocationTable, LocationDetail,
                          WeeksTable, WeekChart (CP3b), Glossary (CP3c), ErrorBox, Notice, DataQualityWarning
  src/test/               setup.ts, mockFetch.ts, fixtures/*.json + README.md (§2, capture commands)
```

No router, no state library, no data-fetching library, no CSS framework. Function over form: semantic HTML and one plain `styles.css` (CP3c, scope change by John).

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
- A glossary (CP3c, scope change by John): a `<details>` block below the account summary tiles and above the location table (position changed by John after CP3c's first build; the plan originally said below the table), summary "What do these numbers mean?", one line each for Normal (median), Normal range, Score (z), Difference, Too quiet and Not enough history. The strings live in `format.ts` (`glossary(parameters)`), next to the other copy, and **every number in them comes from `report.parameters`** (`baseline_weeks`, `z_min`, `min_abs`, `min_baseline_median`, `min_history_weeks`), never a literal. The same one-line definitions are the `title` of the matching table headers.
- The location rows and the account summary carry `data-verdict="<verdict>"` (a styling hook for CP3c; the verdict text is always shown, color never replaces it).
- Each of the six verdicts has text. Account level: `no_activity` (week `null`, 200) is its own empty state; `not_enough_history` with `week null` (events but no judgeable week; none in the seed) gets its own message, not the `no_activity` one.
- `data_quality.unknown_events_in_window > 0` shows a warning at account level and in the detail, worded "in the baseline window plus this week", not "this week".
- Errors: `ErrorBox` renders `{code, message}` from `ApiError`, for any of the four requests.

### 1e. Deliberately not done

ESLint (Q3), a production build in `make check`, snapshot tests, per-type verdicts, styling beyond CP3c's minimal CSS, a location auto-select, re-ranking or grouping, caching of responses, rounding on the server, any backend change.

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
| R1 | `a15-report-0720`, account summary (carries `data-verdict="normal"`) | total 20; median 19; MAD 4; spread max(5.9304, 4.359, 1) = 5.9304; z = 1/5.9304 = 0.1686; h = max(11.8608, 3) → band 7.1392 … 30.8608 | `20`, normal `19`, range `7.1 to 30.9`, `0.17`, verdict normal |
| R2 | `a15-report-0720`, locations (the row carries `data-verdict="higher"`) | Site C: total 12, median 5.5, spread √5.5 = 2.3452 (> 1.4826·1), z = 6.5/2.3452 = 2.7716, diff 6.5, h = 4.6904 → 0.8096 … 10.1904 | first row is Site C with higher-than-usual, `12`, `5.5`, `0.8 to 10.2`, `2.77`, `+6.5` |
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
| R14 | (CP3c) glossary with `parameters` changed in a clone of `a15-report-0720`: `z_min 2.5`, `min_abs 4`, `baseline_weeks 9` (the fixture has 2, 3 and 12) | the copy is `… over up to the last {baseline_weeks} weeks …`, `… a week is flagged from ±{z_min}, and only if the difference is at least {min_abs} events.` Whole phrases, because `±2` alone is a substring of `±2.5` | the glossary text contains `from ±2.5,`, `at least 4 events` and `last 9 weeks`, and does **not** contain `from ±2,`, `at least 3 events` or `last 12 weeks`; the `title` of the `Score (z)` header contains `from ±2.5,` too; the summary text is `What do these numbers mean?` and the block is a `<details>` |
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
- **CP3c: minimal CSS and a short glossary** (two scope changes by John; order: after CP3b, glossary first and CSS last, see Deviations).
  *CSS:* one `frontend/src/styles.css` imported in `main.tsx`. No dependency, no Tailwind, no CSS framework, no class-naming system. Scope: a system font stack; a max-width content column with margins and spacing; table borders and row striping; the header controls on one line; verdict badges colored through a `[data-verdict]` attribute selector (`higher`, `lower`, `too_quiet`, `not_enough_history`, `normal`) with 4 to 5 CSS variables. Color never replaces the verdict text; AA contrast. About 100 lines at most. No layout change that alters test queries (roles and text stay). The components already carry `data-verdict="<verdict>"` on each location row and on the account summary (added in CP2), so the CSS part touches neither components nor tests.
  *Glossary:* a `<details>` block below the account summary tiles and above the location table (John moved it there; it stays closed by default), summary "What do these numbers mean?", with one line each (proposed copy, `{...}` from `report.parameters`):
  - **Normal (median):** the middle value of the weekly totals over up to the last {baseline_weeks} weeks; half the weeks were above it, half below. ("up to": a newer location has fewer weeks; the account summary line shows the weeks actually used, `baseline.weeks_used`.)
  - **Normal range:** totals inside it count as normal; a total at an edge or outside it is flagged. It comes from the median and how much the weeks usually vary.
  - **Score (z):** how unusual this week is, in units of typical week-to-week variation. 0 is exactly normal; a week is flagged from ±{z_min}, and only if the difference is at least {min_abs} events.
  - **Difference:** this week's total minus the median.
  - **Too quiet:** the normal week has fewer than {min_baseline_median} events, too few to judge a quiet week.
  - **Not enough history:** fewer than {min_history_weeks} weeks of data, too few to judge.
  The same one-line definitions (first four) are the `title` attribute of the matching `<th>` in `LocationTable`. The strings live in `format.ts` as `glossary(parameters)`; a new `Glossary` component renders them; `ReportView` places it between the account summary and the table. One new test, **R14** (§2f). Mutation check at CP3c: hard-code `z_min` 2 in the glossary copy -> R14 must fail. Because the glossary changes components and adds a test, CP3c is not purely stylistic; the existing tests stay as they are (the glossary's `<dt>` texts do not collide with the table or summary queries, which are scoped to their own region or table).
- **CP3b: SVG chart.** `chart.ts` (C1 to C6) and `WeekChart` over the same data, the weeks table stays beneath it. Test R13.

**If time runs out, cut in this order (John's call, after CP3a):** (1) the **CSS** part of CP3c, (2) the **glossary** part of CP3c. The **SVG chart (CP3b) is not a cut item.** CP3c is built glossary first and CSS last, so a partial CP3c is still coherent. **Never cut:** `reconcile` and its tests (§2b, A1 to A9), the client header tests (§2d), the `make check` wiring, D-26 and D-27, the close verification. A further cut is not pre-agreed: if both are not enough, stop and ask. Out of scope for CP3c: responsive design, dark mode, animations, icons, any redesign. (The web healthcheck, formerly cut item 2, was already built in CP1a.)

## 5. Decision-log entries (same change)

- **D-26: dev server in compose, not static files from FastAPI.** Alternative: `vite build` and serve `dist` from the API (one origin and one container, but it couples the backend image to the frontend build and loses HMR). Consequences: the Vite proxy removes CORS; the `node_modules` anonymous volume and `up -V`; the dev server is not a production story.
- **D-27: URL reconciliation rules and the header-less bootstrap.** The table in §1c, the account-change flow, and why the account is adopted from `/api/weeks` (no hard-coded 15 in the UI, D-22). Alternatives: default to the first listed account; fall back to the demo account on an unknown id; show the 422 for a stale week.
  Consequences must state the **request waterfall**: with an `account` param, `/api/accounts` first, then `/api/weeks` only if `reconcileAccount` returns `ok` (an unknown id never reaches an account-scoped endpoint, A3); with no `account` param, `/api/accounts` and the header-less `/api/weeks` in parallel; then `/api/report`; then `/api/locations/{location}/history`. The steps are sequential on purpose: the account is only known to exist after `/api/accounts` (when the URL names one); the week to request is only known after `/api/weeks` (the URL week is validated against its list, so no request carries a stale week and no 422 comes from a URL); the location is only known to exist after `/api/report` (the URL location is validated against its rows, so no history request can 404 from a URL). The cost is four sequential round trips on a cold load with an `account` param (three without one); at demo size each is milliseconds, and parallel guessing would send requests that can fail and need cleanup. A bootstrap without `account` still makes one `/api/weeks` call (no header) and no second one after the account is adopted.
- No D-28: hand-written types and the fetch-mock boundary are Q1 and Q2 below.

## 6. Done when

- [x] **CP3c (if built):** `styles.css` is about 100 lines at most, imported in `main.tsx`, adds no dependency, `package.json` and the lockfile are unchanged by it; verdict colors use `[data-verdict]` and the verdict text stays on screen; the text/background pairs meet AA (4.5:1, computed in the session). The glossary: `<details>` between the account summary and the table with the six lines, every number from `report.parameters`, the same definitions as `title` on the four matching headers, R14 passes, the mutation that hard-codes `z_min` 2 fails R14, and every other test is unchanged and green.
  - Evidence: `wc -l frontend/src/styles.css` = 96; `frontend/src/main.tsx:4` is `import "./styles.css";`; no `@media` in the file; 3 rules select on `[data-verdict]` (the badge base, higher/lower, too_quiet; a 4th line is a comment); the CP3c commit `dc45091` contains no `package.json` or lockfile path and no file outside `frontend/src` and `plans/`. The verdict label stays as text: R8 (`render.test.tsx`) asserts the labels in the rows, and R1/R2 the summary and row `data-verdict`. AA: the dataviz script's `contrast()` run in this session gave 4.68:1 (surface text on `#d03b3b`), 10.73:1 (ink on `#fab219`), 16.04:1 (ink on the neutral), 7.09:1 (muted on the stripe), all at least 4.5:1. Glossary: `ReportView` order in `frontend/src/App.tsx` is `<AccountSummary>`, `<Glossary>`, then `<h3>Locations</h3>` and `<LocationTable>`; R14 (in the 90 passed of `make check` this session) checks the six lines, the numbers from `report.parameters`, the four header `title`s and the `<details>`; mutation (w), `z_min` hard-coded as 2, failed R14 (recorded in this plan, CP3c deviations). `git show dc45091` removes no line from `render.test.tsx` or `chart.test.ts` (additions only), and `make check` this session: vitest 90 passed.
- [x] **CP1a:** `make check` green with `tsc` and the smoke test; the empty-DB probe (status and body of `/api/accounts` and `/api/weeks`, no header) recorded in this plan; fixtures captured; the `up -V` / `pgdata` and `package.json`-change checks done.
  - Evidence: `make check` this session: `tsc --noEmit` clean and vitest 90 passed, including `src/test/smoke.test.tsx`. The empty-DB probe (`GET /api/accounts` -> 200 `[]`; `GET /api/weeks` -> 404 `account_not_found`, no 500) is recorded in this plan under "Deviations / CP1a evidence", as are the 12 fixtures, the `make up` x2 count of 12626 and the `package.json` change (SHA-256 identical before and after, `ms` importable then gone). Re-run in this closing session: the fixture `diff -r` and the 12626 count (see the next items). The HMR check on the macOS bind mount was left to John and is not part of this item; no result for it is recorded.
- [x] Every row of §2 exists as a test and passes; `make check` is green (ruff, ruff format, mypy strict, pytest, `tsc --noEmit`, vitest). Record the pass counts (backend and frontend).
  - Evidence: a script over `frontend/src/**/*.test.ts*` found a test named for every row: P1-P8 (`urlState.test.ts`), RA1-RA4, RW1-RW6, RL1-RL4 (`reconcile.test.ts`), F1-F9 (`format.test.ts`), C1-C7 (`chart.test.ts`; C7 added by John), K1-K10 (`client.test.ts`; K9 and K10 added in review), A1-A10 (`App.test.tsx`), R1-R15 and R17 (`render.test.tsx`; R15 and R17 added during the ticket). Missing rows: none. `make check` this session, exit 0: ruff "All checks passed!", "41 files already formatted", mypy "no issues found in 38 source files", pytest "274 passed", `tsc --noEmit` clean, vitest "Test Files 8 passed, Tests 90 passed".
- [x] The fixtures reproduce: after `make reset && make up && make seed`, the §2 commands run into a temporary directory and `diff -r` against `frontend/src/test/fixtures` is empty.
  - Evidence: in this closing session, with the seeded dev API, the twelve §2 commands were run into a temporary directory and `diff -r <tmp> frontend/src/test/fixtures --exclude=README.md` printed nothing (12 files). The same check passed in CP1a after `make reset`, `make up` and `make seed` (recorded in this plan). The closing run did not repeat `make reset`, which drops the dev DB; the backend has no diff against main (`git diff --exit-code main -- backend/` exits 0), so the API output cannot have changed.
- [x] `git diff --exit-code main -- data/ PLAN.md backend/` is empty; `git diff --name-only main` lists only `frontend/`, `docker-compose.yml`, `Makefile`, `CLAUDE.md`, `docs/decisions.md`, `plans/T4-frontend.md`.
  - Evidence: `git diff --exit-code main -- data/ PLAN.md backend/` exits 0 this session. `git diff --name-only main HEAD` lists only `CLAUDE.md`, `Makefile`, `docker-compose.yml`, `docs/decisions.md`, `plans/T4-frontend.md` and `frontend/`. The working tree also has an uncommitted `ai-log/notes.md` (not part of T4; it was already modified when the branch was created and stays out of the commits unless John says otherwise).
- [x] `grep -rnE "new Date|Date\.now|Intl\.DateTimeFormat" frontend/src` finds nothing outside `src/test`; no `.sort(` over report data in `frontend/src` outside `src/test` (checked by grep).
  - Evidence: this session, `grep -rnE 'new Date|Date\.now|Intl\.DateTimeFormat' frontend/src | grep -v 'src/test/'` and `grep -rnE '\.sort\(|\.reverse\(|toSorted|toReversed' frontend/src | grep -v 'src/test/'` both print 0 matches; a control line (`echo 'a.sort(x)' | grep -cE '\.sort\('`) prints 1.
- [x] `make up` twice after `make seed` leaves the data intact (`select count(*) from activity_events` = 12626), proving `up -V` leaves `pgdata` alone; `make up` after a `package.json` change picks the new dependency.
  - Evidence: this session, `make up` run twice and `select count(*) from activity_events` = 12626; `docker compose ps` shows api, db and web healthy. The `package.json` change (`ms` added in a throwaway copy, `make up`, `require('ms')` worked, reverted from a backup, `ms` gone, SHA-256 of both files identical) was run in CP1a in this session and is recorded in this plan; it was not repeated in the closing session because that would edit `package.json`. Finding recorded there: `up -V` leaves the replaced volumes behind (D-26).
- [x] D-26 and D-27 in `docs/decisions.md`; the CLAUDE.md Stack line and Commands section updated, nothing else in it.
  - Evidence: `docs/decisions.md` has `## D-26` at line 425 and `## D-27` at line 441. `git diff main HEAD -- CLAUDE.md` shows only the Stack line (`Frontend (planned, T4)` -> `Frontend: React + TypeScript (strict) + Vite, Vitest + React Testing Library`) and the Commands section (`make up`, `make check` and the API/web URL lines).
- [x] **Verification by John in the browser** after `make reset && make up && make seed`: (a) `http://127.0.0.1:5173/` opens on account 15, week 2026-07-20, and the URL becomes `?account=15&week=2026-07-20`; Site C `higher` is the top row; (b) account 6 at `2026-06-01` shows the spike (total 880); (c) account 20 shows the empty state; (d) a reload keeps account, week and location; (e) the back button walks account switches and week changes; (f) `?account=999`, `?week=2026-01-05` (notice and default week) and `?location=Nope` (dropped) behave as in §1c; (g) before `make seed`, the page loads and shows the API's error message instead of crashing (the status and body to expect are the ones recorded by the CP1a probe, not an assumption); (h) displayed numbers equal the `curl` values on the same endpoints, formatted by the §1d rules. The unknown-events warning cannot be seen in the seed (zero unknown events); it is covered by R9 only.
  - Not ticked: no browser run exists. John was handed the checks to do in the browser (the lists after CP3b, CP3c and the layout addition) and has not reported a result in this session; the dev server and the proxy were exercised only with `curl` (CP1a: `:5173/api/health`, `/api/weeks` with `X-Account-Id: 6`, `/`). The automated tests cover the same behavior in jsdom (a-c: A1, A2, A6, R2, R3; d: A1; e: A7; f: A3, A4, A5; g: the empty-DB probe plus A10) but they do not replace the look-and-feel check, and (h), the numbers against `curl` formatted by the §1d rules, was not done by hand.
- [x] Nothing committed without your say-so (one commit per checkpoint when you say so).
  - Evidence: `git log --format='%h %an' main..HEAD` shows 8 commits, all authored by `johnuribe17g`. In this session John said "I committed stop point 1", "I committed CP2" and "I committed CP3b", "I'll commit the plan as docs(plans): add T4 plan before any code", and, for CP1a and CP3a, that he would review and commit them. I ran no `git add`, `git commit`, `git reset` or `git checkout` in this session, except `git checkout -b feat/T4-frontend` (step 2 of /plan-ticket). Limit: for the commits of CP1b stop point 2 (`3991b1d`) and of CP3c (`dc45091`) John did not state in this session that he made them; they carry his identity and I did not run a commit.

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
| Q10 | **Glossary and the cut order.** CP3c holds both the CSS and the glossary. | **Decided by John (after CP3a):** order CP3b, then CP3c with the glossary first and the CSS last; cut order if ever needed: the CSS, then the glossary; the chart is not a cut item. | Cutting the CSS first keeps the explanation of the numbers; nothing is expected to be cut. |
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

## Deviations (CP1b)

- **Two commits for CP1b**, not one: stop point 1 (`feat: add typed API client, URL state and reconcile with tests`, already committed by John) and stop point 2 (the hooks, the App shell, A1 to A10, D-26, D-27, the CLAUDE.md edit; not committed).
- **Review fixes after stop point 1 (tests first):** K9 (a 200 with a non-JSON body is `ApiError(200, "unexpected_response")`) and K10 (abort with a custom reason through a real `AbortController` is not an `ApiError`); K8 was reworked to use a real `AbortController`. The client now decides an abort by `signal?.aborted` in the fetch catch and in both body parses, and rethrows the original error. Finding: with the old `instanceof DOMException` check, K8 also failed under jsdom, because `controller.abort()` produces Node's `DOMException`, which is not `instanceof` jsdom's `DOMException` (the check is realm-fragile). Mutation, the `instanceof`-only check restored: K8 and K10 fail.
- **`reconcileAccount` returns `{kind: "ok", id: "15"}`** (the id as the string the header and the URL use); the plan said "id 15".
- **`scope` and `adopted` state in `App` (not in the plan).** `/api/weeks` must run exactly once on a header-less bootstrap, but after the adoption the URL gains `account=15`, which would change the weeks request key and refetch (and abort and refetch the report). `scope` is the account the weeks request is for (`null` = header-less); it follows the URL except right after adoption, tracked by `adopted`. It is derived state set during render, so there is no one-render lag.
- **`useAsync` tags each result with its key** and returns `loading` when the stored key is not the current one, so a render under a new key never shows the previous key's data. The stale-response guard (abort plus a `live` flag) stays, and an aborted request never produces an error state.
- **Test infrastructure:** `src/test/setup.ts` registers `cleanup`, `vi.unstubAllGlobals()` and a history reset in `afterEach` (Vitest runs without globals, so Testing Library's automatic cleanup is not active); `src/test/mockFetch.ts` is the router over the fixtures, with a `held()` helper for pending or abortable responses; `tsconfig.json` gets `resolveJsonModule`. The `open()` helper in `App.test.tsx` uses `pushState`, not `replaceState`: an earlier test's `history.back()` leaves a forward entry, and the next push truncates it, which made `history.length` comparisons wrong (found when A8 failed).
- **Test deviations:** A8 is two tests (keeps / drops the location); for the keep case account 6's Site G history is a stand-in body (the 2026-06-01 fixture) for any week, and only the request path is asserted. A9 runs twice (the mock honors the abort, or answers late) and asserts 15 location buttons for account 6 (data profile §1: 15 locations), not "Site C is absent", because account 6 also has a Site C. A10 is three tests (loading, the API's error shape, a network failure).
- **No StrictMode** in `main.tsx`. The trade-off: `useAsync` already aborts the superseded request, so StrictMode's double-invoked effects would cost only one duplicate request per fetch in development, aborted at once. What is given up is StrictMode's development check for effects without a cleanup (the adopt/correct and location effects in `App` have none and do not need one). Turning it on is a one-line change.
- **Review fix (effect dependencies).** The adopt/correct effect and the location effect in `App` had incomplete dependency lists (Q3's mitigation said effects outside `useAsync` stay trivial). Both lists are now complete: `weekResult` and `locationResult` are `useMemo`'d so they are stable dependencies, and the location effect depends on the primitive `locationCorrected`. No loop is possible: `replace` runs only when the URL differs from the desired one, and `setNotice` returns the previous value when nothing changed. Behavior is unchanged (A1 to A10 pass with the same request counts).
- **Minimal pieces as planned:** `LocationList` (names as buttons) and `LocationDetail` (heading only); the account summary is one line, `Account verdict: <verdict>`. CP2 and CP3a replace them.

**CP1b mutation checks (each applied alone, reverted, `cmp` against a backup).** Stop point 1: (a) `getWeeks` always sends the header: K2. (b) `reconcileAccount` with `Number()`: RA3 for `"015"`. (c) no notice for an out-of-range week: RW3 and both RW4 rows. (d) case-insensitive location match: RL3. (e) no `encodeURIComponent` on the location: K4 and K5. Review fix: `instanceof`-only abort check: K8 and K10. Stop point 2: (f) `/api/weeks` in parallel with `/api/accounts` when the URL has an account: both A3 rows. (g) `useAsync` without abort and without the superseded guard: both A9 rows. (h) the account switch uses `replaceState`: A7. (i) the week correction uses `pushState`: A2, the three A4 rows and A7. None survived.

**CP1b test counts (`make check`, exit 0):** ruff clean, "41 files already formatted", mypy "no issues found in 38 source files", pytest 274 passed, `tsc --noEmit` clean, vitest 54 passed in 5 files (urlState 8, reconcile 19, client 10, App 16, smoke 1). Greps: no `new Date`, `Date.now` or `Intl.DateTimeFormat` and no `.sort(` in `frontend/src` outside `src/test` (the date grep was first run with an unquoted glob that errored under zsh, then re-run correctly; a control line confirms the pattern matches).

## Deviations (scope change by John, before CP2)

- **Minimal plain CSS added to T4** as a new checkpoint **CP3c**, after CP3a and before CP3b (see §4): one `frontend/src/styles.css`, no dependency, no framework, no class-naming system; system font stack, a max-width column, table borders and striping, the header controls on one line, verdict badges through `[data-verdict]` with 4 to 5 CSS variables, AA contrast, about 100 lines at most, no change to test queries.
- **Why plain CSS and not Tailwind:** one screen. Tailwind would add a dependency, a config and a lockfile change for no second use (PLAN §10).
- **Cut order becomes:** (1) CP3b, the SVG chart; (2) CP3c, the CSS. "Never cut" is unchanged. The web healthcheck (formerly cut item 2) was already built in CP1a.
- **Out of scope stays:** responsive design, dark mode, animations, icons, any redesign.
- **Consequence for CP2:** the location rows and the account summary get `data-verdict="<verdict>"` in CP2, so CP3c needs no component or test change.

## Deviations (CP2)

- **R9, location part moved to CP3a.** The plan's §1d puts the data-quality warning "at account level and in the detail"; the location detail is CP3a, so CP2 builds and tests `DataQualityWarning` at account level (`role="note"`, so it never collides with `alert` for errors or `status` for the week notice) and CP3a adds the location case.
- **Selector tightened in `App.test.tsx` (approved test, one line).** `getByLabelText(/^account/i)` matched the new `Account summary` region as well as the switcher and broke A1, A2, A7 and A9. The query is now `/^account \(demo/i` (the switcher's own label). No assertion changed.
- **`LocationList` removed**, replaced by `LocationTable`; the account summary is `AccountSummary` (a labelled `<dl>`: events this week, normal (median), normal range, score (z), difference, calls/leads/appointments), with the account time zone and `Data through <as_of>`. Both carry `data-verdict`. The normal range line says "(the edges count as unusual)" (Q6). The location button stays the only `button` per row, so A-tests' button queries are unchanged.
- **Unjudged reasons** (`too_quiet`: "normal is 3.5 events a week, below 4"; `not_enough_history`: "5 of 8 weeks") come from `reasonText(summary, parameters)`, so no number is hard-coded.
- **R8 is two tests** (location verdict labels; the two account empty states).

**CP2 mutation checks (each applied alone, reverted, `cmp` against a backup).** (j) `LocationTable` sorts by |z|: R4. (k) `fmtZ` uses "-" instead of U+2212: F1. (l) the baseline sentence hard-codes 12: R6 and F8. (m) `displayBand` stops clipping at 0: F5. None survived.

## Deviations (scope change by John, before CP3a)

- **A short glossary added to CP3c**, besides the CSS (see §4 and §1d): a `<details>` block "What do these numbers mean?" (originally below the location table; moved above it, see "Layout" below) with one line each for Normal (median), Normal range, Score (z), Difference, Too quiet and Not enough history. Every number in the copy comes from `report.parameters`; `{weeks}` is `parameters.baseline_weeks`, never a literal. The same definitions are the `title` of the matching table headers. The strings live in `format.ts` as `glossary(parameters)`. One new test, R14 (with `z_min 2.5`, `min_abs 4`, `baseline_weeks 9` in a clone, whole phrases), and one mutation (hard-code `z_min` 2 -> R14 fails).
- **Wording changes to the proposed copy:** "over up to the last N weeks" (a newer location has fewer weeks, and the account summary shows the weeks actually used); the two "not judged" reasons are two lines and carry their parameters (`min_baseline_median`, `min_history_weeks`) instead of the shared line "too few events, or too few weeks".
- **Correction to the CSS deviation above:** it said CP3c needs no component or test change. That held for the CSS alone. With the glossary, CP3c adds `Glossary` and `glossary()`, adds `title` attributes in `LocationTable` and places the block in `ReportView`, and adds R14. Existing tests are untouched.
- **Cut order unchanged in the plan's text** (CP3b, then CP3c), but see Q10: CP3c now holds content as well as polish.

## Deviations (CP3a)

- **R9, location part, built here** (moved from CP2): the warning in the detail, `role="note"`, worded as the window.
- **One extra test beyond the plan:** "a history error is shown with the API's code" (App-level, the history route answers 404): a regression guard for the error branch of `LocationDetail`. It passed against the minimal CP1b detail already, so it was not red first.
- **R11 expected values are all from the plan's arithmetic**, not from the fixture: the 13 Mondays 2026-04-27 .. 2026-07-20 and the totals `5,4,4,6,4,5,10,4,6,6,7,6` + `12` (T3 S6), plus median 5.5, z 2.77, diff +6.5 and the band 0.8 to 10.2.
- **"This week" in the detail is the point with `role: "selected"`**, not the last array element; the reason text for an unjudged location first used `weeks.length - 1` as the history weeks (the history response has no `history_weeks` field); **superseded by the review fix below**.
- **The note under the table** ("The normal range shown is the selected week's; earlier weeks are not judged against it here.") is the "chart note" of R11; CP3b reuses it. The first wording failed R11's phrase ("the selected week's") and was reworded, not the test.
- **The detail heading is the location name only** and the verdict line says "Selected week <date>" (not "Week of <date>"), so `getByText("Week of 2026-07-20")` in the App tests still finds exactly one element.

**CP3a mutation checks (the plan names none; each applied alone, reverted, `cmp` against a backup).** (o) the detail shows the raw band instead of `displayBand`: R10. (p) `WeeksTable` reverses the weeks: R11. (q) the detail hides the data-quality warning: R9 (location). (s) "This week" takes the first week's total instead of the selected one: R11. None survived.

## Deviations (CP3a review)

- **Fix: `history_weeks` comes from the report row.** `LocationDetail` had derived `history_weeks` as `weeks.length - 1`, the UI computing something the API already gives (the location's row in `/api/report`, which is loaded, has `history_weeks`). `LocationDetail` now takes a `historyWeeks` prop (`number | null`), and `ReportView` passes the selected row's `history_weeks`. Tests first (red, then green): **R17** (component) with a not_enough_history history whose window has 13 weeks, `historyWeeks` 5 and `min_history_weeks` 8: the detail shows "5 of 8" and not "12 of 8" (so `weeks.length - 1` would fail it); **R17** (end to end) the same through a cloned report row and history, `<App />`. The existing detail tests pass `historyWeeks={12}` (the full windows of T3 S6 and S16). Mutation: restoring `weeks.length - 1` makes both R17 tests fail.
- **Order and cut order (John's call, resolving Q10):** next is CP3b (SVG chart), then CP3c with the glossary first and the CSS last. Cut order if ever needed: the CSS, then the glossary; the chart is not a cut item. John does not expect to cut anything. This supersedes the earlier "CP3b first to be cut, CP3c second" and the earlier "CP3c after CP3a and before CP3b".

## Deviations (CP3b)

- **Colors and the dataviz skill.** One series, so one color (the skill's categorical slot 1, `#2a78d6`; `validate_palette.js --mode light` on it: all checks pass, contrast vs surface `#fcfcfb` at least 3:1), no legend box, a 2px line, points of radius 4 (the selected one 6) with a 2px surface ring, the band as a 12% wash of the same color, hairline solid axes, no gridlines, text in text tokens (`#52514e`, `#0b0b0b`), one label (the selected total). Colors are presentation attributes, so CP3c's CSS can override them through `data-role` and `data-chart`. Dark mode is out of scope.
- **`chartGeometry` also returns `plot` and the band rect's `x` and `width`** (the component draws the band over the full plot width); C1 to C6 assert only what the plan lists (`xs`, `ys`, `yMax`, `bandRect.y` and `.height`).
- **The "chart note" is now the chart caption** ("Shaded: normal range for the selected week (<band>). Earlier weeks are shown for context and are not judged against it."), as John specified. The CP3a note under the weeks table (and R11's phrase "the selected week's") was removed with it; R11's assertion now checks the caption text. The weeks table stays below the chart.
- **`WeekChart` returns nothing when the history has no baseline** (R15: no `<svg>`, the table stays, no empty frame). R15 passed before the chart existed (it is a guard, not a red test).
- **R13** checks 13 points (the R11 window arithmetic), exactly one `data-role="selected"` and it is the last, the selected point larger, one band rect, the `role="img"` name (location, 13 weeks, selected week and total, normal range), the axis labels (`0`, the Y maximum 12 = max(12, band high 10.19), the first and last week) and the caption through R11.

**CP3b mutation checks (each applied alone, reverted, `cmp` against a backup).** (t1) `chartGeometry` clips with its own `Math.max(0, ...)` and `displayBand` stops clipping: only F5 and R10 fail; **all chart tests (C1 to C6, R13) still pass**, because the chart then clips by itself, so this variant shows nothing about the chart. (t2) only `displayBand` stops clipping, `chartGeometry` still calls it: C1 fails (and F5, R10), which shows that the chart really depends on `displayBand`. (u) the Y axis starts at the data minimum: C1, C2, C3 and C4 fail. (v) the selected point is marked by index 0 instead of role: R13 fails. None survived.

## Deviations (CP3c; three additions by John, plus the CSS as amended)

- **Added by John at the start of CP3c (his call):**
  1. **Native hover on the chart:** a `<title>` inside each point, `<week>: <total> events` (the selected one adds ` (selected week)`); no JS tooltip layer. R13 asserts the selected point's title (`2026-07-20: 12 events (selected week)`) and the first point's (`2026-04-27: 5 events`, the first total of T3 S6). The format is John's literal one, so a week with a total of 1 reads "1 events".
  2. **`yMax` rounded up to a whole number** (counts are integers), so the Y axis never prints a value like 100.2: `Math.max(Math.ceil(max(data, band high)), 1)`. C1 to C6 keep their values (already integers); **C7** added: totals [5,7], band 1..10.19 -> yMax 11 (ys 53.636 and 39.091, band y 15.891, height 66.836). Mutation: no `ceil` -> C7 fails.
  3. **CSS last**, glossary first, in the amended scope (see §4).
- **Glossary as planned:** `glossary(parameters)` in `format.ts`, the `Glossary` component (a collapsed `<details>`, summary "What do these numbers mean?") under the account summary and above the location table (moved there afterwards, see "Layout" below), the same four definitions as `title` on the matching headers, **R14**. Parameters are written with `String(value)` (not `fmtNum`, which would round `2.25` to `2.3`), so the copy always equals the setting. R14 first checks the real fixture values (`from ±2,`, `at least 3 events`, `last 12 weeks`), then a clone (`z_min 2.5`, `min_abs 4`, `baseline_weeks 9`, `min_baseline_median 5`, `min_history_weeks 6`): the new phrases are present and the old ones absent. Mutation: hard-coding `z_min` 2 in the copy -> R14 fails.
- **CSS:** one `frontend/src/styles.css` (79 lines), imported in `main.tsx`; the CSS step touched no other `.tsx` (the `main.tsx` diff is the single import line). Page background `#fcfcfb` (the skill's chart surface, which the chart's point ring assumes), text tokens `#0b0b0b` and `#52514e`; verdict badges through `[data-verdict]` with `:is()` selectors, no class names and no markup change; the verdict text is always visible. No dependency, no framework; `package.json` and the lockfile have no diff. A production `vite build` compiles it (2.04 kB CSS) and the dev server serves it.
- **Badge colors (the skill's status palette):** `higher` and `lower` share **critical `#d03b3b`** (the flag is direction-neutral, PLAN §2, and the text says the direction), `too_quiet` is **warning `#fab219`**, `normal` and `not_enough_history` are a neutral gray (`#e9e8e3`). I first considered serious `#ec835a` for the flags; `validate_palette.js` rejected the pair serious/warning (normal-vision floor: dE 13.6 < 15, too close to tell apart by color). **Validator on `#d03b3b,#fab219` (light, surface `#fcfcfb`):** chroma floor PASS; CVD separation PASS (dE 24.4 deutan, 24.4 tritan); normal-vision floor PASS (dE 28.4); **lightness band FAIL** (`#fab219` L 0.811 is outside the categorical band 0.43 to 0.77) and **contrast vs surface WARN** (`#fab219` 1.79:1, relief required). Both come from using the colors as categorical series marks; here they are badge backgrounds behind text, the script's own scope note says a lone status or text color is checked with `contrast()`, and the relief the skill asks for (a visible label) is present. Text contrast with the script's `contrast()`: surface text on `#d03b3b` 4.68:1, ink on `#fab219` 10.73:1, ink on the neutral 16.04:1, muted on the stripe 7.09:1 (all at least 4.5:1, AA). Not applied from the skill: an icon next to the label for the sub-3:1 status color (it needs markup, which this CSS step was not allowed to touch); dark mode and texture (out of scope).

**CP3c mutation checks (each applied alone, reverted, `cmp` against a backup).** (w) `z_min` hard-coded as 2 in the glossary copy: R14. (x) `yMax` not rounded up: C7. (y) the selected point loses its title suffix: R13. None survived. (A first attempt at (w) did not apply because the search string did not match the file; its "90 passed" was discarded and the mutation was redone.)

**CP3c final state (`make check`, exit 0):** ruff clean, "41 files already formatted", mypy "no issues found in 38 source files", pytest 274 passed, `tsc --noEmit` clean, vitest 90 passed in 8 files. Greps: no `new Date`, `Date.now` or `Intl.DateTimeFormat` and no `.sort(`, `.reverse(`, `toSorted` in `frontend/src` outside `src/test`; the only `Math.max(0` is `displayBand`.

## Deviations (CP3c, layout addition by John)

- **Stat tiles and a wider layout (his call, within CSS of about 100 to 130 lines; no media queries).** The account summary and the location detail show their metrics as a wrapping row of stat tiles (small label, large value). The **only markup change** allowed and made: each `<dt>`/`<dd>` pair is wrapped in a `<div>` inside the existing `<dl>` (valid HTML) in `AccountSummary` and `LocationDetail`. Tests pass unchanged (they query by text; `valueOf` follows `dt.nextElementSibling`, still the `dd` inside the same `div`).
- **Per-type tiles (calls, leads, appointments)** are a separate, smaller group: with no markup change, the CSS styles the 6th tile onward (`:nth-child(n + 6)`) smaller and starts them on their own row. This relies on the tile order (five main tiles, then the per-type ones), which is the component's order. The **normal range** tile is the 3rd and spans two columns with a smaller value, because its text is long ("... (the edges count as unusual)"); this also relies on the order.
- **Page order:** header bar (title left, account and week selectors right), account summary tiles, **glossary (moved by John: below the summary tiles and above the table; the plan had said below the table; still a `<details>`, closed by default; a position change in `ReportView` only, R14 passes unchanged because it checks text)**, location table full width, then the location detail: its tiles, then the chart and the weeks table side by side when there is room (a CSS grid on the detail section with `auto-fit` and a 20rem minimum per column; stacked when not), with every other child of the section spanning the full width.
- **Glossary text in the plan updated** where it said "below/under the location table" (§1d, §4, §6 and the earlier deviation entries).

