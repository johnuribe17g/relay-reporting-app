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
- [04-T2-backend-core.md](04-T2-backend-core.md) — T2 plan and implementation: pure domain
  logic (median/MAD, verdict, ranking, week arithmetic), ReportSettings, zero-filled series SQL,
  seed anchors. Rejected the agent's "max local_week − 1" fix (it dropped the injectable clock)
  and its existence-rule "gap" (it would leak future data). Asked for an explicit self-check that
  found a false data claim in the plan, mutation checks on judge and the SQL (the HAVING guard
  turned out redundant), and caught REPORT_* overrides that never reached the container.
- [05-T2-review-close.md](05-T2-review-close.md) — independent review and close in a fresh
  session: built and ran the aggregation-reviewer subagent (no expected values, read-only DB,
  every query approved by hand). It matched A1 and found a real-data boundary case (z = −2.0
  exactly) that became anchor A10. Report and comparison in
  [T2-aggregation-review.md](T2-aggregation-review.md). Ends with /close-ticket.

## Reflection
(written at the end, based on notes.md)