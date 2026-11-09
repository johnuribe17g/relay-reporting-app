"""create the clean_events view

All aggregations read from this view, never from activity_events directly (PLAN §3).

* Normalize: btrim the text fields (explicit whitespace set: plain trim() strips only spaces),
  lower() on event_type only. location is NOT case-folded, so distinct sites never merge.
* Dedupe AFTER normalization, keeping the lowest id. PARTITION BY treats NULLs as equal, so two
  rows with NULL duration/outcome collapse, while NULL vs a value stays distinct. A self-join on
  "=" would silently keep NULL-bearing duplicates (NULL = NULL is unknown), which would miss
  every lead_created and appointment_set duplicate (their duration is always NULL).
* Expose local_ts / local_week once, using the double AT TIME ZONE: first label the stored
  value as UTC, then convert to the account zone. A single AT TIME ZONE converts the wrong way.
  date_trunc('week') is ISO Monday regardless of locale.
* No filter on event_type: unknown values stay visible so the data-quality test can catch them.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

CLEAN_EVENTS_SQL = r"""
CREATE VIEW clean_events AS
WITH normalized AS (
    SELECT e.id,
           e.account_id,
           btrim(e.location, E' \t\r\n')                  AS location,
           lower(btrim(e.event_type, E' \t\r\n'))         AS event_type,
           e.occurred_at,
           e.duration_seconds,
           btrim(e.outcome, E' \t\r\n')                   AS outcome
    FROM activity_events e
),
ranked AS (
    SELECT n.*,
           row_number() OVER (
               PARTITION BY account_id, location, event_type,
                            occurred_at, duration_seconds, outcome
               ORDER BY id
           ) AS rn
    FROM normalized n
)
SELECT r.id,
       r.account_id,
       r.location,
       r.event_type,
       r.occurred_at,
       r.duration_seconds,
       r.outcome,
       l.local_ts,
       date_trunc('week', l.local_ts)::date AS local_week
FROM ranked r
JOIN accounts a ON a.id = r.account_id
CROSS JOIN LATERAL (
    SELECT (r.occurred_at AT TIME ZONE 'UTC') AT TIME ZONE a.timezone AS local_ts
) l
WHERE r.rn = 1
"""


def upgrade() -> None:
    op.execute(CLEAN_EVENTS_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW clean_events")
