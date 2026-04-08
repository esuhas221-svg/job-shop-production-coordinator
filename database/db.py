import os
from contextlib import contextmanager

DB_TYPE = os.getenv("DB_TYPE", "sqlite")   # change to "alloydb" if needed

if DB_TYPE == "alloydb":
    import psycopg2
    from psycopg2 import pool
    ALLOYDB_CONFIG = {
        "host": os.getenv("ALLOYDB_HOST", "localhost"),
        "port": os.getenv("ALLOYDB_PORT", "5432"),
        "database": os.getenv("ALLOYDB_DB", "jobshopdb"),
        "user": os.getenv("ALLOYDB_USER", "postgres"),
        "password": os.getenv("ALLOYDB_PASSWORD", "")
    }
    _pool = None
    def get_connection():
        global _pool
        if _pool is None:
            _pool = psycopg2.pool.SimpleConnectionPool(1, 10, **ALLOYDB_CONFIG)
        return _pool.getconn()
    def return_connection(conn):
        _pool.putconn(conn)
    @contextmanager
    def get_cursor():
        conn = get_connection()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            return_connection(conn)
else:
    import sqlite3
    DB_PATH = os.getenv("SQLITE_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "jobshop.db"))
    @contextmanager
    def get_cursor():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

def init_db():
    with get_cursor() as cur:
        if DB_TYPE == "alloydb":
            cur.execute("CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, order_no TEXT UNIQUE, customer TEXT, part_no TEXT, quantity INTEGER, due_date TEXT, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            cur.execute("CREATE TABLE IF NOT EXISTS inventory (id SERIAL PRIMARY KEY, part_no TEXT, material TEXT, thickness TEXT, stock_qty INTEGER, reorder_level INTEGER)")
            cur.execute("CREATE TABLE IF NOT EXISTS machines (id SERIAL PRIMARY KEY, name TEXT, type TEXT, available BOOLEAN DEFAULT TRUE)")
            cur.execute("CREATE TABLE IF NOT EXISTS work_orders (id SERIAL PRIMARY KEY, order_id INTEGER, operation TEXT, machine TEXT, start_time TEXT, end_time TEXT, status TEXT)")
            cur.execute("CREATE TABLE IF NOT EXISTS dispatch_log (id SERIAL PRIMARY KEY, order_id INTEGER, invoice_no TEXT, dispatched_at TIMESTAMP)")
        else:
            cur.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, order_no TEXT UNIQUE, customer TEXT, part_no TEXT, quantity INTEGER, due_date TEXT, status TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
            cur.execute("CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, part_no TEXT, material TEXT, thickness TEXT, stock_qty INTEGER, reorder_level INTEGER)")
            cur.execute("CREATE TABLE IF NOT EXISTS machines (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, type TEXT, available BOOLEAN DEFAULT 1)")
            cur.execute("CREATE TABLE IF NOT EXISTS work_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, operation TEXT, machine TEXT, start_time TEXT, end_time TEXT, status TEXT)")
            cur.execute("CREATE TABLE IF NOT EXISTS dispatch_log (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, invoice_no TEXT, dispatched_at TEXT)")
    print("✅ Database tables ready")
