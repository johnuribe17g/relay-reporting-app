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
