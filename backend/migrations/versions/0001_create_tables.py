"""create accounts and activity_events

Same schema as data/schema.sql (already valid PostgreSQL 16), expressed as Alembic operations
with named constraints, plus the composite index from PLAN §7.

Deliberately NOT added, because each would reject rows in the unmodified seed or hide a
data-quality problem: a UNIQUE over the payload columns (12 exact duplicate pairs), a CHECK on
event_type (unknown types must load and be caught by the data-quality test), NOT NULL on
outcome/duration_seconds, a CHECK on timezone, and a locations table.

Ids are plain INTEGER primary keys (autoincrement=False: no serial, no identity) because the
seed supplies explicit ids. occurred_at/created_at stay TIMESTAMP WITHOUT TIME ZONE holding UTC.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("industry", sa.String(60), nullable=False),
        sa.Column("timezone", sa.String(60), nullable=False),  # IANA name
        sa.Column("created_at", sa.TIMESTAMP(timezone=False), nullable=False),  # UTC
        sa.PrimaryKeyConstraint("id", name="pk_accounts"),
    )
    op.create_table(
        "activity_events",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("location", sa.String(80), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=False), nullable=False),  # UTC
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(40), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_activity_events"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name="fk_activity_events_account_id"
        ),
    )
    op.create_index(
        "ix_activity_events_account_id_occurred_at",
        "activity_events",
        ["account_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_activity_events_account_id_occurred_at", table_name="activity_events")
    op.drop_table("activity_events")
    op.drop_table("accounts")
