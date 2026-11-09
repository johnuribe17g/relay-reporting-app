# Working notes

Running notes written as I go: my reasoning, decisions, and moments where I
corrected or overrode the agent. Raw and unpolished on purpose.

## 2026-11-08 — Approach

How I intend to work on DASH-247:

1. **Understand the business and the data first.** Before planning anything, I
   want a clear picture in my head of what the final result should look like.
   That means profiling the seed data (session 01) and understanding what
   "normal" can realistically mean with this data.
2. **High-level plan, split into tickets.** A PLAN.md with only what I already
   know will be needed, without detail. Roughly:
   DB (migrations, seed load, cleaning layer) → backend tickets (aggregation,
   API) → frontend tickets (dashboard, detail view, URL state).
3. **A detailed plan per ticket, just in time.** Before starting each ticket, a
   short planning session with the agent that produces a mini-plan. I commit it
   before the code, so the history shows plan → implementation for each ticket.
4. **AI feature last, behind a flag.** An experimental LLM summary, off by
   default and opt-in per request. Only after the core is correct and verified,
   and time-boxed. If there's no time left, the design stays in PLAN.md.

Workflow: one branch and one Claude Code session per ticket, an export of each
session committed to ai-log/, and merge commits only (no squash).

## 2026-11-08 — Session 01 (data profiling)

- Agent proposed `occurred_at AT TIME ZONE tz` on a naive UTC timestamp. That
  converts in the wrong direction. Corrected it to the double conversion and
  asked for a check against one concrete event.
- Re-ran exact-duplicate and account-6 weekly queries myself in pgAdmin: matches 
  the profile.

## 2026-11-08 — Approach addendum: agent tooling

Agent tooling grows with the project. I don't set up subagents, skills or hooks
upfront. When a step in the workflow repeats, or the agent makes the same kind of
mistake twice, I turn it into a rule (CLAUDE.md), a command, a hook or a subagent.
Each one should trace back to a concrete need in this project.

First instance: CLAUDE.md, motivated by the timezone conversion mistake in session 01.

## 2026-11-08 — Session 02 (planning)

- I gave the agent my decisions upfront and asked it to challenge them, plus give options
  only for what was still open (baseline window, verdict rule, metrics, minimum history,
  AI feature shape).
- Accepted: baseline must use only weeks *before* the selected week. Otherwise the
  week selector leaks future data into older weeks. A good catch I had missed.
- Accepted: rank locations by a standardized score, not raw difference, so small
  locations aren't buried and a 2-event wobble doesn't top the list.
- Rejected: the agent proposed Alembic create only the view and load schema.sql
  directly via docker-compose. That breaks the brief (real schema + migrations) and
  the starter README (put the schema in your own migrations). Migration 1 now creates
  the tables.
- Deferred instead of building: account-wide banner, chart-axis handling, second
  verdict tier. The plan was getting too detailed. Parameter values and UI states
  belong in the per-ticket plans.
- Added: statistical parameters as typed config (pydantic-settings, env overrides).
  Tuning the statistics isn't the focus of this exercise, but changing them later
  should be trivial.
- Reviewing the draft, I found two gaps: no ticket owned the scaffold / `make check`
  gate, and no ticket covered README + clean-clone verification. Added both (T1 scope,
  new T6). T6 is prioritized over the AI ticket.
- The agent flagged it hadn't read seed.sql. I confirmed it has only INSERTs (no DDL),
  so there's no conflict with migration 1.

## 2026-11-08 — Before T1: run path and planned agent tooling

- Decided: the whole app runs via docker-compose from T1, not just the DB. `make up`
  (db + api, migrations on startup), `make seed` (idempotent), `make check` (lint,
  typecheck, tests inside the api container). A reviewer only needs Docker and make.
  Reason: the brief's "~15 min local run" gets exercised on every ticket instead of
  being discovered broken in T6.
- Planned agent tooling, each tied to a trigger (per the tooling principle above).
  I'll mark each one when it's actually built and what triggered it:

  | Tool                                                                                                                  | Trigger                                                                          | Status                      |
  | --------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | --------------------------- |
  | `/plan-ticket` command: creates the ticket branch, writes `plans/Tn-*.md` with the T1 structure, stops for approval   | T1 plan approved (it becomes the template); first use in T2                      | built at T1 close           |
  | PreToolUse hook blocking writes to `data/`                                                                            | T1 touches seed and migrations, so the CLAUDE.md rule becomes a guarantee now    | planned, in T1 plan         |
  | Hook protecting already-applied migrations                                                                            | First migration merged to main                                                   | replaced by deny rules (T1) |
  | Aggregation reviewer subagent: clean context, recomputes a few cases by hand, compares with the query/endpoint output | Baseline SQL exists (T2/T3), so the work doesn't grade itself                    | built at T2 close           |
  | `/close-ticket` command: verifies, ticks the plan checklist, drafts the PR description, lists my steps                | Closing T1 by hand made the steps concrete; built then instead of waiting for T2 | built after T1              |

- Not building tooling upfront on purpose: a command derived from a plan that already
  worked is better than one designed in the abstract.

## 2026-11-08 — T1 skeleton review and deny-rule check

- Ran `make reset && make up`, the health check and `make check` on my machine: all green.
- Dropped the custom hook script the agent planned (Python script + ~12 unit tests) for
  native `permissions.deny` rules: too much for the time budget, given the ro mount and
  the `git diff` check already exist.
- Tested the deny rules in a fresh session. First attempt: the agent refused on its own,
  citing CLAUDE.md, so the permission layer was never exercised. Second attempt, with
  an explicit override: the Edit tool returned "File is in a directory that is denied by
  your permission settings". Reads still work. Two separate layers: the instruction the
  agent chooses to follow, and the rule the harness enforces.
- Asked the agent to lint migrations (it had excluded migrations/versions from ruff) and
  to publish the api port on 127.0.0.1 only.
- Verified the migrated table with \d in psql: matches schema.sql (no default on id, 
  named constraints, composite index).
- Migration 1 reviewed: tests written first (5 red → green). Agent caught SQLAlchemy's
  implicit SERIAL on integer PKs (autoincrement=False) and fixed its own faithfulness
  query instead of loosening the test. Verified the table with \d in psql.

## 2026-11-08 — T1 close

- Clean-clone check, run by me: dropped the shared DB volume first (compose project
  name is fixed, so a second clone would reuse it), fresh clone into /tmp, no .env,
  `make up && make seed && make check`: green in 2 seconds. Health returned 200.
- Agent's closing checklist left one item open on purpose: CLAUDE.md still said
  "Stack (planned)". It flagged it instead of ticking it or editing CLAUDE.md
  unasked. Approved the one-line fix.
- Accepted one gap: the week-changer test checks the clean view only, not raw rows.
  The view is what the app reads.
- The agent corrected its own earlier report (22 → 21 timezone cases) after my
  independent recount.
- Built /close-ticket now instead of waiting for T2 as the tooling table said: the
  steps were already concrete from closing T1 by hand, and every remaining ticket
  repeats them. The command verifies, ticks the plan checklist with evidence, drafts
  the PR description, and lists what stays mine (export, notes, commit, PR, merge).
  It never commits or pushes. First real use: T2.
- Also built /plan-ticket now, from the approved T1 plan. It creates the ticket branch,
  writes the plan in T1's structure, and self-checks for the two mistakes I caught in
  T1's plan review (contradictions between sections, tests destroying shared state)
  before stopping for approval. First use: T2, right after merging T1.

## 2026-11-08 — T2 planning

- My context message ended with "go ahead with /plan-ticket T2"; the agent took that as the
  instruction and invoked the command itself. End state was correct (branch from clean main,
  plan file only).
- The command's step-5 self-check didn't hold up on the first pass. Asking for it explicitly
  found problems in 4 of 5 checks: section contradictions, test IDs clashing with question IDs,
  a missing ValueError for non-Monday weeks, and a false data claim (the "zero weeks inside the
  baseline" for 3 locations; only Site G's is). Lesson: a self-check bundled into the same
  generation step is weak. Run it as a separate step, or give it to the reviewer subagent.
- Seeding the dev DB went beyond the command's allowed changes; I approved it 
  explicitly.
- Recomputed A1, A2, A4 in psql with percentile_cont (independent of the Python code): 
  matches the tests
- Pre-plan context: the agent challenged my decision 5 (complete week in account-local time vs
  "no timezone logic in T2"). It was right that my wording was too broad, but its fix ("max
  local_week minus one") dropped the injectable clock (D-03) and assumed the last week is always
  partial. Rejected; went with a pure last_complete_week(as_of_utc, tz) using zoneinfo.
- Also rejected its "gap" in the existence rule: listing a location with no events up to W as
  unjudged would leak future data. Locations exist only through events.

## 2026-11-08 — T2 implementation

- Batch 1 (pure domain + settings): red runs were against NotImplementedError stubs, which only
  prove the tests run. Asked for a mutation check: flipping >= / < in judge broke the boundary
  rows (V1, V5, V7, V10) each time.
- Caught a bug no test could see: the REPORT_* overrides documented in .env.example never reached
  the app (compose didn't pass them; ReportSettings doesn't read .env). Tests passed because they
  use monkeypatch in-process. Approved a deviation: pass-through in compose with no defaults,
  verified end to end (no var → defaults, .env → override, shell var → override).
- Batch 2 (series SQL): mutation check on the SQL. Removing the HAVING future-data guard broke
  nothing: an empty generate_series range already excludes those locations. My expectation was
  wrong; kept the HAVING as an explicit rule with a comment.
- Committed after each checkpoint so later diffs on domain code would be meaningful (the agent
  pointed out that git diff on untracked files proves nothing).

## 2026-11-08 — T2 independent review

- Built the aggregation-reviewer subagent (tooling table trigger: baseline SQL exists). No
  expected values in its prompt; DB read-only via PGOPTIONS; I approved each query by hand. The
  main agent's task to it was fixed to "Run your review as defined in your instructions" so it
  couldn't leak numbers.
- /list-agents showed nothing and I almost changed the frontmatter. It lists running subagents,
  not defined ones; the agent was loaded all along.
- Results: case A (account 6, 2026-06-01) matches the tests and my psql recompute exactly. Case B
  (6 Site G) matched the plan's arithmetic but no test executed it. Case C (9 Site B, 05-04) is a
  real-data boundary: z = -2.0 exactly. Added B and C as anchors A9/A10; the code agreed with every
  value.
- Its "deviations" were decisions already in the T2 plan (too_quiet, precedence, band, Sunday
  23:59:59), which it can't read. One stands as a known limit: local-week logic exists twice
  (the view's SQL and zoneinfo in weeks.py) and could diverge; they agree on the seed (A5).
- Weak spot: its last-complete-week check isn't blind, because PLAN §2 states 2026-07-20 and it
  didn't flag that.

## 2026-11-09 — T3 pre-plan context

- Gave the agent my T3 decisions upfront (thin endpoints over a shared service module, so the
  backtest tests the code the API serves; X-Account-Id with a demo default; injectable as-of;
  GET /api/accounts as a gap in PLAN §6; one band in the history chart; backtest ceiling fixed
  before the first run) and asked it to challenge them. It kept all nine.
- Rejected: a location absent at W returning 200 `no_activity`. In T2, `no_activity` means
  "account has no events at all" (precedence 1). Reusing it would change what the verdict means,
  and a 200 for a location that only starts after W leaks future data. It's 404, per the T2
  existence rule.
- Caught a misdiagnosis: it proposed "replacing the hardcoded 2026-07-20" in aggregation-reviewer.md.
  There is no hardcoded date there; the reviewer gets it from PLAN §2, which it must read. Asked
  it to check the file. The real fix: the reviewer derives each account's last complete week from
  max(occurred_at) in the account's timezone and treats any week date in PLAN as unverified.
- Caught a contradiction: "judgeable weeks only" plus "early weeks return not_enough_history if
  asked by date" conflicted with my 422-outside-range decision. Made it pick one (422) and define
  account 20 and late-starting accounts exactly (weeks=[], default_week=null, 200 no_activity /
  not_enough_history), with no "or".
- Test isolation: asked it to read conftest.py before proposing "seed relay_test once per
  session". It found its own proposal would collide with the TRUNCATEs in the seed tests, and
  switched to the test_seed_anchors.py pattern (module-scoped seeded connection, rolled back).
  Same class of mistake I caught in T1's plan; this time it caught it itself once pointed at the code.
- Kept the Vite proxy target out of T3: it depends on how T4 runs the frontend.
- To check in the draft: first judgeable week is 2026-03-30 (T2 anchor A4), what `week` holds in
  the report when default_week is null, and get_conn listed as a new dependency (health keeps the engine).
- Used claude.ai chat to review the agent's pre-plan replies against the repo before answering.

## 2026-11-09 — T3 implementation
- CP3 mutations: (d) survived. My expectation was wrong: H8 uses Site A, which exists at 02-09,
  so the order of the week and location checks can't matter for it. The agent explained why and
  added H8b (Late, absent and not selectable → 422). Same lesson as the T2 HAVING check.
- (a) exposed that the exists-at-W rule is enforced twice (fetch_series omits the location,
  build_history turns that into a 404). Kept both.
- Verified B2's 3 unjudged locations independently in psql (account 6, baseline 03-09 … 05-25):
  medians Site C 3.0, Site H 3.5, Site O 3.5, all below min_baseline_median 4 → too_quiet is
  right. At 07-20 only Site M is too_quiet because the window is different.
- Checked account 12 (10 of 55 location flags, all higher) in psql: account totals are flat
  (32–68, no direction), so I ruled out "trend lag" before letting it into D-23. Cause at
  location level left uninvestigated and said so.
- D-23 cross-check: account 6's flag at 06-08 was already in the data profile (§11, 102 vs 76),
  written before any code.
- Reviewer edit: caught that the quoted curl examples wouldn’t match the prefix permission, so every report/history call would have prompted. Switched to -G -d with an unquoted URL.”
- T3 review: the reviewer derived the last complete week blind (all 6 zones → 2026-07-20) and
  checked PLAN's dates against the data. That fixes the T2 weak spot. ~190 endpoint values
  matched its SQL. I recomputed its two new cases by hand (Site N z −1.0117 at the min_abs
  boundary, Site G z 17.705); both added as anchors.
- Gap: series.py wasn't in its allowed reads (in T2 either), so zero-fill was checked through
  outputs only. Added for next time.
- For T4: band_low can be negative (Site G −1.43); clip at 0 when drawing it.
- Agent found that DEMO_ACCOUNT_ID never reached the container, the same bug as T2’s REPORT_*. It recorded it instead of fixing it outside the plan’s scope. I approved the fix in T3, verified end to end.

## 2026-11-09 — T3 close

- /close-ticket: 10/11 ticked by the agent. It left the reviewer item for me because I hadn't
  said I compared. I had (Site N/G by hand, B2 in psql) and ticked it with that evidence.
- Decision log: rejected a D-24 for a field name (folded into D-16) and a D-27 for things
  already in plan Q7/Q10. Filled the agent's TODO(john) gaps in D-24/D-25 with my actual reasons
  instead of letting it invent them.
- T3 numbers: 274 tests, backtest 4.93 % (8 % ceiling, not tuned), reviewer ~190 values matched.

## 2026-11-09 — T4 pre-plan context

- Gave the agent my T4 decisions upfront (Vite dev server in compose, no state/router/fetch libraries, URL state,
  no recomputation in the UI, hand-rolled SVG, global fetch stub, close verification) and asked it to challenge them.
- It found cases my message missed: no `?account` at all (nothing exposes the server's demo default, and
  hard-coding 15 would duplicate D-22), an account with events but no judgeable week, late responses overwriting
  a newer account, the band clipped in the text and not only in the chart, and `new Date('2026-07-20')` rendering
  as the 19th in US time zones.
- Its proposal to mock the client module would have left the X-Account-Id logic untested. Agreed to stub global
  fetch instead and keep the real client.
- Decided: header-less bootstrap (adopt `account.id` from /api/weeks), unknown account = error state with no
  fallback, no ESLint, no auto-select of a location.
- Rejected a D-28 for hand-written types and the mock boundary: plan open questions, not ADRs (same call as in T3).
- Asked for checkpoints with an explicit cut order, given the time left.

## 2026-11-09 — T4 plan review

- R11's expected row count was "confirmed at capture": the expected value came from the fixture under test.
  Replaced with the calendar arithmetic (07-20 minus 12 weeks = 04-27, after 02-02, so 12 + 1 = 13).
- The empty-DB case assumed a 404 without checking. Made it a CP1a probe that records the real status and body.
- CP1 was one huge diff (run path + client + URL logic + App + docs). Split into CP1a (run path only) and CP1b.
- After my D-27 edit, the plan said /api/accounts and /api/weeks "start together". That breaks A3: with
  `?account=999` a parallel weeks call would carry the bad id. Fixed before committing the plan: parallel only
  without an account param. The /plan-ticket self-check missed it, same as T2.

## 2026-11-09 — T4 CP1a (run path)

- The agent reported "make check green" and the versions, but had not checked the proxy, which is the whole point
  of D-26. Asked for curl through :5173: /api/health 200, and /api/weeks with X-Account-Id: 6 returned account 6,
  so the header passes through.
- `frontend/node_modules` existed on the host, contradicting the plan. Two causes: `npm install
  --package-lock-only` on the bind mount wrote `.package-lock.json`, and Docker recreates the empty mount point of
  the anonymous volume. The lockfile is now generated in a throwaway copy; the plan sentence was corrected.
- `@types/node` came in at 26 against the node:22 image. Pinned to ^22.
- Empty-DB probe (before seeding): /api/accounts 200 `[]`, /api/weeks 404 `account_not_found`. No 500.
- The agent found that `up -V` leaves the replaced anonymous volumes behind. Accepted as a known limit: the obvious
  fix (`docker volume prune` in the Makefile) would delete other projects' volumes.
- Checked the fixtures myself against the T3 anchors (Site C z 2.7716, band 0.8096–10.1904; Site G band_low
  −1.4304; Site M too_quiet). HMR works on the macOS bind mount.

## 2026-11-09 — T4 CP1b (client, URL logic, shell)

- Stop point 1: mutations (a)–(e) all caught. (b) was caught only by the "015" case in RA3, which justifies having
  it there.
- Reviewing client.ts I found two cases no test covered: a 200 with an HTML body (Vite serves index.html for /api/*
  if the proxy is off) threw a raw SyntaxError instead of an ApiError, and abort detection relied on the error type,
  so `abort(reason)` would have shown a false network error. Added K9/K10; abort is now decided by
  `signal.aborted`.
- The agent then found that the old `instanceof DOMException` check already failed under jsdom (jsdom's and Node's
  DOMException are different classes).
- Committed stop point 1 separately so the fixes show up as their own diff (same reasoning as T2).
- Stop point 2: mutations (f)–(i) caught.
- Q3's mitigation for skipping ESLint said effects outside useAsync would stay trivial. App.tsx had two non-trivial
  effects with incomplete dependency lists. Completed them (results memoized); same request counts in A1–A10. That
  is the concrete cost of skipping ESLint.
- StrictMode off: corrected the agent's reason. The cost of enabling it is only a duplicate aborted request in dev;
  what we lose is its check for effects without cleanup.

## 2026-11-09 — T4 CP2, CP3a, CP3b

- CP2: mutations (j)–(m) caught. The agent tightened a selector in an approved test (`/^account/i` also matched the
  new "Account summary" region); no assertion changed. Accepted.
- CP3a: the detail derived `history_weeks` as `weeks.length - 1`. Correct today, but it is the UI computing what the
  API already gives in the report row. Changed to use the row; test added for a not_enough_history clone.
- CP3a: when R11 failed on a copy change, the agent reworded the copy, not the test.
- CP3b: my mutation (t) was badly designed. As written, the chart clipped by itself, so the chart tests stayed green
  and proved nothing. The agent split it: (t1) shows nothing; (t2) only displayBand stops clipping and C1 fails,
  which proves the chart depends on it.
- dataviz skill: the agent proposed it in the pre-plan; I approved it for CP3b and asked for a report of what it
  applied and what it didn't. Applied: one series with no legend, mark specs, the band as a wash, selective labels,
  validated palette. Not applied, following my rules over the skill: hover layer, gridlines, dark mode. It read
  only part of the skill's files and said which, and it did not look at the rendered chart; I checked it in the
  browser.

## 2026-11-09 — T4 scope changes (mine)

- Plain CSS in T4 (CP3c), against the plan's "Out: styling work". One styles.css, no Tailwind: one screen, and
  Tailwind adds a dependency, config and a lockfile change for no second use.
- A glossary (`<details>`), every number taken from `report.parameters`, never a literal; the same definitions as
  `title` on the table headers. Many admins won't know what a z-score or a median is.
- The chart is no longer a cut item. A chart of 13 weeks against the band shows outliers and streaks far better
  than the numbers alone.
- Metrics as horizontal tiles, the glossary above the location table. The only markup change allowed for styling:
  `<div>` wrappers around `<dt>/<dd>` pairs.
- Native `<title>` on chart points instead of a JS tooltip layer; yMax rounded up to a whole number.
- Considered a per-row sparkline in the location table; deferred, since /api/report has no per-location series
  (backend change or 15 extra requests).
- Used claude.ai chat to review each agent reply against the repo before answering, as in T3.

## 2026-11-09 — T4 close

- /close-ticket ticked 9 of 10. It left my browser verification unticked because I hadn't reported it in that
  session, and it flagged that it could not confirm I made two of the commits (3991b1d, dc45091) because I didn't
  say so there. Both are mine.
- Decision log: added D-28 (presentation). No other entries: abort-by-signal and the effect dependencies are
  implementation fixes, recorded in the plan's deviations.

## 2026-11-09 — T5 pre-plan context

- Order change: T5 before T6, against PLAN §8 ("6, then 5"). PLAN.md not edited; recorded as a
  deviation in plans/T5-ai-summary.md with a time box and a cut rule (stop at the last green state).
- Decided before the plan: a card under the account summary with a button (no chat); "AI summary"
  vs "Template summary" label with the reason; POST /api/summary with the account from the header;
  the model returns structured claims with no numbers and the server renders the figures; validator
  plus deterministic fallback; mock provider only, real adapter if time remains; prompt as a
  versioned file.
- Flag off by default, but the card is always visible: with the flag off it returns the template
  with reason "disabled" instead of PLAN §6's 404, so the demo works without configuration.
- The label must say "mock provider" when the mock answers: presenting deterministic output as a
  model's would be misleading. Framed as a preview, not production-ready (PLAN §11 lists what's missing).
- Considered Spec Kit. For a 4–6 h slice I kept my own minimal flow (PLAN.md, a plan per ticket with
  an approval gate, /plan-ticket and /close-ticket, the aggregation-reviewer, decisions.md), so every
  artifact reflects a decision of mine, not a template.

## 2026-11-09 — T5 plan review (rev. 1 → rev. 3) and S1

- Rev. 1, Q1: with near-enum claims, a completeness rule and server-rendered text, a valid "AI
  summary" was word-for-word the template; the model only ordered lines. My own decision 4 caused
  it. Rejected the agent's recommendation to accept it (a gratuitous model call). Added a
  model-written headline, validated on the server: ≤ 200 chars, no digits, locations only as
  [L1]..[L5] tokens, a direction-word check against the verdicts. Fact lines unchanged.
- Q8: location ids instead of names. Names are never sent to the model, so injection through
  location names is removed rather than mitigated; the <data> escaping is now just hygiene.
- The agent put the prompt in prompt.py, against my "versioned file" decision. Moved to
  prompts/summary-v1.md, version taken from the file name.
- Added reason nothing_to_summarize (week null): no provider call, no cost for an empty account.
- Rev. 2 gap: the direction check skipped sentences without a token, so "The whole account is
  lower" passed for a higher account. Added the account check (H13).
- Time box extended by me, no pre-cuts; restored U7 (the card's only error-path UI test).
- S1 review: the lexicon missed common verbs ("[L1] dropped" passed for a higher location).
  Extended it and made the prompt use only "higher/lower than usual". The agent's time log called
  `date` a lower bound; wrong, the file mtimes agree, caveat removed.
- Considered LangChain (familiar ecosystem). Not used: one structured call with no tools, retrieval
  or retries doesn't need it, and it would hide the validation inside the library, which is the
  part under review. It would fit if the feature grew to multi-step or RAG (LangGraph, with
  LangSmith for tracing and evals).
- Used claude.ai chat to review each agent reply and the code against the repo before answering.

## 2026-11-09 — T5 S2

- S2 approved; the S11 deviation accepted (anthropic + key → mock until S6). In review: log truncation, a single SummaryReason type.
- S3: PLAN §13 says all 15 of account 6’s locations flag on 2026-06-01; the seed says 12. Tests count from /api/report instead of hard-coding it; PLAN.md left as written, README will say 12.
