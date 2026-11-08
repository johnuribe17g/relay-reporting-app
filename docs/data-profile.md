## TL;DR
- Data covers 2026-02-01 to 2026-07-27: 25 complete Monday–Sunday weeks per location.
  It ends ~15 weeks before today, so "this week" must be anchored to the data, not now().
- Text fields are clean. The real problems are 12 exact duplicates, ~3% NULL outcomes,
  unreliable call durations, and one 60x spike (account 6, 2026-06-03).
- Location volume is low (4–10 events/week, CV ~0.4). Account-level totals are much steadier.
- Account 20 has no events. Timezone bucketing affects only 8 events in this seed.
- Verified independently: exact duplicates and account 6 weekly totals (see [working notes](../ai-log/notes.md))

# Data profile: `data/seed.sql` (DASH-247)

Purpose: describe what the seed data actually contains so we can decide how to compute
"is this week's activity normal?". This document **lists issues and options only**; it does not
decide anything. Decisions belong in PLAN.md.

## Method

- Throwaway `postgres:16` container (`docker run --rm`, port 127.0.0.1:5433, no volume, nothing committed).
  `data/schema.sql` then `data/seed.sql` loaded unmodified with `ON_ERROR_STOP`. `git status` stayed clean.
- All queries are read-only (temp tables only). Queries below are the ones that produced the numbers; long
  ones are trimmed to the essential shape.
- **Local time conversion** (`occurred_at` is `TIMESTAMP` without tz, stored as UTC):

  ```sql
  (e.occurred_at AT TIME ZONE 'UTC') AT TIME ZONE a.timezone
  ```

  Sanity check on a `America/Chicago` account (account 1, February so CST = UTC-6):

  | event id | stored (UTC)        | correct local       | wrong version (`occurred_at AT TIME ZONE tz`) |
  | -------- | ------------------- | ------------------- | --------------------------------------------- |
  | 12       | 2026-02-01 16:39:22 | 2026-02-01 10:39:22 | 2026-02-01 22:39:22+00                        |

  Direction is right: local is 6 hours *earlier* than UTC.
- **Week** in this document = `date_trunc('week', <local ts>)`: Monday 00:00 to Sunday 23:59:59 in the
  account's timezone. (Whether the product uses this definition is an open decision; see section 4.)
- **"Last complete week"** is relative to `max(occurred_at)` in the data, not `now()`.

---

## 1. Row counts and accounts

```sql
select 'accounts', count(*) from accounts union all select 'activity_events', count(*) from activity_events;

select a.id, a.name, a.timezone, a.created_at,
       count(distinct e.location) locations, count(e.id) events
from accounts a left join activity_events e on e.account_id = a.id
group by a.id order by a.id;
```

**Result.** 20 accounts, 12,626 events. There is no `locations` table; a location is just a free-text
`activity_events.location` string. Locations per account: 1 location: accounts 8, 13, 16, 19;
2: accounts 3, 7, 10, 11, 17; 3: accounts 2, 9, 15; 4: accounts 4, 14; 5: accounts 5, 18; 6: account 1;
7: account 12; 15: account 6.
**Account 20 (Quiet Harbor Spa) has zero events.** 69 (account, location) pairs in total.
Time zones in use: America/Chicago, New_York, Denver, Los_Angeles, Phoenix, UTC (6 distinct, all valid IANA).

**Why it matters.** Single-location accounts (4 of 19 with data) and multi-location accounts need the same
answer; 15-location account 6 is the stress case. A location has no stable ID, only a name unique per
account (`Site A` exists in nearly every account). An account with no events has no baseline at all.

**Options.**
- Identify a location by `(account_id, location string)` as-is vs. introduce a `locations` table in our schema (the seed does not provide one).
- Account with no data: show an explicit empty/"not enough data" state vs. omit it from any list.

---

## 2. Date range, future events, events before `created_at`

```sql
select min(occurred_at), max(occurred_at) from activity_events;
select a.id, min(e.occurred_at), max(e.occurred_at), a.created_at,
       count(*) filter (where e.occurred_at < a.created_at) before_created,
       count(*) filter (where e.occurred_at > now() at time zone 'utc') future
from accounts a join activity_events e on e.account_id = a.id group by a.id;
```

**Result.**
- Overall: **2026-02-01 10:57:44 to 2026-07-27 22:20:34 (UTC)**, about 25.9 weeks.
- Every account with data starts between 2026-02-01 and 2026-02-03 (UTC) and ends between 2026-07-24 and 2026-07-27.
  Per location, the first event is Feb 1-5 and the last is Jul 22-27.
- **0 events before the account's `created_at`**, **0 events in the future**.
- Every `created_at` (2025-01-04 to 2025-12-04) is *earlier* than the first event. `created_at` does not
  tell us when data starts for any account: all accounts, even ones created in Dec 2025 (13, 20) or
  Nov 2025 (15), have the same ~26 weeks of history as accounts created in Jan 2025.
- Today's date is 2026-11-08; the data stops about 15 weeks before that.

**Why it matters.** "This week" cannot literally be `now()` with this data: every "current week" computed from
the wall clock would be empty. All accounts have the same fixed history window (~25 complete weeks), which
is an upper bound on baseline length.

**Options.**
- Anchor "this week" to the wall clock (and accept empty results on seed data) vs. anchor to `max(occurred_at)` (globally or per account) vs. a configurable/injected "as of" date.
- Use `created_at` as a lower bound on history vs. ignore it (it is not informative in this seed).

---

## 3. Dataset boundaries: partial weeks and last complete week

```sql
-- per account, in local time
select a.id, a.timezone,
  ((min(occurred_at) at time zone 'UTC') at time zone a.timezone) data_start_local,
  ((max(occurred_at) at time zone 'UTC') at time zone a.timezone) data_end_local
from accounts a, activity_events group by ... ; -- global min/max converted per account tz
```

**Result.**
- Data starts **Sunday 2026-02-01 (local)** for every US zone and UTC. The week beginning Mon 2026-01-26
  therefore contains only that Sunday (18 events across 8 accounts): **a partial first week**.
- Data ends **Monday 2026-07-27 (local)**: 15:20 (LA/Phoenix) to 22:20 (UTC account). The week beginning
  2026-07-27 has only Monday: **79 events, 17 accounts: a partial last week**.
- **Last complete week for every account = week beginning Mon 2026-07-20.** First complete week = Mon 2026-02-02.
  So there are **25 complete weeks** (2026-02-02 to 2026-07-20) for every location.
- Accounts 2 and 8 have no events in the partial week 2026-07-27 yet (their last events are on 07-24 / 07-26).

**Why it matters.** Comparing a partial week to full-week baselines (or including partial weeks in the
baseline) would bias results low. The last week of data is partial for the same structural reason a live
"this Monday morning" week would be: the week has barely started.

**Options.**
- Exclude partial weeks from the baseline (first and last) vs. include with pro-rating vs. compare like-for-like (week-to-date vs. same weekdays/hours of past weeks).
- Treat the current partial week as the thing being judged vs. judge the last complete week.

---

## 4. Time zones and week boundaries

```sql
select count(*) filter (where wk_local <> wk_utc) differ, count(*) from ev;     -- week by local vs by UTC
select timezone, count(*), count(*) filter (where wk_local <> wk_utc) from ev group by 1;
```

**Result.** Only **8 of 12,626 events (0.06%)** land in a different week when bucketed in UTC vs. account-local
time (Chicago 2, Denver 3, LA 2, New_York 1, Phoenix 0, UTC 0). The effect is small here because activity is
mostly mid-day local time and weekends are quiet (see section 12); an event has to occur on Sunday evening
(local) to be in a different Monday-based week.
- `America/Phoenix` does not observe DST (offset to UTC is constant), unlike Chicago/Denver/LA/New_York
  which change on 2026-03-08 within the data range. The `UTC` account (18) has no offset.
- Hour-of-day generation looks anchored to local time and not to UTC: modal UTC hour differs by zone
  (Chicago 15, Denver 14, LA 16, NY 16, Phoenix 15) and modal local hours cluster at about 8-12.
  Chicago's average UTC hour moves only slightly across the DST change (15.7 before, 15.5 after).

**Why it matters.** The effect on the seed data is tiny, but it can matter for real data and for which week
a Sunday-night call belongs to. Buckets must be derived with DST-aware conversion (not a fixed offset), and
"which day is Monday" depends on the account's zone.

**Options.**
- Bucket in account-local time (DST-aware, `timezone` column) vs. UTC (simpler, 0.06% differing here) vs. store a precomputed local-week column.
- Week start: ISO Monday (matches "Monday morning") vs. Sunday vs. rolling 7 days ending at report time.
- Multi-location customers: one timezone per account (what the schema has) vs. per-location timezone (not available).

---

## 5. `event_type` and `outcome` values

```sql
select '['||event_type||']', length(event_type), count(*) from activity_events group by 1,2 order by 3 desc;
select '['||coalesce(outcome,'<NULL>')||']', count(*) from activity_events group by 1 order by 2 desc;
select lower(trim(event_type)), coalesce(lower(trim(outcome)),'<NULL>'), count(*) from activity_events group by 1,2 order by 1,3 desc;
select count(*) filter (where location ~ '[^\x20-\x7E]') ...;   -- non-ASCII / control chars
```

**Result.**
- `event_type` has exactly 3 values, no casing/whitespace/typo variants: `call_received` 7,780; `lead_created` 3,044; `appointment_set` 1,802.
- `outcome` has 7 values plus NULL, no variants: connected 4,669; missed 1,937; open 1,871; completed 1,439;
  converted 1,073; voicemail 934; no_show 305; **NULL 398 (3.2%)**.
- Combinations (all sensible; no impossible pairs found):

  | event_type      | outcomes                                     | NULL outcome |
  | --------------- | -------------------------------------------- | ------------ |
  | call_received   | connected 4,669; missed 1,937; voicemail 934 | 240 (3.1%)   |
  | lead_created    | open 1,871; converted 1,073                  | 100 (3.3%)   |
  | appointment_set | completed 1,439; no_show 305                 | 58 (3.2%)    |

- No non-ASCII or control characters in `location`, `event_type` or `outcome`.
- NULL-outcome rate is steady over time (2.8 to 3.6% per month) and across accounts (up to 4.4%), so it looks like random missing data, not a one-off.

**Why it matters.** Text columns are clean *in this seed*, but real input could have variants; the spec
says "production-like and messy," so any normalization we do would be defensive. NULL outcomes are 3% of
rows: if the baseline is "all events," they count; if it is by outcome (e.g. connected calls, no-shows), they
do not. Note an `appointment_set` with outcome `completed`/`no_show` is a *later* state than "set", and a
`lead_created` `converted` is likewise a later state: outcome is not known at event time.

**Options.**
- Count by `event_type` only (ignore outcome) vs. by type+outcome vs. both.
- NULL outcome: include in totals, count as "unknown", or exclude from outcome-specific metrics.
- Add defensive normalization (trim/lower) at ingest vs. rely on clean input vs. reject/flag unknown values.

---

## 6. Location name variants

```sql
select account_id, lower(regexp_replace(trim(location), '\s+', ' ', 'g')) norm,
       count(distinct location) variants, array_agg(distinct location)
from activity_events group by 1,2 having count(distinct location) > 1;
select account_id, '['||location||']', count(*), min(occurred_at)::date, max(occurred_at)::date
from activity_events group by 1,2 order by 1,2;
```

**Result.** **0 groups** with more than one raw spelling after normalizing case and whitespace. The 69
locations are named `Site A`, `Site B`, ... with no leading/trailing/double whitespace or case variants.
All locations have events in both the first and last complete weeks (no location starts late or stops early).

**Why it matters.** Because there is nothing to merge in this seed, location identity is straightforward
here. Names carry no business meaning ("Site A" in account 1 is unrelated to "Site A" in account 2), so
location must always be scoped by account.

**Options.**
- Key by `(account_id, exact string)` vs. normalized string (case/whitespace) vs. a managed locations table.
- Display: raw name vs. a friendlier label (not available in the data).

---

## 7. Exact duplicates (all columns equal except `id`)

```sql
select account_id, location, event_type, occurred_at, duration_seconds, outcome, count(*), array_agg(id)
from activity_events group by 1,2,3,4,5,6 having count(*) > 1;
```

**Result.** **12 groups of exactly 2 rows = 12 surplus rows (0.1%)**. In every case the two ids are
consecutive (e.g. 5856/5857, 11266/11267, 1538/1539), so they look like double-inserts. Spread over 7
accounts (account 6: 4; accounts 1, 18: 2 each; accounts 2, 4, 8, 12: 1 each) and across event types.
Also checked: no group where `(account, location, event_type, occurred_at)` match but duration/outcome differ.
`id` is gap-free 1 to 12,626 and increases monotonically with `occurred_at`.

**Why it matters.** At this rate (0.1%) the effect on weekly counts is about +0.1 events per location-week, but
duplicates would inflate any exact-count baseline slightly and are the cleanest case of "bad data."

**Options.**
- Dedupe at ingest/migration (drop surplus rows) vs. dedupe at query time (`count(distinct ...)`) vs. leave and accept ~0.1% noise.
- Add a uniqueness constraint over `(account_id, location, event_type, occurred_at, duration_seconds, outcome)`; this can drop legitimate coincident events, so it may be too strict.

---

## 8. Near duplicates

```sql
-- same account+location+event_type, consecutive events <= N seconds apart, excluding exact dups
with x as (select *, lag(occurred_at) over w pt, lag(duration_seconds) over w pd, lag(outcome) over w po
           from activity_events window w as (partition by account_id, location, event_type order by occurred_at, id))
select thr, count(*) pairs,
       count(*) filter (where duration_seconds is not distinct from pd and outcome is not distinct from po) same_payload
from x, unnest(array[0,1,5,10,30,60,300]) thr
where pt is not null and occurred_at - pt <= make_interval(secs => thr) and <not exact dup> group by thr;
```

**Result.**

| gap <= | pairs | of which same duration+outcome |
| ------ | ----- | ------------------------------ |
| 5 s    | 2     | 0                              |
| 10 s   | 4     | 1                              |
| 30 s   | 10    | 2                              |
| 60 s   | 25    | 4                              |
| 300 s  | 131   | 21                             |

Samples (random 10 pairs <= 60 s): gaps of 6 to 58 s, mostly with *different* durations/outcomes (e.g. 784 s then 510 s).
Few look like true duplicates; most are plausible separate events at a busy site, and several of the sampled pairs fall on
account 6 / 2026-06-03 (see section 11). Only 12 (account, location, second) groups hold more than one event, and these are the 12 exact duplicates above.

**Why it matters.** There is no clean signal for near-duplicates; any rule (time window) will also remove
real events. The volume is small (<= 0.2% at 60 s), so it is likely noise for baselines.

**Options.**
- Ignore near-duplicates (only handle exact) vs. flag same-payload pairs within a short window (<= 60 s: 4 pairs) vs. a wider window (300 s: 21 same-payload pairs; likely false positives).

---

## 9. `duration_seconds`

```sql
select event_type, count(*), count(duration_seconds), count(*) filter (where duration_seconds = 0) zero,
       count(*) filter (where duration_seconds < 0) neg, min(duration_seconds),
       percentile_cont(array[.01,.05,.25,.5,.75,.95,.99]) within group (order by duration_seconds), max(duration_seconds)
from activity_events group by 1;
select coalesce(outcome,'<NULL>'), count(*), count(*) filter (where duration_seconds is null), avg(duration_seconds)
from activity_events where event_type='call_received' group by 1;
```

**Result.**

| event_type      | rows  | non-NULL | NULL           | zero | negative | min | p50 | p99   | max   |
| --------------- | ----- | -------- | -------------- | ---- | -------- | --- | --- | ----- | ----- |
| call_received   | 7,780 | 7,467    | **313 (4.0%)** | 0    | 0        | 20  | 754 | 1,484 | 1,500 |
| lead_created    | 3,044 | 0        | 3,044          | 0    | 0        | n/a | n/a | n/a   | n/a   |
| appointment_set | 1,802 | 0        | 1,802          | 0    | 0        | n/a | n/a | n/a   | n/a   |

- Duration is only ever populated for calls (as documented in the schema); never for leads or appointments.
- No zero, negative, or extreme values: calls are between 20 s and 1,500 s (25 min). The distribution is
  almost uniform (about 1,370 to 1,560 calls in each 300 s bucket), and the 1,500 s ceiling has 6 rows.
- **Missed calls have durations**: 1,861 of 1,937 missed calls (96%) carry a duration averaging 737 s,
  and voicemail calls average 768 s, essentially the same as connected calls (765 s). A "missed" call that
  lasted 12 minutes is not meaningful.
- NULL outcome and NULL duration look roughly independent (NULL-outcome calls: 6 of 240 have NULL duration).

**Why it matters.** No cleansing needed for sign/zero/outliers, but duration is not a reliable quality signal
(missed calls with long durations), and 4% of calls lack it. If a baseline used average duration or talk time,
NULLs and non-informative durations matter; if it only counts events, duration is irrelevant.

**Options.**
- Ignore duration entirely (count-only baseline) vs. use it only for connected calls vs. average over non-NULL durations.
- Treat `missed`/`voicemail` durations as invalid (null them in analysis) vs. trust them.

---

## 10. Weekly counts per location (account-local weeks)

```sql
-- 25 complete weeks 2026-02-02 .. 2026-07-20; zeros filled with generate_series
create temp table wc as
select l.account_id, l.location, w.wk, count(e.id) n
from (select distinct account_id, location from activity_events) l
cross join (select d::date wk from generate_series('2026-02-02','2026-07-20','7 days') d) w
left join ev e on e.account_id = l.account_id and e.location = l.location and e.wk_local = w.wk
group by 1,2,3;
-- per location: count(*) filter (where n=0), min, percentile_cont(.25/.5/.75), max, avg, stddev_samp, stddev_samp/avg
```

**Result (69 locations x 25 weeks).**
- **History**: every location has the same 25 complete weeks and is active in all of them, except three
  locations with isolated zero weeks: account 6 Site G (2026-04-13, 2026-06-29), account 6 Site N (2026-02-23),
  account 18 Site C (2026-03-23). **3 of 69 locations have any zero week; 4 weeks in total.**
- **Level**: location mean weekly count ranges **4.2 to 10.4** (median of means 7.3). 67 of 69 locations
  average under 10 events/week; 4 average under 5 (all in account 18, UTC).
- **Volatility** (CV = stddev / mean) per location: min 0.18, median 0.40, max 1.80. Typical location-week
  has p25 to p75 spreads of about 2 to 4 events (e.g. account 1 Site A: p25 7, median 8, p75 9, min 4, max 12;
  account 18 Site B: p25 2, median 5, p75 7, min 1, max 9).
- **Account level** (all locations summed) is far steadier: CV 0.16 to 0.32 for 18 of 19 accounts. Examples:
  account 1 mean 48.5, median 50, p25 43, p75 53, CV 0.16; account 8 mean 10.4, CV 0.18; account 16 mean 6.6, CV 0.32.
- Dataset-wide weekly totals are very flat: 421 to 503 events per complete week, except the spike week in section 11.
- **Account 6 is the exception**: location CVs of 1.2 to 1.8 and account CV 1.54, **caused by one week**
  (section 11). Excluding week 2026-06-01, account 6 locations have mean 4.0 to 5.6 and stddev 1.9 to 2.8, in line with other locations.

**Why it matters.** At location level the weekly counts are small (about 4 to 10) and noisy (Poisson-like:
CV about 0.3 to 0.5), so a week 2 to 3 events away from the mean is routine. A per-location "is this normal?" judgment
will be sensitive to the choice of statistic; at account level it is much tighter. Roughly 25 weeks is the maximum
history, and zero-activity weeks are rare (4 total), so the zero-fill question is nearly moot in this seed but
would matter for real quiet locations.

**Options.**
- Baseline statistic: mean +/- k stddev vs. median with p25 to p75 (IQR) vs. median +/- k MAD. Mean/stddev is distorted by the spike (account 6); median/IQR is not.
- Baseline window: all 25 weeks vs. trailing N (e.g. 4, 8, 13) weeks vs. same-season weeks (only 1 year of data, so no year-over-year).
- Granularity: per location vs. rolled up per account vs. both (multi-location customer: show account first, drill to locations; or flag locations that differ from their own history).
- Minimum history/volume required before showing a verdict (e.g. weeks of data, minimum mean) vs. always show.
- Zero weeks: count as 0 in the baseline vs. exclude as "no data."
- Event scope: all event types combined vs. per type (calls, leads, appointments) vs. calls only.

---

## 11. One-day spike: account 6 on Wednesday 2026-06-03

```sql
select local_ts::date d, count(*) from ev where wk_local = '2026-06-01' group by 1 order by 1;
select account_id, count(*) from ev where local_ts::date = '2026-06-03' group by 1 order by 1;
select min(id), max(id), count(*) from activity_events
 where account_id = 6 and (occurred_at at time zone 'UTC' at time zone 'America/New_York')::date = '2026-06-03';
```

**Result.**
- Week of 2026-06-01 has **1,270 events vs. about 470 in every other complete week** (dataset-wide). Nearly all of
  it is **Wednesday 2026-06-03: 882 events vs. 78 to 110 on other days**.
- **Account 6 (Metro Collision Centers, America/New_York, 15 locations) had 805 events that day** vs. its normal
  daily average of 10.9 (max 28 on any other day), about 60x a typical Wednesday. Other accounts were in their normal
  range (0.3x to 1.9x). The **account 6 weekly total that week was 881 vs. a median of 76**.
- The spike covers **all 15 locations** (42 to 69 events each), has the usual shape: same event-type mix
  (60% calls / 26% leads / 14% appointments vs. 61/23/16 on other days) and a normal hour-of-day curve (peak at 10:00 to 15:00 local).
  805 rows, 804 distinct `(location, type, occurred_at)` keys, so it is not made of duplicate rows.
  Ids 8114 to 8994 are interleaved with other accounts' events, so it looks like a normal ingest, not a
  separate batch.
- The following week for account 6 (2026-06-08) is also slightly high (102 vs. median 76).
- Without this day, monthly totals are flat (1,848 / 2,064 / 2,039 / 1,984 / 2,048 / 1,838 for Feb to Jul).

**Why it matters.** It is the one large outlier in the data and sits inside the baseline window for account 6.
It is indistinguishable from a real surge (e.g. campaign, outage retries, backfill) from the data alone. It
inflates account 6's mean/stddev (mean 105 vs. median 76; stddev 162) and would make an ordinary week look "low" against a mean-based baseline.

**Options.**
- Keep it as real data and use a robust statistic (median/IQR) so it has little influence.
- Exclude outlier weeks from the baseline automatically (e.g. beyond k MADs) vs. by manual flag vs. leave in.
- Winsorize/cap extreme weeks.
- Confirm with data owner whether this is a known event/backfill (cannot be resolved from the data).

---

## 12. Weekday and hour-of-day patterns

```sql
select to_char(local_ts,'Dy'), extract(isodow from local_ts), count(*) from ev group by 1,2 order by 2;
select extract(hour from local_ts), count(*) from ev group by 1 order by 1;
```

**Result.**
- Weekdays about 2,100 to 2,225 events each (Wed shows 2,893 only because of the 06-03 spike); **Sat 584, Sun 583 (about 9% of events
  are on weekends; 8 to 10% in every time zone)**.
- Hour of day (local): peak 10:00 to 12:00 (about 1,100 to 1,200/hour); about 90% of events fall between 05:00 and 19:59;
  there is a thin tail at night (hours 20 to 04 each <= 412; 20:00 to 23:00 about 30 to 47 per hour).

**Why it matters.** On Monday morning, "this week" has barely started: only a few hours of activity exist,
and Mon is a normal weekday, so comparing week-to-date to full-week totals will always look low. If a
verdict is computed on a partial week, it needs a like-for-like comparison. Weekend volume is small, so Sunday
evenings near week boundaries matter little here.

**Options.**
- Compare the last complete week against its baseline (no partial-week handling needed) vs. compare week-to-date to the same elapsed time in prior weeks (needs the hour/day-of-week shape).
- Count all days vs. business days only.

---

## 13. Other oddities and observations

1. **Account 20 (Quiet Harbor Spa) has no events** (created 2025-12-04): empty state is needed.
2. **Seed data is synthetic-looking and very clean** for text fields (no casing, whitespace or typo variants in
   `event_type`, `outcome` or `location`), no negative/zero/future values, and no pre-`created_at` events. The
   "messy" parts actually present: 12 exact duplicate rows, about 3% NULL outcomes, 4% NULL call durations, missed/voicemail calls with
   durations, one large spike, and missing `locations` table. Any other messiness (e.g. variants) is not in this file and should
   not be assumed to be handled by it.
3. **Accounts' `created_at` is not data-start**: all accounts have identical history windows (section 2).
4. **Locations are generic per-account labels** (`Site A..O`), not unique across accounts (section 6).
5. **Account 18 uses `UTC` as its zone** and has the lowest per-location volume (mean 4.2 to 5.0/week); a zone of `UTC` for a
   business account may be a default rather than the real zone.
6. **Phoenix accounts (7, 15) do not observe DST**, so their UTC offset differs from Denver in summer despite both being Mountain-ish.
7. **Staleness**: data ends 2026-07-27 while today is 2026-11-08 (section 2).
8. `id` is a contiguous integer 1 to 12,626 ordered by time: ids carry time order in this seed; real data may not.
9. Low location volume (mean about 4 to 10 per week) limits statistical power; see section 10.
