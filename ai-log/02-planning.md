▗ ▗   ▖ ▖  Claude Code v2.1.317
           Sonnet 5.5 · Claude Pro
 ▘▘   ▝▝   ~/dev/technical-tests/qualitara/relay-reporting-app

▎ [✻] [✻] [✻] · Share Claude Code and earn $10 in usage credits · /passes

❯ /clear                                                                        

❯ Read @CLAUDE.md, @docs/data-profile.md and @ai-log/notes.md first.            
                                                                                
  We're now planning DASH-247. I want to write PLAN.md together with you. Don't 
  write                                                                         
  any code. First we agree on the content, then you draft the file.             
                                                                                
  ## Decisions I've already made (challenge them if you see a problem)          
  - User: a single customer admin for one account. No auth. The backend         
  resolves the                                                                  
    account via a `get_current_account` dependency (demo default/header for     
  now). The UI                                                                  
    has an account switcher clearly labeled as a demo stand-in for login.       
  - "Is this normal?" = a selected week compared against that location's own    
  history,                                                                      
    plus an account-level rollup. Locations are ranked by how far they deviate  
  from                                                                          
    their own normal, so "which location needs attention" is answered by the    
  ordering.                                                                     
  - Weeks run Monday–Sunday in the account's timezone. We judge complete weeks  
  only.                                                                         
  - "As of" is anchored to the data, not now(). The default view is the last    
  complete                                                                      
    week in the data (2026-07-20). A week selector is the user input persisted  
  in the URL                                                                    
    (along with account and selected location).                                 
  - Robust baseline (median-based), because of the account 6 spike and low      
  volumes.                                                                      
    Partial weeks are excluded from the baseline.                               
  - Cleaning: raw seed tables stay untouched. A SQL view (created in an Alembic 
  migration)                                                                    
    dedupes exact duplicates and normalizes defensively. Aggregations read only 
  from it.                                                                      
    Count by event_type and ignore duration and outcome for the baseline.       
  - One focused screen: an account summary, a location table ranked by          
  deviation, and a                                                              
    location detail with ~12 weeks of history against its normal band.          
  - AI feature last and optional, behind a server-side flag (off by default)    
  plus                                                                          
    per-request opt-in. The deterministic logic decides what's anomalous. The   
  LLM never                                                                     
    does. The LLM sits behind an interface, and the app must run fully without  
  an API key.                                                                   
                                                                                
  ## Open decisions: give me 2–3 options each with trade-offs and a             
  recommendation, then I'll decide                                              
  1. Baseline window: trailing N weeks (which N?) vs all prior complete weeks.  
  2. Verdict rule given low counts (4–10/week per location): IQR band, median ± 
  k·MAD                                                                         
     (with what floor when MAD is ~0?), or a count-aware rule. How do we avoid  
  flagging                                                                      
     a difference of 2 events as "abnormal"?                                    
  3. Metrics shown: total events only, per event type, or total plus per-type   
  breakdown.                                                                    
  4. Minimum history before showing a verdict, and how the UI shows "not enough 
  data"                                                                         
     (e.g. account 20).                                                         
  5. AI feature shape: (a) a generated summary of the computed results, or (b)  
  a                                                                             
     constrained chat with tool calling over read-only, account-scoped queries. 
     Also: real provider adapter (key in .env) plus a mock default, vs mock     
  only.                                                                         
     Consider verification, trust boundary, time budget and fit with the        
  ticket.                                                                       
                                                                                
  ## Questions for the business (I'm not sending them on a weekend, so they go  
  in section 12                                                                 
  with a working assumption and impact if wrong)                                
  - Is the 2026-06-03 spike for account 6 a known event (campaign, backfill) or 
  an artifact?                                                                  
  - Are weeks Monday–Sunday in the account's timezone?                          
  - Does "messy data" refer to what the profile found, or are other issues      
  expected?                                                                     
  Add any other questions that come up while planning.                          
                                                                                
  ## PLAN.md structure I want                                                   
  1. Ticket interpretation (what "normal" means, who uses it, the               
  Monday-morning use case)                                                      
  2. Definitions (week, as-of, baseline, verdict)                               
  3. Data handling (cleaning rules, each linked to a finding in                 
  data-profile.md)                                                              
  4. Scope: in / out / deferred, with reasons                                   
  5. UX: the single screen                                                      
  6. API sketch (endpoints, main response shapes)                               
  7. Schema and migrations                                                      
  8. Tickets: a high-level list (DB, backend, frontend, AI). Each ticket gets   
  its own                                                                       
     detailed plan in plans/ later.                                             
  9. Testing strategy and quality gate (a single `make check` that must pass    
  before merge)                                                                 
  10. Engineering principles (maintainability, config via env, pure domain      
  logic,                                                                        
      proportional architecture, no over-engineering)                           
  11. Where would an LLM fit? (use case and why, trust boundary, verification   
  of                                                                            
      nondeterministic output, failure handling, cost/latency, what's needed    
  before                                                                        
      production, and what we deliberately don't build and why)                 
  12. Open questions and working assumptions (question / assumption / impact if 
  wrong)                                                                        
  13. Risks                                                                     
                                                                                
  Keep it concise and practical, roughly 2–4 pages. It's a working plan, not a  
  polished doc.                                                                 
                                                                                
  Start with your challenges to my decisions and the options for the open       
  decisions.                                                                    
  Don't draft PLAN.md until I've answered.                                      
  ⎿  Read CLAUDE.md (36 lines)
  ⎿  Read docs/data-profile.md (429 lines)
  ⎿  Read ai-log/notes.md (43 lines)

⏺ I read the three files. Nothing is drafted or written yet.

  Challenges to your decisions

  Most of your decisions hold. These are the ones I'd change or sharpen:

  1. The baseline must use only weeks before the selected week. Once there's a
     week selector, a baseline of "all complete weeks" would leak future data
     into older weeks. The selector then also needs a rule for early weeks with
     too little history (see open decision 4).
  2. Ranking by deviation needs a count-aware score. Raw differences make a
     10-event location outrank a 4-event one, and a 2-event wobble would top the
     list. Rank by a standardized score (see open decision 2). Normal locations
     stay in the table but sort below flagged ones.
  3. Account 6 breaks the ranking on 2026-06-03. All 15 locations spike
     together. The UI should detect "most locations deviate in the same
     direction" and show a single "account-wide change" banner above the table.
     Otherwise the ordering says nothing useful that week.
  4. Multiple comparisons. With 69 locations, a loose threshold gives several
     false flags every week. I'd add an acceptance check: backtest the rule over
     the 25 seed weeks and report the flag rate. The account 6 spike must flag,
     and normal weeks should rarely flag.
  5. Keep the account rollup separate from the location verdicts. It is its own
     series, the sum of locations per week, with its own median and band.
     Account-level counts are steadier, so its band is tighter.
  6. Normalization in the view should trace to a finding. The profile found zero
     casing or whitespace variants. I'd keep in the view:
     - exact-duplicate removal (finding 7), keeping the lowest id;
     - trim on text fields;
     - lower on event_type.

     I'd not case-fold location, because that could silently merge distinct
     sites. I'd add a data-quality test that fails on an unknown event_type,
     rather than silently dropping it.
  7. Alembic only adds the view, not the raw tables. schema.sql and seed.sql
     stay immutable and load through docker-compose. The migration creates the
     view over those tables. I'd add no indexes (12k rows).
  8. The view exposes local_ts and local_week once, using the correct double AT 
     TIME ZONE. That keeps the timezone logic in one place. Python then does the
     baseline and verdict as pure functions over zero-filled weekly series.
  9. Weeks with no events must be zero-filled (generate_series). A zero week is
     a real signal. Only 4 occur in the seed.
  10. The history chart's y-axis will be blown out by the 881 spike (median 76).
      The UI needs to cap or annotate the axis.

  Open decisions

  1. Baseline window

  ┌──────────────────────┬──────────────────────────────────────────────────┐
  │        Option        │                    Trade-off                     │
  ├──────────────────────┼──────────────────────────────────────────────────┤
  │ A. All prior         │ Most stable, but no adaptation to trends, and    │
  │ complete weeks (up   │ the window length varies by week                 │
  │ to 24)               │                                                  │
  ├──────────────────────┼──────────────────────────────────────────────────┤
  │ B. Trailing 8        │ Adapts faster, but the median and MAD of 8       │
  │                      │ integers of 4–10 are noisy                       │
  ├──────────────────────┼──────────────────────────────────────────────────┤
  │                      │ Roughly a quarter. It matches the ~12-week       │
  │ C. Trailing 12       │ detail chart, so the band shown is exactly the   │
  │                      │ band used                                        │
  └──────────────────────┴──────────────────────────────────────────────────┘

  Recommend C, with prior complete weeks only, partial weeks excluded, and zero
  weeks counted as 0.

  2. Verdict rule

  ┌──────────────────┬──────────────────────────────────────────────────────┐
  │      Option      │                      Trade-off                       │
  ├──────────────────┼──────────────────────────────────────────────────────┤
  │ A. IQR/Tukey     │ Quantiles of 12 small integers are unstable, and     │
  │ fences           │ tied values give fences that are too tight           │
  ├──────────────────┼──────────────────────────────────────────────────────┤
  │ B. median ±      │ Robust and easy to explain. It needs a floor for MAD │
  │ k·MAD with       │  ≈ 0                                                 │
  │ floors           │                                                      │
  ├──────────────────┼──────────────────────────────────────────────────────┤
  │ C. Poisson       │ Principled for counts, and location CV (~0.4) is     │
  │ prediction       │ close to Poisson. It is harder to explain, and       │
  │ interval         │ account-level data is overdispersed                  │
  └──────────────────┴──────────────────────────────────────────────────────┘

  Recommend B with two guards:
  - spread = max(1.4826·MAD, √median, 1). The √median term is the Poisson floor,
    so it also covers MAD ≈ 0.
  - z = (x − median)/spread.
  - Flag only if |z| ≥ z_min and |x − median| ≥ min_abs (start with 2.5 and 3),
    so a 2-event difference is never "abnormal".
  - Add a second "strong" tier at about |z| ≥ 3.5.
  - Make all of these config constants, tuned by the backtest in challenge 4.

  Flags are neutral in direction ("higher/lower than usual"). Score = |z|, with
  ties broken by absolute difference.

  3. Metrics

  ┌──────────────────────────┬──────────────────────────────────────────────┐
  │          Option          │                  Trade-off                   │
  ├──────────────────────────┼──────────────────────────────────────────────┤
  │ A. Total only            │ Best signal at low volume, but hides "calls  │
  │                          │ down, leads up"                              │
  ├──────────────────────────┼──────────────────────────────────────────────┤
  │ B. Per type only         │ Per-type location counts are about 1–5 a     │
  │                          │ week, so mostly noise                        │
  ├──────────────────────────┼──────────────────────────────────────────────┤
  │ C. Total plus per-type   │ Covers calls, leads and appointments from    │
  │ breakdown                │ the ticket                                   │
  └──────────────────────────┴──────────────────────────────────────────────┘

  Recommend C, with the verdict on the total only. Per-type counts versus their
  own median appear as context in the account summary and location detail, with
  no verdict. Per-type verdicts go in "deferred".

  4. Minimum history and "not enough data"

  Two options for the history floor:
  - 4 weeks: quick, but the bands are unreliable.
  - 8 weeks: the first judgeable week is 2026-03-30.

  Recommend 8, plus a volume floor (median < 1 means "too quiet to judge"). The
  seed never triggers the volume floor, so fixtures test it.

  The UI shows three distinct states:
  - No activity at all (account 20): a page-level empty state.
  - Not enough history: a grey badge with the counts still shown, sorted below
    flagged locations and never ranked.
  - Too quiet: same grey badge, different text.

  The week selector lists all complete weeks. Early weeks show "not enough
  history (has n of 8)".

  5. AI feature shape

  ┌──────────────────┬──────────────────────────────────────────────────────┐
  │      Option      │                      Trade-off                       │
  ├──────────────────┼──────────────────────────────────────────────────────┤
  │ (a) Summary of   │ Small surface, cheap to verify, and it fits the      │
  │ computed results │ ticket                                               │
  ├──────────────────┼──────────────────────────────────────────────────────┤
  │                  │ Most useful, but it brings: a larger trust boundary  │
  │ (b) Tool-calling │ (account scoping, injection), an eval burden for     │
  │  chat            │ open-ended questions, high cost and latency, and a   │
  │                  │ time budget that doesn't fit                         │
  └──────────────────┴──────────────────────────────────────────────────────┘

  Recommend (a). The LLM gets only the computed payload (account verdict plus
  the top flagged locations). It returns structured claims that cite a location
  and a metric. The server checks each cited number against the payload and
  renders the numbers itself. If validation fails, or the call errors or times
  out, it falls back to a deterministic template summary. Build (b) nowhere.
  Section 11 explains why.

  Provider: build the interface and a deterministic mock first, as the default.
  The real adapter (key in .env) is the last, optional sub-ticket, small, with a
  contract test against a fake client. This keeps CI keyless. The cost is that
  the real path only gets a manual smoke test.

  Extra business questions for section 12

  - Is account 18's UTC timezone real or a default?
  - Are "Site A…" labels stable identifiers, and can a location be renamed or
    merged?
  - Do low weeks matter as much as high ones? My working assumption is yes,
    flagged neutrally.
  - Are the 12 duplicates known double-inserts? My working assumption is yes.
  - Is account 20 a new customer, or should it have data?
  - Is production "as of" simply the wall clock? My assumption is yes, through
    an injectable clock, with the seed using a data-anchored default.

  What I need from you

  Say "go with all recommendations", or give overrides for 1–5. Also confirm
  challenges 1–10, especially 3, 6 and 7. Then I'll draft PLAN.md.

✻ Baked for 1m 12s · done 2:35 PM

❯ Good challenges. Decisions:                                                   
                                                                                
  Open decisions: go with your recommendations for 1–5 (trailing 12 prior       
  complete                                                                      
  weeks; median ± k·MAD with the √median floor and a min absolute difference;   
  total                                                                         
  plus per-type breakdown, verdict on total only; 8 weeks minimum history;      
  option (a)                                                                    
  summary, mock default first, real provider adapter as the last optional       
  sub-ticket).                                                                  
                                                                                
  Challenges:                                                                   
                                                                                
  - Accept 1, 2, 5, 6, 8, 9.                                                    
  - 4: accept as a lightweight test (the account 6 spike must flag, normal      
  weeks                                                                         
    rarely flag). Not a tuning exercise.                                        
  - 7: reject. The brief requires a real schema with migrations, and the        
  starter README                                                                
    says to put the schema into our own migrations rather than running the DDL  
  by hand.                                                                      
    So the first Alembic migration creates accounts and activity_events         
  (adapted to                                                                   
    Postgres), the next one creates the view, and a seed script loads seed.sql  
  after                                                                         
    migrating. Also add a composite index on (account_id, occurred_at). Not     
  needed for                                                                    
    12k rows, but it's what a real table would have.                            
  - 3 and 10: defer. The account-level verdict already communicates an          
  account-wide                                                                  
    change, and the chart axis is a frontend-ticket detail.                     
  - Single verdict tier for now. The "strong" tier is deferred.                 
                                                                                
  Add all your extra business questions to section 12.                          
                                                                                
  Keep PLAN.md high-level. Concrete threshold values, UI states and chart       
  details                                                                       
  belong in the per-ticket plans in plans/, not here. PLAN.md should say what   
  we                                                                            
  decided and why, not every parameter.                                         
                                                                                
  One more principle for the plan: statistical parameters (baseline window,     
  minimum                                                                       
  history, z threshold, minimum absolute difference) are business rules, not    
  hard-coded constants. They live in a typed settings module                    
  (pydantic-settings),                                                          
  with defaults in code and env overrides, alongside feature flags like         
  LLM_SUMMARY_ENABLED. The defaults are pragmatic and sanity-checked by the     
  backtest,                                                                     
  not statistically optimized. Tuning them is explicitly not the focus of this  
  exercise. The API response includes the parameters it used, so the UI copy    
  (e.g.                                                                         
  "compared with your last 12 weeks") follows the config instead of hard-coding 
  it.                                                                           
  Per-account overrides (thresholds, features, branding per tenant) go under    
  "deferred" as the natural next step for a multi-tenant SaaS.                  
                                                                                
  Go ahead and draft PLAN.md.                                                   

⏺ Write(PLAN.md)
  ⎿  Wrote 237 lines to PLAN.md
      1 # PLAN.md: DASH-247
      2 
      3 Working plan. It records what we decided and why. Concrete parame
        ter values, UI states and
      4 chart details live in the per-ticket plans in `plans/`. Data fact
        s: [docs/data-profile.md](docs/data-profile.md).
      5 
      6 ## 1. Ticket interpretation
      7 
      8 A customer admin opens the app on Monday morning and wants one an
     … +230 lines (~15 KB) (ctrl+o to expand)

⏺ I drafted PLAN.md at the repo root, with all 13 sections in your order. I
  didn't commit it. It's about 3 pages and sticks to decisions and reasons.
  Thresholds, UI states and chart details are left for the per-ticket plans.

  How I applied your decisions:
  - Open decisions 1–5: I used the recommendations as you confirmed them.
  - Challenge 7 (migrations): I wrote it as you decided. Migration 1 creates
    accounts and activity_events with the composite index, migration 2 creates
    the view, and a seed script loads seed.sql unmodified.
  - Challenges 3 and 10: these are deferred. The account-wide banner is in the
    Deferred list, and the chart-axis point is left to the frontend ticket plan.
  - Strong tier and per-account overrides: both are in the Deferred list.
  - Challenge 4: the backtest is a lightweight test inside the backend API
    ticket. It is not a tuning step.
  - Settings: the statistical parameters are in a pydantic-settings module with
    env overrides, next to LLM_SUMMARY_ENABLED. The API echoes the parameters it
    used.
  - Section 12: it holds your three questions plus my six extras, each with an
    assumption and the impact if wrong.

  Things to check:
  - Seed files unread: I haven't read data/schema.sql or data/seed.sql, only the
    profile. I assumed seed.sql contains only INSERTs. If it also has DDL, the
    seed script and migration 1 will conflict, so check this in the DB ticket
    plan. The plan already has a risk entry that checks the 20 accounts and
    12,626 events after loading.
  - Partial-week definition: I defined a complete week as one that "ended on or
    before as-of". If the data ended mid-Sunday, that week would count as
    partial.
  - Added beyond your list: an API sketch with a not_enough_history | too_quiet 
    | no_activity verdict set, a cached-per-week note under LLM cost, and a
    timezone/DST risk. Remove any you don't want.

  Once you approve PLAN.md, the next step is plans/ for the DB ticket.

✻ Cogitated for 49s · done 2:52 PM

※ recap: We're planning DASH-247, the reporting app that shows whether an account's and each location's weekly activity is normal, and I've drafted PLAN.md without committing it. Next, review and approve it, then I'll write the DB ticket plan in plans/. (disable recaps in /config)

❯ Approved with three small changes:                                            
                                                                                
  1. Seed check: resolved. data/seed.sql contains only comments and INSERT      
  statements                                                                    
     (no DDL), so there's no conflict with migration 1. Drop that concern; keep 
  the                                                                           
     row-count test.                                                            
  2. Rename ticket 1 to "Scaffold + DB": it also creates the backend skeleton   
  (FastAPI                                                                      
     app, settings module stub, pytest, ruff) and the Makefile with make check, 
  so                                                                            
     the quality gate exists from the first ticket. The frontend scaffold stays 
  in ticket 4.                                                                  
  3. Add ticket 6 "Docs and final verification": README (run instructions,      
  decisions,                                                                    
     trade-offs, deferred items), .env.example, a clean-clone run check (must   
  work in                                                                       
     ~15 min), and the AI log reflection. Priority: ticket 6 comes before       
  ticket 5. If                                                                  
     time runs short, the AI ticket is cut, not this one.                       
                                                                                
  Everything else stays as drafted. Apply these edits, then stop. Don't commit; 
  I'll                                                                          
  review and commit myself.                                                     

⏺ Update(PLAN.md)
  ⎿  Added 4 lines, removed 2 lines
      133  Each ticket gets its own plan in `plans/<ticket>.md`, approved
            before any code. One branch and one
      134  session per ticket.
      135  
      136 -1. **DB:** docker-compose, Alembic, migrations 1 and 2, the se
          -ed script, and view tests (duplicates,                        
      137 -   timezone and DST bucketing, week edges).                   
      136 +1. **Scaffold + DB:** docker-compose, Alembic, migrations 1 an
          +d 2, the seed script, and view tests                          
      137 +   (duplicates, timezone and DST bucketing, week edges). Also 
          +the backend skeleton (FastAPI app,                            
      138 +   settings module stub, pytest, ruff) and the Makefile with `
          +make check`, so the quality gate exists                       
      139 +   from the first ticket. The frontend scaffold stays in ticke
          +t 4.                                                          
      140  2. **Backend core:** pure domain logic (baseline, verdict, ran
           king) with tests first on small
      141     hand-computed fixtures. Then the typed settings module and 
           the weekly-series queries (zero-filled).
      142  3. **Backend API:** FastAPI endpoints, the `get_current_accoun
           t` dependency, and the response models.

⏺ Update(PLAN.md)
  ⎿  Added 5 lines
      145  5. **AI (optional, time-boxed):** the summary interface, the v
           alidator, the deterministic fallback and
      146     the mock provider, then the flag and opt-in. A real provide
           r adapter is the last sub-ticket and
      147     is only done if time remains.
      148 +6. **Docs and final verification:** README (run instructions, 
          +decisions, trade-offs, deferred items),                       
      149 +   `.env.example`, a clean-clone run check (must work in ~15 m
          +in), and the AI log reflection.                               
      150  
      151 +**Order:** 1, 2, 3, 4, then 6, then 5. Ticket 6 comes before t
          +icket 5. If time runs short, the AI                           
      152 +ticket is cut, not the docs and verification.                 
      153 +                                                              
      154  ## 9. Testing strategy and quality gate
      155  
      156  - **Tests first** for aggregation and verdict logic, using sma
           ll fixtures with hand-computed expected

⏺ Update(PLAN.md)
  ⎿  Added 2 lines, removed 2 lines
      238    (20 accounts, 12,626 events).
      239  - **Untested real-provider path:** the real LLM adapter is onl
           y smoke-tested manually. Mitigation:
      240    it is optional, off by default, and the mock and fallback co
           ver the logic.
      241 -- **Time budget:** the AI work is last and time-boxed. If time
          - runs out, section 11 stands as the                           
      242 -  design.                                                     
      241 +- **Time budget:** the AI work comes after docs and final veri
          +fication (ticket 6) and is time-boxed.                        
      242 +  If time runs out, the AI ticket is cut and section 11 stands
          + as the design.                                               
      243  - **Timezone/DST mistakes:** a single conversion in the view, 
           with tests across the 2026-03-08 DST
      244    change and a Phoenix (no-DST) account.

⏺ Update(PLAN.md)
  ⎿  Added 2 lines, removed 3 lines
      233    Mitigation: a single conservative tier, plus the backtest sa
           nity check.
      234  - **Account 6 spike dominates the story** for the weeks around
            2026-06-03, and all 15 locations
      235    flag together. Mitigation: the account-level verdict; a dedi
           cated banner is deferred.
      236 -- **Migrations vs. the provided DDL:** the adapted migration m
          -ust stay faithful to `schema.sql`, and                        
      237 -  the seed must load unmodified. Mitigation: a test that loads
          - the seed and checks row counts                               
      238 -  (20 accounts, 12,626 events).                               
      236 +- **Migrations vs. the provided DDL:** the adapted migration m
          +ust stay faithful to `schema.sql`.                            
      237 +  Mitigation: a test that loads the seed and checks row counts
          + (20 accounts, 12,626 events).                                
      238  - **Untested real-provider path:** the real LLM adapter is onl
           y smoke-tested manually. Mitigation:
      239    it is optional, off by default, and the mock and fallback co
           ver the logic.
      240  - **Time budget:** the AI work comes after docs and final veri
           fication (ticket 6) and is time-boxed.

  Searched for 1 pattern (ctrl+o to expand)

⏺ Update(PLAN.md)
  ⎿  Added 1 line, removed 1 line
      71  | Account summary, location ranking, location detail with ~12 w
          eeks of history | The core question |
      72  | Week selector, with account, week and location persisted in t
          he URL | The one user input |
      73  | Total verdict plus per-type breakdown | Total is the best sig
          nal at 4–10 events/week |
      74 -| Optional AI summary behind a flag | Explicitly in the brief, 
         -built last |                                                   
      74 +| Optional AI summary behind a flag | Explicitly in the brief, 
         +built last (after docs and verification) |                     
      75  
      76  | Deferred | Why |
      77  |---|---|

⏺ I applied the three changes to PLAN.md and didn't commit.

  - Ticket 1: it's now "Scaffold + DB". It adds the backend skeleton (FastAPI
    app, settings module stub, pytest, ruff) and the Makefile with make check.
    The frontend scaffold stays in ticket 4.
  - Ticket 6: added as "Docs and final verification". It covers the README,
    .env.example, the clean-clone check (about 15 minutes) and the AI log
    reflection. An order line now reads 1, 2, 3, 4, 6, 5, and says the AI ticket
    is cut first if time runs short.
  - Seed concern: I dropped the "seed must load unmodified" wording from the
    migrations risk. The row-count test stays.

  I made two more edits for consistency with the new order:
  - The Scope table now says the AI summary is built after docs and
    verification.
  - The time-budget risk says the AI ticket is cut, not ticket 6.

  The tickets are numbered 1–6 but run in the order 1, 2, 3, 4, 6, 5. Renumber 5
  and 6 if that bothers you.

✻ Cooked for 14s · done 2:56 PM

※ recap: We're planning DASH-247 for the Relay reporting app, and PLAN.md is now updated with your three approved changes and left uncommitted. Next, review and commit it yourself, then I'll draft the plan for ticket 1, Scaffold + DB.