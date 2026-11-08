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
