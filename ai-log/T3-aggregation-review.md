# T3: aggregation-reviewer run (endpoint review)

Run at T3 close, 2026-11-09, on the dev database (20 accounts, 12,614 clean events) with the api container serving
the T3 working tree. The subagent was launched with exactly the task "Run your review as defined in your
instructions." and nothing else. It had no expected values, did not read `backend/tests/`, `plans/`,
`docs/decisions.md` or `ai-log/`, and compared its own recompute with `GET /api/weeks`, `/api/report` and
`/api/locations/{location}/history`. Nothing was approved on its behalf.

Format note: unlike `05-T2-review-close.md`, this is not a terminal export. It holds the subagent's final report
verbatim (part 1), then the comparison against the tests (part 2). The session export, if wanted, is John's to add.

---

## Part 1: the reviewer's report (verbatim)

## Review report

I recomputed three cases from `clean_events`, read the domain code and the API mapping against PLAN §2 and §6, and compared my numbers with the running API. There is no numeric mismatch. I did not touch `backend/tests/`, `plans/`, `docs/decisions.md` or `ai-log/`, and I saw no expected values anywhere I was not allowed to read.

### 1. Recomputed cases

Parameters, from the defaults in `backend/app/settings.py`: baseline_weeks=12, min_history_weeks=8, z_min=2.0, min_abs=3.0, min_baseline_median=4.0. The last one is not in PLAN §2, so that rule comes from the code and settings.

| Case | Weekly series used (oldest to newest) | x | Median | MAD | Spread | z | Verdict |
|---|---|---|---|---|---|---|---|
| 1. Account 6 (America/New_York), account level, week 2026-06-01 | Mar 9 to May 25: 84,81,71,82,76,55,64,86,68,78,62,53 | 880 | 73.5 | 9 | 13.3434 (1.4826·9; √73.5=8.573) | 60.442 (diff 806.5) | higher |
| 2a. Account 6, Site N, week 2026-04-27 | Feb 2 to Apr 20: 6,4,8,0,8,8,5,6,3,8,1,8 | 3 | 6 | 2 | 2.9652 (√6=2.449) | -1.0117 (diff -3) | normal |
| 2b. Account 6, Site G, week 2026-06-01 | Mar 9 to May 25: 3,5,7,8,2,0,2,6,4,3,7,5 | 57 | 4.5 | 2 | 2.9652 | 17.705 (diff 52.5) | higher |

- **Why I chose 2a:** it has a zero week (Feb 23) inside its own baseline, and |diff| is exactly 3, which sits on the min_abs boundary. |z| is far below 2, so it is normal.
- **Why I chose 2b:** it is a location during the account 6 spike, and it also has a zero week in its baseline (Apr 13).
- **Even-count median:** I used `percentile_cont(0.5)` for the median and for the median of the absolute deviations. For an even count it averages the two middle values, which is the rule.
- **Other event types:** `clean_events` holds only call_received, lead_created and appointment_set. I saw 0 events of any other type in the weeks I used.
- **Account 6 weekly totals around the spike:** May 25 was 53, Jun 1 was 880 and Jun 8 was 102.

Expected location order for the account 6 report on 2026-06-01, from my own SQL:
- **Judged, by |z| descending:** D 30.88, N 30.35, L 27.73, F 27.43, K 24.60, M 23.0, J 21.53, I 21.5, E 21.11, B 20.57, G 17.71, A 14.84.
- **Unjudged (too_quiet because the baseline median is below 4):** C (median 3), H (3.5) and O (3.5), after the judged ones. I ordered these by name, which is a code rule.

### 2. First and last complete week per account

The data start is 2026-02-01 10:57:44 UTC, a Sunday. The as-of is 2026-07-27 22:20:34 UTC, a Monday. Both are `max`/`min(occurred_at)` over `clean_events`, with all accounts together.

I converted both to local time with `(ts AT TIME ZONE 'UTC') AT TIME ZONE tz`:
- **Data start:** it is a Sunday in every account's zone, so that week is partial. The first complete week is therefore Monday 2026-02-02.
- **As-of:** it is a Monday in every zone, so the last complete week is 2026-07-20, which ended on 2026-07-27 00:00 local.

| Account | Time zone | First complete week | Last complete week | How you derived them |
|---|---|---|---|---|
| 1, 4, 8, 10, 13, 16 | America/Chicago | 2026-02-02 | 2026-07-20 | Local start 2026-02-01 04:57 and local as-of 2026-07-27 17:20, then the rule above |
| 2, 6, 11, 14, 19 | America/New_York | 2026-02-02 | 2026-07-20 | Local start 05:57 on Feb 1, local as-of 18:20 on Jul 27 |
| 3, 9 | America/Denver | 2026-02-02 | 2026-07-20 | Local start 03:57, local as-of 16:20 |
| 5, 12, 17, 20 | America/Los_Angeles | 2026-02-02 | 2026-07-20 | Local start 02:57, local as-of 15:20 |
| 7, 15 | America/Phoenix | 2026-02-02 | 2026-07-20 | Local start 03:57, local as-of 15:20 |
| 18 | UTC | 2026-02-02 | 2026-07-20 | Local start 10:57, local as-of 22:20 |

Account 20 has no events but still gets these bounds, because they come from the global data. The API returns an empty selectable list for it (section 4).

I wrote the per-account local conversions out in SQL, not by hand, and all 20 rows came out the same.

### 3. Deviations in `backend/app/domain/` and the API mapping

None of these changes a number in the three cases. I read `domain/models.py`, `ranking.py`, `stats.py`, `verdict.py` and `weeks.py`, plus `report.py`, `schemas.py`, `api.py` and `deps.py`.

1. `settings.py:32` and `verdict.py:38-39`. The code adds a `too_quiet` rule, `median < min_baseline_median` (4.0).
   - PLAN §2 says only "if its baseline is too quiet" and gives no threshold. The threshold comes from the code, not from the plan.
   - It matters because 3 of 15 account 6 locations (C, H, O) become unjudged on this rule alone.
   - The comparison is exclusive, so a median of exactly 4 is judged (Site F, Site G in case 2b's baseline neighbours, and Site M/I all show this).
2. `verdict.py:27-34`. The code computes a band, `center ± max(z_min·spread, min_abs)`.
   - The plan does not define a band beyond "baseline{median, band}".
   - `band_low` is not clipped at 0. The API returned `band_low=-1.43` for Site G.
3. `verdict.py:20-23` and `verdict.py:38`. The precedence is no_activity, then not_enough_history, then too_quiet, then higher/lower/normal.
   - PLAN §2 and §6 list the verdict names but do not state a precedence, so this order comes from the code.
   - `too_quiet` is decided by the baseline median only and leaves z and diff as None. A too_quiet location is therefore ranked as unjudged.
4. `ranking.py:11-12`. Ties on |z| then |diff| are broken by name. Unjudged items sort after the judged ones, by name.
   - PLAN §2 says only "ties broken by absolute difference" and "not judged sort below".
   - The name tie-break comes from the code.
5. `report.py:39` and `report.py:90-92`. The first selectable week is the account's first event week plus 8 weeks, computed with `fetch_account_start`.
   - The plan says to judge complete weeks and show `not_enough_history` below 8 weeks. The code instead hides those weeks from the account's selector.
   - PLAN §6 `/api/weeks` is "the selectable complete weeks", so this is a reasonable reading, but the plan does not say it.
6. `schemas.py:17-22`, `schemas.py:46-56` and `report.py:116-123`. Names and shapes differ from the PLAN §6 sketch:
   - The baseline has `band_low` and `band_high`, plus `mad`, `spread` and `weeks_used`, instead of a single `band`.
   - Locations carry `z` and `diff` instead of `score`.
   - `Parameters` adds `min_baseline_median`, and `Summary` adds `history_weeks` and `data_quality`.
   - Nothing is dropped. Floats pass through unrounded.
7. `deps.py:56`. With no header, the account defaults to `demo_account_id=15` (`settings.py:17`). PLAN §1 allows "demo default or header".
8. `deps.py:43-45`. The data start and as-of are global over all accounts, which is what PLAN §2 says.
   - Only the week bounds are shared. Counts are always scoped by account id in the code I could read.
   - I did not see a path where another account's or a later week's events enter a series.
9. `weeks.py:22`. `last_complete_week` is the local Monday of the as-of minus 7 days. This matches the plan: a week is complete once it has ended on or before the as-of.
10. `weeks.py:25-34`. `first_complete_week` returns the Monday only if the start is exactly Monday 00:00:00 local. This matches the plan.

Calendar dates written in PLAN:
- "last complete week (2026-07-20)": agrees with what I derived.
- "default here is the max occurred_at (2026-07-27)": agrees as a date.
- "the 2026-06-03 spike": falls in week 2026-06-01, which agrees.
- "25 seed weeks": agrees (Feb 2 to Jul 20 is 25 Mondays).
- "12,626 events": the view holds 12,614, which is consistent with 12 removed duplicates. I could not check the raw count because I may not read `activity_events`.

I found no disagreement.

### 4. Endpoint vs recompute

No mismatch. The endpoint matched my numbers at 6 significant digits or better on every field I compared.

The comparison covered about 190 values.
- `/api/report?week=2026-06-01`, account 6:
  - **Account summary:** total, median, MAD, spread, z, diff, verdict, weeks_used, and the parameters.
  - **Fifteen locations:** the same fields plus the order.
- `/api/locations/Site%20N/history?week=2026-04-27`, account 6: verdict, z, diff, median, MAD, spread, weeks_used, and all 12 baseline totals plus the selected week.
- `/api/locations/Site%20G/history?week=2026-06-01`, account 6: the same fields.
- `/api/weeks` for every account.

Details:
- **Case 1, account level:** total 880, median 73.5, MAD 9.0, spread 13.3434, z 60.4419, diff 806.5, verdict higher, weeks_used 12. My z was 60.442.
- **Case 2a (Site N, Apr 27):** z -1.011736, diff -3.0, median 6, MAD 2, spread 2.9652, normal. The weekly totals matched.
- **Case 2b (Site G, Jun 1):** z 17.705382, diff 52.5, median 4.5, MAD 2, spread 2.9652, higher.
- **Location order:** the same as my expected order. The judged locations came out D, N, L, F, K, M, J, I, E, B, G, A. After them came C, H and O, all `too_quiet`, ordered by name.
- **Per-location values in the report:** each of the 15 locations' median, MAD, spread, z and diff matched my SQL.
- **`/api/weeks`:**
  - **Accounts 1 to 19:** each returned 17 weeks starting 2026-03-30 and a default_week of 2026-07-20. That is 2026-02-02 plus 8 weeks, which is what I expected.
  - **Account 20 (no events):** it returned `weeks: []` and `default_week: null`. The report path has an empty state: week None, verdict `no_activity`, from reading `report.py:193`.

### 5. Could not check

- **Weekly series and location start rule:** `backend/app/series.py` (`fetch_series`, `fetch_account_start`) is not on the allowed list. I did not read how locations start, how history is zero-filled for a location that stops, or what feeds `history_weeks`. I matched the outputs to my SQL instead.
- **The 12 duplicates across 7 accounts, and the 12,626 raw event count:** I may not read `activity_events`, so I did not verify them. I only saw that the view holds 12,614 rows.
- **`/api/report` for account 20:** I did not request it. Its empty state is from reading `report.py:193`.
- **Other weeks and accounts:** I did not recompute any week besides the three cases, and I did not recompute any account other than 6. I did not exercise DST weeks.
- **Error paths:** I did not test invalid weeks, unknown locations or a bad header.

### 6. Method notes

SQL, condensed. Every statement used only `clean_events`, plus `accounts` for the time zone:
- **Bounds:** `select count(*), min(occurred_at), max(occurred_at) from clean_events`.
- **Per-account local week:** one query converted min and max with `(b.s at time zone 'UTC') at time zone a.timezone`. It took `date_trunc('week', ...)` of the local start, adding 7 days unless the start equals that Monday exactly. For the last week it took `date_trunc('week', local_max) - 7 days`.
- **Series:** `generate_series(first_week, last_week, '7 day')` left-joined to `clean_events` on `account_id` and `local_week`, with `count(c.id)` split by known and other `event_type`.
- **Locations:** the same series per `(account_id, location)`, starting at `greatest(first_event_week, '2026-02-02')`. I scanned it for series with zero weeks. Only three locations qualified: account 6 Site G (2 zeros), account 6 Site N (1 zero) and account 18 Site C (1 zero).
- **Statistics:** median and median-of-deviations with `percentile_cont(0.5)`, spread `greatest(1.4826*mad, sqrt(median), 1)`, ranking `order by abs(z) desc, abs(diff) desc`.

Surprising or noteworthy:
- The view and the code agree on the double `AT TIME ZONE`. The view dedupes after normalization and does not filter event types, as the migration says.
- I wrote the three hand computations before querying the API. I did not change any number after seeing an endpoint.
- Account 6's spike week is 880 events at account level, and every one of its 15 locations jumped. Site G has a spike week in its baseline for any later week selected inside the next 12 weeks. I did not test those weeks.

Files read: `/Users/andresruiz/dev/technical-tests/qualitara/relay-reporting-app/PLAN.md`, `backend/migrations/versions/0002_clean_events_view.py`, `backend/app/settings.py`, `backend/app/domain/{models,ranking,stats,verdict,weeks}.py`, `backend/app/{report,schemas,api,deps}.py`.

---

## Part 2: comparison against the tests (main session)

Done after the report was received, against `tests/api/test_api_seed.py` (S5–S9, S11) and `tests/api/test_backtest.py` (B1, B2).
The reviewer chose its own cases, so only B1, B2 and S7 overlap with it directly.

| Test | Reviewer's numbers | Test's expected | Difference |
|---|---|---|---|
| B1, S7: account 6 at 2026-06-01 | total 880, median 73.5, MAD 9, spread 13.3434, z 60.442 (API 60.4419), diff 806.5, higher, weeks_used 12, same 12-week history | same, z ≈ 60.44 | none |
| B2: locations of account 6 at 2026-06-01 | 15 locations, 12 judged (smallest z 14.84, all higher), 3 unjudged: C, H, O (`too_quiet`) | 15 locations, 12 judged, 12 flagged `higher`, 3 unjudged C, H, O | none |
| S9: account 6 Site G | two zero weeks; at 06-01 x is 57 and the baseline has a 0 at 04-13 | 06-01 is 57 and 06-29 is 0 (profile: zero weeks 04-13 and 06-29) | none, but a different window: S9 judges 07-20 (median 4.5, MAD 1.5), the reviewer judged 06-01 (median 4.5, MAD 2). Consistent, not a direct check. |
| S11: `too_quiet` | at 06-01, C (median 3), H and O (3.5) are `too_quiet`, M is judged (z 23.0) | at 07-20, Site M is `too_quiet` (median 3.5) and account 18 Site A (median 3) | none, different weeks. The rule (exclusive `< 4`) is confirmed, S11's own values are not. |
| S5, S6, S8 | account 15 and account 1 Site A were not recomputed | | not covered by this run |
| S2, S3, S4 (weeks) | accounts 1 to 19: 17 weeks from 03-30, default 07-20. Account 20: `[]`, `null`. | same | none |

Other points:
- **Negative `band_low`:** the reviewer notes `band_low` is not clipped at 0 (Site G, -1.43). That is D-17 (the exact no-flag region), and the API output for account 15 Site B (-0.913) showed the same earlier. It is a presentation question for T4; no test pins or forbids it.
- **Reviewer deviations 5 and 6** (the hidden early weeks; field names that differ from PLAN §6) are already recorded as plan gaps in the T3 plan (Q2), D-21 and D-22.
- **PLAN dates:** all five checked dates agree with the data.
- **Not verifiable from the report:** that it wrote its tables before its first `curl` (only the final report is visible); its "about 190 values" count.
- **Could not read `series.py`:** this run did not read `backend/app/series.py`, so the zero-fill and location-start logic were checked only through API outputs. `series.py` was added to the reviewer's allowed reads afterwards (plan Deviations).

Follow-ups made from this run: the two reviewer-sourced cases became S15 (account 6 Site N at 2026-04-27) and S16 (account 6 Site G at 2026-06-01) in `test_api_seed.py`; the code agreed with every value.
