from __future__ import annotations

import contextlib
import sqlite3
from config import DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    # SQLite does not enforce ON DELETE CASCADE unless this is enabled on every connection.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextlib.contextmanager
def db_cursor():
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
