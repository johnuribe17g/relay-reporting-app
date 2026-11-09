# Fixtures

Real output of the seeded dev API (`make up && make seed`), captured with these commands from the repo root.
Regenerate them when the API changes; `diff -r` against a fresh capture into a temp dir must be empty.

```bash
B=http://127.0.0.1:8000/api; F=frontend/src/test/fixtures
curl -s $B/accounts                                                              > $F/accounts.json
curl -s -H 'X-Account-Id: 15' $B/weeks                                           > $F/a15-weeks.json
curl -s -H 'X-Account-Id: 15' "$B/report?week=2026-07-20"                        > $F/a15-report-0720.json
curl -s -H 'X-Account-Id: 15' "$B/locations/Site%20C/history?week=2026-07-20"    > $F/a15-history-siteC-0720.json
curl -s -H 'X-Account-Id: 6'  $B/weeks                                           > $F/a6-weeks.json
curl -s -H 'X-Account-Id: 6'  "$B/report?week=2026-06-01"                        > $F/a6-report-0601.json
curl -s -H 'X-Account-Id: 6'  "$B/report?week=2026-07-20"                        > $F/a6-report-0720.json
curl -s -H 'X-Account-Id: 6'  "$B/locations/Site%20G/history?week=2026-06-01"    > $F/a6-history-siteG-0601.json
curl -s -H 'X-Account-Id: 20' $B/weeks                                           > $F/a20-weeks.json
curl -s -H 'X-Account-Id: 20' $B/report                                          > $F/a20-report.json
curl -s -H 'X-Account-Id: 999' $B/weeks                                          > $F/err-account-not-found.json
curl -s -H 'X-Account-Id: 15' "$B/report?week=2026-01-05"                        > $F/err-invalid-week.json
# a15-summary-disabled.json: the AI summary flag must be off (the default); the key is the flag state
curl -s -X POST -H 'X-Account-Id: 15' -H 'Content-Type: application/json' -d '{"week":"2026-07-20"}' $B/summary > $F/a15-summary-disabled.json
```

Expected values in tests come from the plan's hand arithmetic (plans/T3 §2c, plans/T4 §2), never from these files.
