"""Load data/seed.sql, unmodified, into the app database: `python -m app.seed`.

Destructive by design: it truncates both tables first, so running it twice ends in the same state.
`load_seed` is caller-managed (it opens and commits no transaction). The CLI wraps it in
`engine.begin()`, so a failure rolls the TRUNCATE back too: never a half-loaded database.
"""

from pathlib import Path

from sqlalchemy import Connection, text

from app.db import get_engine
from app.settings import settings


def load_seed(conn: Connection, path: Path | None = None) -> None:
    """Truncate both tables and execute the seed file on `conn`, inside the caller's transaction.

    The file is sent as one string with no parameters, so psycopg uses the simple-query protocol
    and runs every statement as written: no parsing or splitting on our side. The seed supplies
    explicit ids, so there are no sequences to reset.
    """
    sql = (path or settings.seed_path).read_text()
    conn.execute(text("TRUNCATE activity_events, accounts"))
    conn.exec_driver_sql(sql)


def main() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        load_seed(conn)
        accounts = conn.execute(text("SELECT count(*) FROM accounts")).scalar_one()
        events = conn.execute(text("SELECT count(*) FROM activity_events")).scalar_one()
    print(f"seed loaded: {accounts} accounts, {events} events")


if __name__ == "__main__":
    main()
