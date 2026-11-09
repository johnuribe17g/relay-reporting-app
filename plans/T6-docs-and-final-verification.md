# T6: Docs and final verification

Status: **APPROVED** with John's review answers: README capped at ~250 lines; the "Technical choices" section moves verbatim from `ai-log/README.md` into the README (§8) and is removed there; the reflection already exists in `ai-log/README.md` (not edited; README §14 links to it); Q1 accepted (`make up`, then `make seed`); Q2 yes, as a correction note appended to D-09; Q3 answered by the table's "Data access" row; Q6 based on the table's last column plus sourced deferrals, marked draft; Q4, Q5, Q7 to Q10 as recommended; Q11: D-30 and D-31 are added with John's answers for the TODOs. Order: README draft shown first, then the rest.
Source: PLAN.md §8 (ticket 6), §4, §9, §10, §12, §13; CLAUDE.md (Commands); decisions D-01 to D-29; docs/data-profile.md; plans/T1 to T5 (what they leave for this ticket: T4 Q5 (PLAN gaps left to T6: §6 lacks `GET /api/accounts`, `z`/`diff` and the `week null` shapes that T3 added; §9's "25 seed weeks" is 17 selectable), T4 §1a and D-26 ("the README says the Vite dev server is not a production story"), T1 ("the README mention" that migration 1 is an adapted copy of `data/schema.sql`, D-07; the raw-counts note 881 → 880); T5 §0 "T6 follows D-29, not PLAN §6, on the 404 and the opt-in"); John's T6 brief of this session (scope, facts to get right, two short lines, time note placeholder, 16:10 deadline).
Branch: `feat/T6-docs-and-final-verification` (created from `main` at `48406eb`, checked out). No commits until asked.

**In:** the full `README.md` (new sections around the existing "AI summary: status" section, which stays word for word); `.env.example` checked against `docker-compose.yml` and the settings classes (edited only for a real gap); the `08-T5.md` entry in `ai-log/README.md`; a record of the verification (the checks in §2, evidence for `/close-ticket`).
**Out (John's, per the brief):** the clean-clone run and its timing; the reflection section of the AI log; the T4-close placeholders in `ai-log/notes.md`; the hours note (a placeholder only). **No code changes**; if John's clean-clone run finds a bug, the fix is a separate commit, not part of this ticket's docs. Not touched: `PLAN.md`, `data/`, `CLAUDE.md`, `backend/`, `frontend/`, `Makefile`, `docker-compose.yml`. `docs/decisions.md` only if John approves Q2 (one stale sentence in D-09) or the pending D-30/D-31 (his T5 close checklist).

## 1. Design

### 1a. Files

| File | Change |
|---|---|
| `README.md` | rewritten around the existing AI summary section (kept byte-identical, §2 check C7); outline in §1b |
| `.env.example` | checked (§1c); at most one comment line (Q7) |
| `ai-log/README.md` | add the `08-T5.md` entry in the style of the others; the "Reflection" placeholder stays John's |
| `plans/T6-docs-and-final-verification.md` | this plan, ticks and evidence at close |

### 1b. README outline (about 250 to 300 lines, a short table of contents at the top)

Each section says where its facts come from; nothing is copied from `docs/decisions.md`, it is linked by D-number.

| # | Section | Content | Facts from |
|---|---|---|---|
| 1 | What this is | two sentences: DASH-247, "was last week normal for us, and which location should I look at?"; the three screen parts; what is out (auth, alerting, forecasting, production infra) | PLAN §1, §5; CLAUDE.md |
| 2 | Run it | needs only Docker and `make`; `cp .env.example .env` is optional; **`make up`, then `make seed`** (two commands, Q1); URLs (web `http://127.0.0.1:5173`, API `http://127.0.0.1:8000`, `GET /api/health`, db on `127.0.0.1:5433`); what the first screen shows (account 15, week 2026-07-20, Site C `higher`, T3 S5/S6); before `make seed` the page shows the API's error, not a crash (T4 CP1a); `make down`, `make reset`; the ~15 minute target is John's to confirm (Q9) | CLAUDE.md Commands; D-12, D-13, D-22; T4 plan |
| 3 | Tests and the quality gate | the one-line command `make check` and what it runs (ruff check and format check, mypy strict, `tsc --noEmit`, pytest, vitest); the test databases are separate (`relay_test`, `relay_migrations_test`); counts **from the last `make check`: pytest 383 passed, vitest 104 passed** (re-run at close, Q5); the backtest (D-23: 4.93 % against an 8 % ceiling fixed before the run, not tuned) | Makefile; CLAUDE.md; D-23 |
| 4 | Configuration | a table of the 16 user-facing variables in §1c with default and purpose; says the four internal ones (`DATABASE_URL`, `TEST_DATABASE_URL`, `SEED_PATH`, `API_URL`) are set by compose; where the AI ones are explained (the AI summary section) | `settings.py`, `docker-compose.yml`, `.env.example` |
| 5 | Make targets | table from `make help`: the 12 targets help, up, down, reset, migrate, seed, psql, logs, lint, typecheck, test, check | Makefile |
| 6 | How I read DASH-247 | the user (one admin, one account, a demo account switcher standing in for login); **"normal" = a week compared with that location's own recent history**, plus an account rollup (D-02, D-08); the window (trailing 12 complete weeks before the selected week, median centre, zero-filled); complete weeks only, as-of anchored to the data (D-03); Monday to Sunday in the account's IANA time zone (D-04); the verdict (`spread = max(1.4826·MAD, √median, 1)`, `z_min` 2, `min_abs` 3, D-08, D-14, D-17); the views (account summary, ranked location table, location detail with 12 weeks and the band, glossary); which week is selectable (17 per account, 2026-03-30 to 2026-07-20, D-21) | PLAN §1, §2, §5; D-02 to D-08, D-14, D-17, D-21 |
| 7 | The data | (T1 leftover) migration 1 is an adapted copy of `data/schema.sql`, never an edit of it (D-07); 20 accounts, 12,626 events, account 20 has none; **the seed ends 2026-07-27, never `now()`**; the cleaning rules in the `clean_events` view (12 exact duplicates removed; no other cleaning, D-06); unknown event types counted separately (D-16); account 6's 2026-06-03 spike kept as real data (D-09): it hits all 15 locations, and **at 2026-06-01 12 of the 15 are flagged `higher` and 3 are unjudged (`too_quiet`)**, so PLAN §13's "all 15 locations flag together" is wrong and the README says so (D-23 has the counts). Raw profile counts are before dedupe: account 6's spike week is 881 in the profile and 880 in the app | data-profile §1, §7, §11 and its line 20; D-06, D-09, D-16, D-23 |
| 8 | Stack and why | D-01 (Python, FastAPI, SQLAlchemy 2.0 sync, Alembic, Pydantic v2, PostgreSQL 16; React, TypeScript strict, Vite). Notable choices, each one line plus a link: SQLAlchemy `text()` on a connection, no ORM models (Q3); Alembic migrations as the schema source, the `migrate` service, seed by truncate and reload (D-07, D-12); the `clean_events` plain view (D-05, D-06); statistics in pure Python, SQL only builds the zero-filled series (D-15); typed settings, `REPORT_` prefix (D-18); no frontend state library, state in the URL with reconciliation (D-27); Vite dev server behind a proxy, not a production serving story (D-26); everything under docker-compose (D-13); `data/` protected by deny rules (D-11) | D-01, D-05 to D-07, D-11 to D-13, D-15, D-18, D-26, D-27 |
| 8b | API at a glance (T4 Q5 leftover) | the five endpoints with one line each and a pointer to T3's plan for the JSON shapes: `GET /api/accounts` (the one unscoped endpoint), `GET /api/weeks`, `GET /api/report?week=`, `GET /api/locations/{location}/history?week=`, `POST /api/summary`; the `X-Account-Id` header with the demo default 15 (D-22); one error shape (D-20); verdicts and the `week null` states (`no_activity`, `not_enough_history`); says PLAN §6 is the sketch and T3 plus D-20 to D-22 and D-29 are the source | plans/T3 §1b to §1d; D-20 to D-22, D-29 |
| 9 | How the AI summary is kept honest | **unchanged section "AI summary: status"** (moved only as a block). Beside it, the two short lines (§1d) | existing README |
| 10 | Key assumptions | PLAN §12's nine rows condensed to one line each (question, working assumption, what breaks if wrong); stated as unanswered | PLAN §12 |
| 11 | Decisions and trade-offs | grouped link list by theme (data and time, verdict, API, frontend, AI, workflow), each item only `[D-nn](docs/decisions.md#anchor) title`, not the text (Q4) | decisions.md headings |
| 12 | Deliberately deferred, and why | from PLAN §4 "Deferred" (per-type verdicts, second tier, per-account overrides, week-to-date, tool-calling chat, account-wide banner), plus the T4 and T5 out-lists (per-location sparkline needs a backend change, D-28; caching, retries, streaming, the real-provider production checklist in PLAN §11) | PLAN §4, §11; D-28; T4/T5 plans |
| 13 | With another day | a short list drawn **only** from the sourced deferrals and open questions above, marked draft for John to rewrite (Q6) | PLAN §4, §11, §12; D-23 (account 12's 10 location flags not investigated); D-28 |
| 14 | How it was built | one paragraph: PLAN.md then a plan per ticket with an approval gate, `/plan-ticket` and `/close-ticket`, the aggregation-reviewer subagent, mutation checks, `ai-log/`; the Spec Kit line (§1d); the time note `<!-- TODO(john): hours -->` | CLAUDE.md; ai-log/README.md; notes.md |
| 15 | Repository map | six lines: `backend/`, `frontend/`, `data/` (immutable), `docs/`, `plans/`, `ai-log/` | `git ls-files` |

### 1c. `.env.example` check (done while planning, read-only)

The 16 user-facing names and where each appears:

| Group | Names | In `.env.example` | Read by | Passed by compose |
|---|---|---|---|---|
| Database | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | yes (active lines) | compose (db and URLs) | interpolated, with inline defaults |
| Report parameters | `REPORT_BASELINE_WEEKS`, `REPORT_MIN_HISTORY_WEEKS`, `REPORT_Z_MIN`, `REPORT_MIN_ABS`, `REPORT_MIN_BASELINE_MEDIAN` | yes (commented, with the defaults) | `ReportSettings` | pass-through, no default (D-18) |
| Demo account | `DEMO_ACCOUNT_ID` | yes (commented) | `Settings` | pass-through, no default |
| AI summary | `LLM_SUMMARY_ENABLED`, `SUMMARY_PROVIDER`, `ANTHROPIC_API_KEY`, `SUMMARY_MODEL`, `SUMMARY_MOCK_MODE`, `SUMMARY_TIMEOUT_SECONDS`, `SUMMARY_MAX_TOKENS` | yes (commented) | `SummarySettings` | pass-through, no default |

3 + 5 + 1 + 7 = **16**. The internal ones (`DATABASE_URL`, `TEST_DATABASE_URL`, `SEED_PATH`, `API_URL`) are set only by compose and are deliberately not in `.env.example`. One consistency gap: `make psql` hard-codes `-U relay relay`, so a changed `POSTGRES_USER` or `POSTGRES_DB` breaks it, while `.env.example` offers them as overrides (Q7). Verified by the script in check C3 at close, not only by this reading.

### 1d. The two short lines (wording from the sources, placed where they fit)

- **Spec Kit** (README §14, from `ai-log/notes.md`, T5 pre-plan entry): considered; for a 4 to 6 hour slice I kept my own minimal flow (PLAN.md, a plan per ticket with an approval gate, `/plan-ticket` and `/close-ticket`, the aggregation-reviewer, `docs/decisions.md`), so every artifact reflects a decision of mine, not a template.
- **LangChain** (README §8, from D-29): considered and not used; a single structured call with no tools or retrieval does not need it, and it would hide the validation inside the library; it would fit if the feature grew to multi-step or RAG. Linked to D-29.

### 1e. Deliberately not done

New make targets (`make demo`), a docs site, screenshots, badges, a changelog, a README test in the repo (Q8), rewriting `PLAN.md` or `docs/decisions.md` beyond what Q2 asks, the reflection, the hours.

## 2. Tests, written first

This ticket has no code, so "tests" are **verification checks run as commands before the README is called done**; they are commands and expected results, recorded as evidence at close, not files added to the repo (Q8). None of them changes shared state: the dev database is only read (`curl`, one `select`), and `make check` uses its own test databases.

Expected values, with the arithmetic:

- Selectable weeks per account: 2026-03-30 to 2026-07-20 is 112 days (03-30 to 04-30 = 31 days, to 05-31 = 62, to 06-30 = 92, to 07-20 = 112); 112 / 7 = 16 steps, so **17 weeks** (D-21).
- Complete weeks per location: 2026-02-02 to 2026-07-20 is 168 days (02-02 to 03-02 = 28, to 04-02 = 59, to 05-02 = 89, to 06-02 = 120, to 07-02 = 150, to 07-20 = 168); 168 / 7 = 24 steps, so **25 weeks** (profile TL;DR).
- Events after cleaning: 12,626 − 12 surplus duplicates = **12,614** rows in `clean_events` (profile §1, §7).
- Accounts with events: 20 − 1 (account 20) = **19**.
- Account 6 at 2026-06-01: 15 locations = 12 flagged + 3 unjudged (`too_quiet`), so 12 + 3 = 15 (D-23).
- Variables: 3 + 5 + 1 + 7 = **16** (§1c).

| # | Check | Command | Expected |
|---|---|---|---|
| C1 | every relative link and anchor in `README.md` and `ai-log/README.md` resolves | a throwaway script run from the scratchpad: for each `](path#anchor)`, the file exists and the heading slug exists | 0 broken links |
| C2 | the make targets in the README are exactly the real ones | `make help` against the README table | the same 12 names |
| C3 | the 16 variables match everywhere | a throwaway script: names in the README table, `.env.example` (commented or not), compose `environment:` and the three settings classes | the same 16 (plus the 4 internal ones only in compose and settings) |
| C4 | numbers | `make check` (counts); `curl` of `/api/report` for account 6 at 2026-06-01 (counts of `higher` and unjudged); `select count(*) from clean_events` and `from accounts` on the dev DB (read only); `curl /api/weeks` (length) | pytest and vitest counts equal the README's; 12 flagged and 3 unjudged; 12,614; 20 accounts; 17 weeks |
| C5 | the existing AI section is untouched | extract the section from `main:README.md` and from the working copy, `diff` | empty diff |
| C6 | no stale claim | `grep -nE "all 15|one command|one step|25 seed weeks" README.md ai-log/README.md` (the 25 complete weeks per location are a different, true number: write "25 complete weeks", never "25 seed weeks") | no match, or only the sentence that corrects it (C6 lists each hit) |
| C7 | scope | `git diff --exit-code main -- data/ PLAN.md CLAUDE.md backend frontend Makefile docker-compose.yml`; `git diff --name-only main` | exit 0; only `README.md`, `ai-log/README.md`, `.env.example` (if Q7), `plans/T6-*.md` (and `docs/decisions.md` if John approves Q2) |
| C8 | the gate still passes | `make check` | exit 0, counts as in C4 |
| C9 | the two lines and the placeholder exist | `grep -n "Spec Kit" README.md`, `grep -n "LangChain" README.md`, `grep -n "TODO(john): hours" README.md` | one hit each |
| C10 | the run instructions work from a clean clone | **John**, timed; the agent does not run it | John reports the time and any bug |

## 3. Make targets / commands

Nothing changes. `make check` after this ticket runs the same as now: `ruff check .` and `ruff format --check .`, `mypy` (strict), `npm run typecheck` (`tsc --noEmit`), `pytest -q`, `npm test` (`vitest run`). Last result on this branch (14:22): pytest 383 passed, vitest 104 passed, mypy "no issues found in 58 source files".

## 4. Order of work (deadline about 16:10)

1. README draft, committed to the working tree only; **John reviews it before anything else** (his instruction).
2. After that review: `.env.example` (only if Q7 is approved), the `ai-log/README.md` entry (from `ai-log/08-T5.md` and the T5 entries of `notes.md`, John reviews the wording), checks C1 to C9, plan ticks.
3. John: clean-clone run (C10), the reflection, the hours, the T4 placeholders.

## 5. Done when

- [x] `README.md` has every section of §1b, in that order or a stated better one; the AI summary section is byte-identical to `main` (C5).
  - Evidence: `grep -n "^## " README.md`: What this is, Run it, Tests and the quality gate, Configuration, Make targets, How I read DASH-247, The data, API at a glance, Stack and why (with the moved Technical choices table), AI summary: status, Key assumptions, Decisions and trade-offs, Deliberately deferred, With another day, How it was built, Repository map (the TOC at the top links them; 181 lines, under the ~250 cap). The AI section equals `main`'s except for the block John replaced: the C5 `diff` of this session shows exactly that change (the first paragraph and the `Status:` line replaced by the "early preview" quote), nothing else. The plan's "byte-identical" wording is superseded by John's instruction.
- [x] The README carries the three inherited items: the API section (T4 Q5, with PLAN §6 named as the sketch), the 17-selectable-weeks correction of PLAN §9, and the migration-1-is-an-adapted-copy line (T1, D-07).
  - Evidence: `grep -n` in `README.md`: `## API at a glance` (line 69) with "PLAN §6 is the sketch" (line 71); the 17 selectable weeks in "How I read DASH-247" and `instead of "25 seed weeks"` in "Decisions and trade-offs"; "Migration 1 is an adapted copy of `data/schema.sql`" in "The data" (line 65).
- [x] The run section works as written: `make up` then `make seed` (or what Q1 settles), URLs, what the first screen shows; the clean-clone run is **John's** (C10, evidence from him).
  - Evidence: Verified by John in this session: fresh clone, `docker compose build --no-cache`, `make up`, `make seed` ("seed loaded: 20 accounts, 12626 events"), 38 s in total, then the page opened on account 15 with Site C `higher`. The README says `make up` then `make seed`. The cold-build time in the README is a placeholder John will fill (`<!-- TODO(john): cold-build time -->`).
- [x] The facts of the brief are right: 12 of 15 flagged and 3 unjudged for account 6 at 2026-06-01, PLAN §13's "all 15" named as wrong; the seed ends 2026-07-27; 17 selectable weeks; test counts equal the last `make check` (C4, C6).
  - Evidence: This session: `curl /api/report` for account 6 at 2026-06-01 gives 15 locations, 12 flagged, 3 unjudged, account `higher` with total 880; `curl /api/weeks` (account 15) gives 17 weeks, 2026-03-30 to 2026-07-20; `curl /api/accounts` gives 20; `select count(*)` gives 12,614 on `clean_events` and 12,626 on `activity_events`; the README says "the seed ends on 2026-07-27", names PLAN §13's "all 15" as wrong (C6 grep: the only hits are the two sentences that correct it, and two in `ai-log/README.md` that say the same), and states "pytest 383 passed, vitest 104 passed", which equals this session's `make check` (383 and 104).
- [x] All 16 variables are documented, and `.env.example`, compose and the settings agree (C3); any gap fixed or listed (Q7).
  - Evidence: A script this session over the 16 names (3 + 5 + 1 + 7): every name is in `README.md`, `.env.example` and `docker-compose.yml` (0 mismatches), and every non-`POSTGRES_` name is a field of a settings class in `backend/app/settings.py` (0 missing). No gap found, so `.env.example` was not edited (Q7: the README says `make psql` assumes the database defaults).
- [x] Decisions are linked by D-number, not copied (C1); deferred items and "with another day" are present and sourced.
  - Evidence: C1 script over `README.md` and `ai-log/README.md`: 87 relative links, 0 broken, including the D-30 and D-31 anchors; the decision index links by D-number with short labels, no entry text is copied. "Deliberately deferred" and "With another day" (John's text) are present.
- [x] The Spec Kit line and the LangChain line exist where they fit; the hours placeholder `<!-- TODO(john): hours -->` is present (C9).
  - Evidence: C9 this session: `grep -c "Spec Kit" README.md` = 2 (the Process row of the table and "How it was built"); `grep -c LangChain README.md` = 1 (the LLM orchestration row, linking D-29's reasoning); `grep -n "TODO(john)" README.md` shows `<!-- TODO(john): hours -->` (line 177) and the cold-build placeholder (line 18).
- [x] `ai-log/README.md` has the `08-T5.md` entry in the others' style; the Reflection placeholder is untouched.
  - Evidence: `grep -n "^- \[08-T5" ai-log/README.md` finds the entry (line 54), written in the other entries' style from the T5 session and `notes.md`. In this ticket I only removed the "Technical choices" section (moved to the README), added that entry and changed the 05 entry's link sentence; the "## Reflection" section (John's) was not edited by me. The earlier broken link to `T2-aggregation-review.md` is gone (C1: 0 broken); the T2 reviewer run (Case C, z = −2.00, anchor A10) is in `ai-log/05-T2-review-close.md` (12 matches for `A10`).
- [x] `make check` green (C8); `git diff --exit-code main -- data/ PLAN.md CLAUDE.md backend frontend Makefile docker-compose.yml` empty; the changed-files list is as in C7.
  - Evidence: `make check` this session, exit 0: ruff "All checks passed!", "62 files already formatted", mypy "no issues found in 58 source files", pytest "383 passed", `tsc` clean, vitest "104 passed". `git diff --exit-code main -- data/ PLAN.md CLAUDE.md backend frontend Makefile docker-compose.yml .env.example` exits 0. `git diff --name-only main` lists `README.md`, `ai-log/README.md`, `docs/decisions.md` (the D-09 note, D-30 and D-31, approved by John), plus the untracked plan.
- [x] Nothing committed without John's say-so.
  - Evidence: `git log --oneline main..HEAD | wc -l` prints `0` on `feat/T6-docs-and-final-verification`; I ran no `git add`, `git commit` or `git reset` in this session, and one `git checkout -b feat/T6-docs-and-final-verification` (step 2 of plan-ticket).

## 6. Open questions

| # | Issue | Recommendation | Trade-off |
|---|---|---|---|
| Q1 | **"One command from a clean clone" is two commands.** `make up` does not seed (D-12: seed is a separate, destructive `make seed`), and the app without the seed shows the API's `account_not_found` error. Your brief and PLAN §8 say "one-command run". | Say it plainly: `make up`, then `make seed`; do not claim one command. | A `make demo` target would make it one, but it changes the Makefile (code, out of scope) and bundles a destructive reload into "start". Revisit after John's clean-clone run. |
| Q2 | **PLAN §13 and D-09 say all 15 account 6 locations flag; the seed shows 12 flagged and 3 `too_quiet` (D-23, T5 E4).** The data is not wrong: the spike does hit all 15 locations (profile §11); three are unjudged. D-09's consequence line ("will show all 15 account 6 locations flagged together") still says 15, contradicting D-23 in the same file. PLAN.md cannot be edited. | The README states the correct numbers and says PLAN §13 is wrong. Separately, John decides whether T6 also fixes D-09's one sentence (a `docs/decisions.md` edit, to be approved by him). | Fixing D-09 makes the log consistent; leaving it keeps "the log is append-only" but a reader meets two numbers. |
| Q3 | **"SQLAlchemy Core/text vs ORM": no decision with alternatives is written down.** Verified in code: `text(...)` on a `Connection`, no `sqlalchemy.orm` import; T1's plan only says "no ORM models in T1". D-01 names SQLAlchemy and nothing more. | The README states the fact and links T1; for the reason, John gives me one sentence, which goes in the README as his reasoning (not a new D-entry), or I propose a D-entry with `TODO(john)` for the alternatives. | Without his sentence I would be inventing a rationale; I won't. |
| Q4 | **Decision list shape.** 29 entries. | Group by theme with `[D-nn] title` links only (about 29 short lines), with the 8 or 10 that carry the most weight first. | Complete but long; a top-10 only is shorter but hides D-entries a reviewer may look for. |
| Q5 | **Test counts drift** (the brief wants them from the last `make check`). | State them as "at the time of writing: pytest 383, vitest 104" and re-run at close (C4, C8) so the numbers equal the last run. | Any later test change makes the README slightly stale; the command is what stays true. |
| Q6 | **"What I'd do with another day"** is John's own priority call. | I draft 5 or 6 items strictly from sourced deferrals and open questions (per-account overrides, per-location sparkline needing a backend change, the PLAN §11 production checklist, confirming PLAN §12 with the data owner, investigating account 12's flags, a direction-aware flag colour) and mark the list "draft, John to rewrite". | Quick and honest about provenance, but not yet his voice. |
| Q7 | **`make psql` assumes `relay`/`relay`**, while `.env.example` offers `POSTGRES_USER` and `POSTGRES_DB` as overrides. | No code change; add one comment line in `.env.example` ("`make psql` assumes the defaults") and one sentence in the README. | A Makefile fix (`$$POSTGRES_USER`) is code and out of scope here; the comment avoids the surprise at zero risk. |
| Q8 | **A permanent docs test** (a pytest that checks README links, targets and env names). | No: run the checks as commands and record them; the repo gate stays as it is. | A repo test would keep the docs honest after T6, but it is code, adds a test with no ticket, and the brief says no code changes. |
| Q9 | **The "~15 minutes" claim.** Only John's clean-clone run can support it (image builds, `npm ci`, pulls). | The README says "about 15 minutes on my machine, measured on a clean clone" only after John reports the time, otherwise omits the number. | A wrong number is worse than none. |
| Q10 | **Stale items in PLAN that the README must not repeat:** §9's "25 seed weeks" (17 selectable per D-21), §13's "all 15", §6's 404 and opt-in (D-29), §8's order (T5 ran before T6). | The README follows the decisions log and names the PLAN differences once, in "Decisions and trade-offs". | The PLAN stays stale by design (not edited); one sentence tells the reader which document wins. |
| Q11 | **Pending T5 entries D-30 and D-31** are in John's close checklist, not in the log yet. | The README links only entries that exist when it is written; John decides before or after T6. | If he adds them later the README gets two more links in a follow-up line. |
