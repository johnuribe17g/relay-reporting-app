---
description: Plan a ticket. Create its branch and write plans/<ticket>-<slug>.md as a DRAFT for approval. No code.
argument-hint: <ticket id, e.g. T2>
allowed-tools: Bash(git status:*), Bash(git fetch:*), Bash(git rev-parse:*), Bash(git log:*), Bash(ls:*)
---

Plan ticket **$ARGUMENTS**. If no ticket id was given, ask for one and stop.

## Hard rules

- Write no application code, config files, migrations or tests, and make no commits.
- Never edit `PLAN.md` or `data/`. If `PLAN.md` looks wrong or underspecified for this ticket,
  say so in the plan's open questions. Don't work around it silently.
- The only changes you may make are creating the branch (step 2) and writing the plan file (step 4).
- Never invent data facts or numbers. Take them from `docs/data-profile.md` or compute them.

## Steps

1. **Check the starting point.** Run `git status` and `git fetch`. Stop and say so if the working tree
   is not clean, the current branch is not `main`, or `main` differs from `origin/main`.
   Also stop if `plans/$ARGUMENTS-*.md` already exists.

2. **Create the branch** `feat/$ARGUMENTS-<slug>`. The slug is the ticket's title in `PLAN.md` §8,
   lowercased and hyphenated (e.g. "Scaffold + DB" → `scaffold-db`).

3. **Read, in full:** `CLAUDE.md`; `PLAN.md` (this ticket's scope in §8, plus every section it touches);
   `docs/decisions.md`; `docs/data-profile.md`; every earlier plan in `plans/`, including what they
   leave for this ticket (e.g. T1's Q9 for T2). Skim the existing code the ticket builds on.

4. **Write `plans/$ARGUMENTS-<slug>.md`** in the structure of the approved T1 plan, concise:
   - **Header:** `Status: DRAFT, awaiting approval`, source sections, branch name.
   - **In / out of scope**, from `PLAN.md` §8 and the items earlier plans left for this ticket.
   - **Design:** files to create or change, interfaces, SQL or algorithms, what is deliberately not done.
   - **Tests, written first:** a table of cases with tiny hand-computed fixtures (input → expected
     output). Show the arithmetic for every computed value (timestamp conversions, medians, MAD,
     z-scores), so it can be verified by hand. Say which tests share state and how it is isolated.
   - **Make targets / commands:** what changes, and exactly what `make check` runs afterwards.
   - **Done when:** a checklist where each item can be backed by a test, a command or a stated
     verification (this is what `/close-ticket` ticks).
   - **Open questions:** numbered; each with your recommendation and the trade-off. Include anything
     in `PLAN.md` or earlier plans that looks wrong or underspecified for this ticket.

5. **Self-check the draft** before finishing, and fix what you find:
   - Contradictions between sections (e.g. one section says a function owns its transaction, another
     says the caller does).
   - Tests that destroy or depend on shared state (a migration down, a TRUNCATE on a database other
     tests use).
   - Anything that edits `PLAN.md` or `data/`.
   - Numbers or claims not backed by the data profile or a computation you did.
   - Fixtures whose arithmetic doesn't reproduce when you redo it.

6. **Stop and wait for approval.** Do not start implementing. End with a short summary of the
   plan's open questions and this suggested commit message:
   `docs(plans): add $ARGUMENTS plan`
