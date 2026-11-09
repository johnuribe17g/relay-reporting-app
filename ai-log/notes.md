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

  | Tool | Trigger | Status |
  |---|---|---|
  | `/plan-ticket` command: creates the ticket branch, writes `plans/Tn-*.md` with the T1 structure, stops for approval | T1 plan approved (it becomes the template); first use in T2 | planned |
  | PreToolUse hook blocking writes to `data/` | T1 touches seed and migrations, so the CLAUDE.md rule becomes a guarantee now | planned, in T1 plan |
  | Hook protecting already-applied migrations | First migration merged to main | later |
  | Aggregation reviewer subagent: clean context, recomputes a few cases by hand, compares with the query/endpoint output | Baseline SQL exists (T2/T3), so the work doesn't grade itself | later |
  | `/close-ticket` command: export reminder, notes.md line, PR description | Only if T2's closing repeats T1's steps | conditional |

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
