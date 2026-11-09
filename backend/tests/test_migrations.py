from typing import Any

from sqlalchemy import Connection, create_engine, text

from app.settings import settings
from tests import db_utils

TABLES = ("accounts", "activity_events")
VIEW = "clean_events"
EXPECTED_INDEX = "ix_activity_events_account_id_occurred_at"

COLUMNS_SQL = text(
    """
    SELECT table_name, column_name, data_type, is_nullable, character_maximum_length,
           column_default, is_identity, ordinal_position
    FROM information_schema.columns
    WHERE table_schema = :schema AND table_name IN ('accounts', 'activity_events')
    ORDER BY table_name, ordinal_position
    """
)
PK_SQL = text(
    """
    SELECT tc.table_name, kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
    WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = :schema
      AND tc.table_name IN ('accounts', 'activity_events')
    ORDER BY tc.table_name, kcu.ordinal_position
    """
)
FK_SQL = text(
    """
    SELECT cl.relname, a.attname, rc.relname, fa.attname
    FROM pg_constraint c
    JOIN pg_class cl ON cl.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = cl.relnamespace
    JOIN pg_class rc ON rc.oid = c.confrelid
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
    JOIN pg_attribute fa ON fa.attrelid = c.confrelid AND fa.attnum = c.confkey[1]
    WHERE c.contype = 'f' AND n.nspname = :schema
    ORDER BY cl.relname
    """
)
NON_PK_INDEXES_SQL = text(
    """
    SELECT indexname FROM pg_indexes
    WHERE schemaname = :schema AND tablename IN ('accounts', 'activity_events')
      AND indexname NOT LIKE '%pkey' AND indexname NOT LIKE 'pk\\_%'
    ORDER BY indexname
    """
)


def _rows(conn: Connection, sql: Any, schema: str) -> list[tuple[Any, ...]]:
    return [tuple(r) for r in conn.execute(sql, {"schema": schema})]


def test_migrated_tables_are_faithful_to_schema_sql(conn: Connection) -> None:
    """Load data/schema.sql (read-only text) into a scratch schema and compare structures."""
    schema_sql = (settings.seed_path.parent / "schema.sql").read_text()
    conn.execute(text("CREATE SCHEMA ref"))
    conn.execute(text("SET LOCAL search_path TO ref"))
    conn.exec_driver_sql(schema_sql)  # no parameters: multi-statement simple query

    for sql in (COLUMNS_SQL, PK_SQL, FK_SQL):
        migrated = _rows(conn, sql, "public")
        reference = _rows(conn, sql, "ref")
        assert reference, "reference schema produced no rows: the comparison would be vacuous"
        assert migrated == reference

    # The only allowed difference: the extra index from PLAN §7.
    assert _rows(conn, NON_PK_INDEXES_SQL, "ref") == []
    assert _rows(conn, NON_PK_INDEXES_SQL, "public") == [(EXPECTED_INDEX,)]


def test_ids_have_no_default(conn: Connection) -> None:
    """Plain INTEGER PKs (no serial/identity), because the seed inserts explicit ids."""
    rows = conn.execute(
        text(
            """
            SELECT table_name, column_default, is_identity FROM information_schema.columns
            WHERE table_schema = 'public' AND column_name = 'id'
              AND table_name IN ('accounts', 'activity_events')
            """
        )
    ).all()
    assert sorted(tuple(r) for r in rows) == [
        ("accounts", None, "NO"),
        ("activity_events", None, "NO"),
    ]


def test_composite_index_present(conn: Connection) -> None:
    indexdef = conn.execute(
        text("SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' AND indexname = :n"),
        {"n": EXPECTED_INDEX},
    ).scalar_one()
    assert indexdef.endswith("USING btree (account_id, occurred_at)")


def test_constraints_do_not_reject_messy_rows(conn: Connection) -> None:
    """Unknown type, NULL outcome and an exact duplicate must all load (PLAN §3, §7)."""
    conn.execute(
        text(
            "INSERT INTO accounts VALUES "
            "(1, 'A', 'Dental', 'America/Chicago', '2025-01-01 00:00:00')"
        )
    )
    insert = text(
        "INSERT INTO activity_events VALUES "
        "(:id, 1, 'Site A', :type, '2026-02-03 15:00:00', NULL, NULL)"
    )
    conn.execute(insert, {"id": 1, "type": "phone_call"})  # unknown event_type, NULL outcome
    conn.execute(insert, {"id": 2, "type": "call_received"})
    conn.execute(insert, {"id": 3, "type": "call_received"})  # exact duplicate of id 2
    assert conn.execute(text("SELECT count(*) FROM activity_events")).scalar_one() == 3


def test_migration_round_trip(migrations_db_url: str) -> None:
    """upgrade -> downgrade base -> upgrade, in its own throwaway database."""

    def existing() -> set[str]:
        """Names of our tables and view that currently exist."""
        engine = create_engine(migrations_db_url)
        try:
            with engine.connect() as c:
                rows = c.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
                return {r[0] for r in rows} & {*TABLES, VIEW}
        finally:
            engine.dispose()

    assert db_utils.assert_test_database("relay_migrations_test")
    db_utils.upgrade(migrations_db_url)
    assert existing() == {*TABLES, VIEW}

    db_utils.downgrade(migrations_db_url, "0001")  # undo 0002 only
    assert existing() == set(TABLES)  # the view is gone, the tables remain

    db_utils.downgrade(migrations_db_url, "base")
    assert existing() == set()

    db_utils.upgrade(migrations_db_url)
    assert existing() == {*TABLES, VIEW}
