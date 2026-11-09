---
description: Close a ticket. Verify, tick its plan checklist with evidence, propose decision-log entries, draft the PR description.
argument-hint: <ticket id, e.g. T2>
allowed-tools: Bash(make check), Bash(git diff:*), Bash(git status:*), Bash(git log:*), Bash(git branch:*), Bash(ls:*)
---

Close ticket **$ARGUMENTS**. If no ticket id was given, ask for one and stop.

## Hard rules

- No commits, pushes, merges or PRs. No `git add`, `git checkout`, `git reset`.
- Do not edit code, `data/`, `PLAN.md`, `CLAUDE.md` or `docs/decisions.md`.
- The only file you may edit is the plan's "Done when" checklist (step 3). The only file you may
  create is `/tmp/pr-$ARGUMENTS.md` (step 5). Ask before anything else.
- Never tick an item without evidence. Never invent rationale, results or "verified by John".

## Steps

1. **Find the plan.** Look for `plans/$ARGUMENTS-*.md`. If there is none, stop and say so.

2. **Verify.** Run `make check`, then `git diff --exit-code main -- data/ PLAN.md`.
   If either fails, stop and report the output. Do not fix anything.

3. **Tick the checklist.** In the plan's "Done when" section, for each item:
   - Tick `[x]` and add an indented `- Evidence:` line: a test name, a command and its result from
     this session, or "verified by John" **only** where John said so in this session.
   - If there is no evidence, leave it `[ ]` and add a line saying why.
   Change nothing else in the plan. Afterwards list the unticked items and the reason for each.

4. **Decision log.** Compare the ticket's changes (`git log main..HEAD`, `git diff main --stat`, the
   plan's open questions and decisions) with `docs/decisions.md`. For each design decision with real
   alternatives that has no entry, propose one in the log's format (Context, Decision, Alternatives,
   Consequences, Source). Use only what the plan, notes or this session record. Where an alternative
   or reason isn't written down, put `TODO(john)` instead of guessing. Show the proposals and wait for
   approval. Do not write them.

5. **PR description.** Write `/tmp/pr-$ARGUMENTS.md`, for `<current branch>` → `main`:
   what was built; key decisions (link `docs/decisions.md` D-numbers); verification (what was run
   and what it showed, from step 2 and the evidence in step 3); notes a reviewer might trip over
   (deviations from the plan, known limits); what is left for later tickets. Link the plan. End with
   the PR attribution line the session instructions specify, if any.

6. **Stop with John's checklist.** Print this list. Do not do any of it yourself:
   - [ ] Run `/export` to `ai-log/NN-$ARGUMENTS.md` (NN = next number after the highest in `ai-log/`)
   - [ ] Update `ai-log/README.md`
   - [ ] Write your `ai-log/notes.md` entry
   - [ ] Approve and add any proposed `docs/decisions.md` entries
   - [ ] Commit
   - [ ] Push
   - [ ] Open the PR with `/tmp/pr-$ARGUMENTS.md`
   - [ ] Merge with a merge commit (no squash)
