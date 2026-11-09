# AI interaction log

## Tools & division of labor
- **Claude (claude.ai chat):** orientation before and around the work: breaking the
  take-home into phases, repo setup, and drafting the opening prompt for the first
  Claude Code session. Not included because that conversation mixes in unrelated
  personal topics. Product and implementation decisions are made and discussed in
  the logged Claude Code sessions.
- **Claude Code:** data profiling, planning with me, implementation, tests.
  Exported raw per session below.
- **Me:** scope and design decisions, reviewing every diff, README and reflection.

## Sessions
- [01-data-profiling.md](01-data-profiling.md) — profiling the seed data; corrected
  the agent's timezone conversion (single AT TIME ZONE on a naive UTC timestamp) and
  asked for a concrete-event check.
- [02-planning.md](02-planning.md) — drafting PLAN.md with the agent; accepted
  its future-data-leak catch, rejected loading the schema outside Alembic, trimmed
  detail down to ticket plans.
- [03-T1-scaffold-db.md](03-T1-scaffold-db.md) — T1 plan and implementation: compose,
  migrations, clean_events view, seed. Fixed two contradictions in the agent's plan
  (seed transaction vs. test rollback, round-trip test destroying the shared test DB),
  cut its custom hook for native deny rules, and independently recomputed its seed
  and timezone numbers (caught a 22 vs 21 test-count slip). Ends with the
  /close-ticket command.

## Reflection
(written at the end, based on notes.md)