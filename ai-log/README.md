# AI interaction log

## Tools & division of labor
- **Claude Code (Claude Sonnet 5.5):** data profiling, planning with me, implementation, tests, the
  aggregation-reviewer subagent. Exported raw per session below. In T4 it used the `dataviz` skill for the chart
  and the CSS colors, at its own suggestion and with my approval; it reported which rules it applied and which it
  dropped because my instructions excluded them.
- **Claude (claude.ai chat, Claude Opus 5.5):** orientation before the work (phases, repo setup, the first
  session's opening prompt). Also a second reviewer on my side: I pasted the agent's replies there and
  had it check them against the repo (read-only access to my local clone) before I answered, and it drafted the
  prompts I then edited and sent. Several T3 and T4 catches started there. It never edited the repo. That
  conversation mixes in unrelated personal topics, so it isn't exported.
- **Me:** scope and design decisions, reviewing every diff, the browser checks, README and reflection.

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
- [06-T3.md](06-T3.md) — T3 plan, implementation and close: report service behind thin
  endpoints, per-account week range, error contract, backtest (4.93 % against an 8 % ceiling
  fixed before the run, not tuned). Rejected reusing `no_activity` for an absent location (it
  would leak future data) and a misdiagnosed reviewer fix. Mutation (d) survived and exposed an
  H8 gap (H8b added). Caught: quoted curl examples that wouldn't match the permission prefix,
  DEMO_ACCOUNT_ID never reaching the container (same bug as T2's REPORT_*).
- [T3-aggregation-review.md](T3-aggregation-review.md) — reviewer derived the last complete
  week blind; ~190 endpoint values matched its SQL; two cases became anchors S15/S16.
- [07-T4.md](07-T4.md) — T4 plan, implementation and close: Vite dev server in compose behind a proxy (no CORS),
  typed client, URL state with three-stage reconciliation and a header-less bootstrap, summary, ranked table,
  location detail, chart, glossary, minimal CSS. Plan review caught a circular expected value (R11), an unchecked
  empty-DB assumption and a request-order contradiction. Caught in review: the proxy never verified, host
  `node_modules`, `@types/node` 26 vs Node 22, a 200 HTML body and `abort(reason)` uncovered by tests, effect
  dependencies left incomplete without ESLint, the UI deriving `history_weeks`. Mutation checks on every
  checkpoint; one of mine was badly designed and the agent split it. Scope changes of mine: CSS, glossary, tile
  layout, chart no longer cuttable.

## Reflection
(written at the end, based on notes.md)