import os
import psycopg2
import psycopg2.extras
from psycopg2 import pool
from contextlib import contextmanager

_pool = None

def _get_pool():
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(
            1, 10,
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT', 5432)),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return _pool

@contextmanager
def get_db():
    conn = _get_pool().getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _get_pool().putconn(conn)

def execute(sql: str, params=None) -> list:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            try:
                return [dict(row) for row in cur.fetchall()]
            except psycopg2.ProgrammingError:
                return []

def execute_one(sql: str, params=None):
    rows = execute(sql, params)
    return rows[0] if rows else None
