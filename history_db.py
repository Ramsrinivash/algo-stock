# =============================================================
# history_db.py — DUAL DATABASE OPERATIONS (POSTGRES / SQLITE)
# =============================================================
# This file handles connection, tables initialization, logging
# scans and querying stock score/price trends.
# Supports Postgres (via DATABASE_URL) and falls back to SQLite.
# =============================================================

import os
import sqlite3
from datetime import datetime

# Read DATABASE_URL for Postgres cloud migration
DATABASE_URL = os.environ.get("DATABASE_URL")

# Import Postgres packages if available
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None
    print("[history_db] WARNING: psycopg2-binary not installed. PostgreSQL mode will be unavailable.")

DB_FILE = "screener_history.db"

def get_connection():
    """Returns a database connection (PostgreSQL or SQLite)."""
    if DATABASE_URL:
        # PostgreSQL
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        # SQLite
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn

def get_cursor(conn):
    """Returns a database cursor with dict factory support."""
    if DATABASE_URL:
        # Returns a dict-like cursor for PostgreSQL
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        # Returns standard SQLite cursor
        return conn.cursor()


def init_db():
    """Initialize database tables if they do not exist."""
    conn = get_connection()
    cursor = get_cursor(conn)

    if DATABASE_URL:
        # PostgreSQL Schema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id SERIAL PRIMARY KEY,
                scanned_at VARCHAR(50) NOT NULL,
                nifty_price REAL,
                nifty_change REAL,
                nifty_mood VARCHAR(50)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history_records (
                id SERIAL PRIMARY KEY,
                scan_id INTEGER NOT NULL,
                sym VARCHAR(20) NOT NULL,
                price REAL,
                change REAL,
                rsi REAL,
                score INTEGER,
                signal VARCHAR(20),
                FOREIGN KEY (scan_id) REFERENCES scans (id) ON DELETE CASCADE
            )
        """)
    else:
        # SQLite Schema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scanned_at TEXT NOT NULL,
                nifty_price REAL,
                nifty_change REAL,
                nifty_mood TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER NOT NULL,
                sym TEXT NOT NULL,
                price REAL,
                change REAL,
                rsi REAL,
                score INTEGER,
                signal TEXT,
                FOREIGN KEY (scan_id) REFERENCES scans (id) ON DELETE CASCADE
            )
        """)

    # Scan cache table to prevent file resets on Render container restarts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS latest_scan_cache (
            id INTEGER PRIMARY KEY,
            json_data TEXT NOT NULL,
            updated_at VARCHAR(50) NOT NULL
        )
    """)

    # Index for fast queries (both SQLite and Postgres)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_sym ON history_records (sym)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_scan ON history_records (scan_id)")

    conn.commit()
    conn.close()


def save_scan_to_history(summary):
    """
    Log full scan summary details to the database.

    Args:
        summary : dict → containing scanned_at, nifty, and stocks list.
    """
    if not summary:
        return False

    init_db()  # Safety check

    conn = get_connection()
    cursor = get_cursor(conn)

    try:
        scanned_at = summary.get("scanned_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        nifty = summary.get("nifty", {})
        nifty_price = nifty.get("price", 0.0)
        nifty_change = nifty.get("change", 0.0)
        nifty_mood = nifty.get("mood", "NEUTRAL")

        # 1. Guard check & update/insert scans entry
        if DATABASE_URL:
            # Postgres: Cast scanned_at string to date for comparison
            cursor.execute(
                "SELECT id FROM scans WHERE CAST(scanned_at AS DATE) = CAST(%s AS DATE)",
                (scanned_at[:10],)
            )
            existing = cursor.fetchone()
            if existing:
                scan_id = existing["id"]
                cursor.execute(
                    "UPDATE scans SET scanned_at=%s, nifty_price=%s, nifty_change=%s, nifty_mood=%s WHERE id=%s",
                    (scanned_at, nifty_price, nifty_change, nifty_mood, scan_id)
                )
                cursor.execute("DELETE FROM history_records WHERE scan_id=%s", (scan_id,))
            else:
                cursor.execute("""
                    INSERT INTO scans (scanned_at, nifty_price, nifty_change, nifty_mood)
                    VALUES (%s, %s, %s, %s) RETURNING id
                """, (scanned_at, nifty_price, nifty_change, nifty_mood))
                scan_id = cursor.fetchone()["id"]
        else:
            # SQLite duplicate check
            cursor.execute("SELECT id FROM scans WHERE DATE(scanned_at) = DATE(?)", (scanned_at,))
            existing = cursor.fetchone()
            if existing:
                scan_id = existing["id"]
                cursor.execute(
                    "UPDATE scans SET scanned_at=?, nifty_price=?, nifty_change=?, nifty_mood=? WHERE id=?",
                    (scanned_at, nifty_price, nifty_change, nifty_mood, scan_id)
                )
                cursor.execute("DELETE FROM history_records WHERE scan_id=?", (scan_id,))
            else:
                cursor.execute("""
                    INSERT INTO scans (scanned_at, nifty_price, nifty_change, nifty_mood)
                    VALUES (?, ?, ?, ?)
                """, (scanned_at, nifty_price, nifty_change, nifty_mood))
                scan_id = cursor.lastrowid

        # 2. Insert detail rows for each stock with status == "ok"
        stocks_to_insert = []
        for s in summary.get("stocks", []):
            if s.get("status") == "ok":
                stocks_to_insert.append((
                    scan_id,
                    s["sym"].upper(),
                    s.get("price", 0.0),
                    s.get("change", 0.0),
                    s.get("rsi", 50.0),
                    s.get("score", 0),
                    s.get("signal", "AVOID")
                ))

        if stocks_to_insert:
            if DATABASE_URL:
                cursor.executemany("""
                    INSERT INTO history_records (scan_id, sym, price, change, rsi, score, signal)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, stocks_to_insert)
            else:
                cursor.executemany("""
                    INSERT INTO history_records (scan_id, sym, price, change, rsi, score, signal)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, stocks_to_insert)

        # 3. Persist the entire summary JSON as a backup cache
        import json
        json_str = json.dumps(summary)
        updated_at = scanned_at
        
        if DATABASE_URL:
            cursor.execute("""
                INSERT INTO latest_scan_cache (id, json_data, updated_at)
                VALUES (1, %s, %s)
                ON CONFLICT (id) DO UPDATE 
                SET json_data = EXCLUDED.json_data, updated_at = EXCLUDED.updated_at
            """, (json_str, updated_at))
        else:
            cursor.execute("""
                INSERT OR REPLACE INTO latest_scan_cache (id, json_data, updated_at)
                VALUES (1, ?, ?)
            """, (json_str, updated_at))

        conn.commit()
        print(f"[history_db] Successfully saved scan ID {scan_id} and updated latest_scan_cache ({len(stocks_to_insert)} records).")
        return True

    except Exception as e:
        print(f"[history_db] ERROR saving scan to history: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def get_score_history(sym, limit=15):
    """
    Fetch the historical scores and prices for a symbol.

    Args:
        sym : str   → stock symbol e.g., "HDFCBANK"
        limit : int → maximum records to retrieve

    Returns:
        list of dicts → sorted from oldest to newest scan
    """
    sym = sym.strip().upper()
    conn = get_connection()
    cursor = get_cursor(conn)

    try:
        if DATABASE_URL:
            cursor.execute("""
                SELECT s.scanned_at, r.score, r.price, r.signal, r.rsi
                FROM history_records r
                JOIN scans s ON r.scan_id = s.id
                WHERE r.sym = %s
                ORDER BY s.scanned_at DESC
                LIMIT %s
            """, (sym, limit))
        else:
            cursor.execute("""
                SELECT s.scanned_at, r.score, r.price, r.signal, r.rsi
                FROM history_records r
                JOIN scans s ON r.scan_id = s.id
                WHERE r.sym = ?
                ORDER BY s.scanned_at DESC
                LIMIT ?
            """, (sym, limit))

        rows = cursor.fetchall()
        
        # Convert to list of dicts
        history = [dict(row) for row in rows]
        
        # Reverse to get chronological order (oldest to newest)
        history.reverse()
        return history

    except Exception as e:
        print(f"[history_db] ERROR fetching history for {sym}: {e}")
        return []
    finally:
        conn.close()


def load_latest_scan_cache():
    """Retrieve the persistently cached scan data from database."""
    init_db()  # Ensure table exists
    conn = get_connection()
    cursor = get_cursor(conn)
    try:
        cursor.execute("SELECT json_data FROM latest_scan_cache WHERE id = 1")
        row = cursor.fetchone()
        if row:
            import json
            return json.loads(row["json_data"])
        return None
    except Exception as e:
        print(f"[history_db] Error loading scan cache from DB: {e}")
        return None
    finally:
        conn.close()


if __name__ == "__main__":
    print("[history_db] Initializing database...")
    init_db()
    print("[history_db] Test database check complete.")
