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
  exactly) that became anchor A10. Report and comparison are in the session export above. Ends with /close-ticket.
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
- [08-T5.md](08-T5.md) — T5 plan, implementation and close: the optional AI summary behind a flag, an
  always-visible card with a deterministic template fallback, a mock provider that can force every
  failure, a validator for claims and a model-written headline, location ids instead of names in the
  prompt, a versioned prompt file, and (last) a real adapter. Rejected the agent's recommendation to
  accept a "valid" AI summary that was word-for-word the template, which led to the validated headline.
  Caught in review: a direction check that skipped sentences without a location token, and a word list
  that missed "dropped" and "rose". Counting flagged locations from the API instead of hard-coding them
  showed PLAN §13 was wrong (12 of 15, not all 15). The claude-api skill corrected the plan's guesses for
  the adapter (API version, thinking counting toward `max_tokens`). Mutation checks on the validator,
  the flag and the fallback reasons. My own manual run with the real model: ~1.1 s and ~2.6 s, no
  fallback, and a "largest gap" claim the validator cannot check, documented in D-29 as a limit.
- [09-T6.md](09-T6.md) — T6 docs and final verification: README, D-09 correction, 
  D-30/D-31, link check (a T2 link never committed), clean-clone run timed at 38 s.

## Reflection

**Planning with an agent front-loads decisions.** My habit is to plan at a general level and
decide details as they show up during development. Working with the agent inverted that: its
plans asked for decisions up front that I would normally take later (date cut-offs, how long a
truncated log message is, how many locations go into a prompt). That paid off where a mistake is
expensive: plan reviews caught a seed transaction that contradicted the test rollback (T1), a
parallel request that would have sent an invalid account id (T4), and a design where the "AI
summary" was word-for-word the template (T5), all before any code existed. It cost time where
nothing was at stake: the T5 plan grew to ~360 lines for about an hour of work, and some numbers
(200 characters, 5 locations) are reasonable guesses presented with the same weight as real
decisions. What I'd keep: decide up front what is expensive to change (data rules, API
contracts, trust boundaries) and let the cosmetic details be decided in the checkpoints.

**Specific moments I caught the agent wrong or overrode it:**
- Session 01: its timezone conversion used a single `AT TIME ZONE` on a naive UTC timestamp, which
  converts in the wrong direction. It is now a rule in CLAUDE.md.
- T2: rejected its "max local_week − 1" fix (it removed the injectable clock) and its existence
  rule (it would have leaked future data into the baseline).
- T4: an expected value in the plan was "confirmed at capture", i.e. taken from the fixture under
  test. Replaced with calendar arithmetic. It also proposed mocking the client module, which would
  have left the `X-Account-Id` logic untested; we stubbed global `fetch` instead.
- T4, against me: my mutation (t) was badly designed and proved nothing; the agent split it into
  two that did.
- T5: it put the prompt in code against my "versioned file" decision; its direction check skipped
  sentences without a location token; its word list missed "dropped" and "rose". Each fixed with a
  failing test first.
- T5, from the data: by counting flagged locations from the API instead of hard-coding them, the
  tests showed PLAN §13 was wrong (12 of 15 locations, not all 15).
- T5, real model run: the headline said a location had "the largest gap". The validator doesn't
  check comparatives, and the model only saw 5 of the 12. Documented as a limit in D-29 rather than
  patched, because numbers still only come from the server.

**Responsibility doesn't scale with output.** With agents I can ship thousands of lines a day,
but I'm still responsible for what every line does, and reading all of them by hand is no longer
realistic. So I put review effort where the risk is. Here that was the aggregation and timezone
logic (hand-computed fixtures, a backtest, an independent reviewer subagent with no expected
values and read-only DB access) and the LLM trust boundary (validator, fallback, mutation checks).
Styling and fixture JSON got a lighter look. In a real product the high-risk list would be money
and billing, anything that can lose users or data, legal text and security, with a human reading
those changes carefully and specialized review agents (like the aggregation-reviewer here) as a
second line, not a replacement.

**What I'd change next time:** shorter plans with explicit "decide later" items; the independent
reviewer from T1, not T2; and a clean-clone run at the end of every ticket, not only at the end.
