"""Small PostgreSQL helpers: one connection per request, committed on success."""

from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from .config import get_database_url


@contextmanager
def get_conn():
    conn = psycopg2.connect(get_database_url(), connect_timeout=3)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_all(conn, sql, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def fetch_one(conn, sql, params=None):
    rows = fetch_all(conn, sql, params)
    return rows[0] if rows else None
