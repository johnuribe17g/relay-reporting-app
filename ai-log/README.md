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
  the agent's timezone conversion (single AT TIME ZONE on a naive UTC timestamp) and asked for a concrete-event check.
- [02-planning.md](02-planning.md) — drafting PLAN.md with the agent; accepted 
  its future-data-leak catch, rejected loading the schema outside Alembic, trimmed detail down to ticket plans.

## Reflection
(written at the end, based on notes.md)