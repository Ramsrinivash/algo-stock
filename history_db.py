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
psycopg2_import_error = None
try:
    import psycopg2
    import psycopg2.extras
except Exception as e:
    psycopg2 = None
    psycopg2_import_error = str(e)
    print(f"[history_db] WARNING: psycopg2 import failed: {e}")

USING_POSTGRES = (DATABASE_URL is not None) and (psycopg2 is not None)
DB_FILE = "screener_history.db"

def get_connection():
    """Returns a database connection (PostgreSQL or SQLite)."""
    if USING_POSTGRES:
        # PostgreSQL
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        # SQLite — enable foreign key enforcement (required for ON DELETE CASCADE)
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def get_cursor(conn):
    """Returns a database cursor with dict factory support."""
    if USING_POSTGRES:
        # Returns a dict-like cursor for PostgreSQL
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        # Returns standard SQLite cursor
        return conn.cursor()


def init_db():
    """Initialize database tables if they do not exist."""
    conn = get_connection()
    cursor = get_cursor(conn)

    if USING_POSTGRES:
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

    # Settings cache table to prevent config resets on restarts/deploys (Render ephemeral fix)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings_cache (
            id INTEGER PRIMARY KEY,
            json_data TEXT NOT NULL,
            updated_at VARCHAR(50) NOT NULL
        )
    """)

    # Watchlist Alerts table
    if USING_POSTGRES:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist_alerts (
                id SERIAL PRIMARY KEY,
                sym VARCHAR(20) NOT NULL,
                yahoo VARCHAR(20) NOT NULL,
                target_price REAL NOT NULL,
                alert_condition VARCHAR(10) NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                triggered_at TIMESTAMP NULL
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sym TEXT NOT NULL,
                yahoo TEXT NOT NULL,
                target_price REAL NOT NULL,
                alert_condition TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                triggered_at TEXT NULL
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

    # H1 fix: init_db() removed from here — called once at startup in app.py
    # Calling CREATE TABLE IF NOT EXISTS on every scan is wasteful
    conn = get_connection()
    cursor = get_cursor(conn)

    try:
        scanned_at = summary.get("scanned_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        nifty = summary.get("nifty", {})
        nifty_price = nifty.get("price", 0.0)
        nifty_change = nifty.get("change", 0.0)
        nifty_mood = nifty.get("mood", "NEUTRAL")

        # 1. Guard check & update/insert scans entry
        if USING_POSTGRES:
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
            if USING_POSTGRES:
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
        
        if USING_POSTGRES:
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
        if USING_POSTGRES:
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


def has_scan_run_today():
    """Checks if a scan has already been recorded for the current day in IST."""
    from datetime import datetime, timezone, timedelta
    utc_now = datetime.now(timezone.utc)
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    current_date = ist_now.strftime("%Y-%m-%d")
    
    conn = get_connection()
    cursor = get_cursor(conn)
    try:
        if USING_POSTGRES:
            # PostgreSQL
            cursor.execute("SELECT id FROM scans WHERE CAST(scanned_at AS DATE) = CAST(%s AS DATE)", (current_date,))
        else:
            # SQLite
            cursor.execute("SELECT id FROM scans WHERE DATE(scanned_at) = DATE(?)", (current_date,))
        row = cursor.fetchone()
        return row is not None
    except Exception as e:
        print(f"[history_db] Error checking if scan run today: {e}")
        return False
    finally:
        conn.close()


def add_watchlist_alert(sym, yahoo, target_price, condition):
    """Add a new alert to the watchlist."""
    init_db()
    conn = get_connection()
    cursor = get_cursor(conn)
    try:
        if USING_POSTGRES:
            cursor.execute("""
                INSERT INTO watchlist_alerts (sym, yahoo, target_price, alert_condition)
                VALUES (%s, %s, %s, %s)
            """, (sym.upper(), yahoo, float(target_price), condition.upper()))
        else:
            cursor.execute("""
                INSERT INTO watchlist_alerts (sym, yahoo, target_price, alert_condition)
                VALUES (?, ?, ?, ?)
            """, (sym.upper(), yahoo, float(target_price), condition.upper()))
        conn.commit()
        return True
    except Exception as e:
        print(f"[history_db] Error adding watchlist alert: {e}")
        return False
    finally:
        conn.close()

def get_watchlist_alerts():
    """Get all watchlist alerts (both active and triggered)."""
    init_db()
    conn = get_connection()
    cursor = get_cursor(conn)
    try:
        cursor.execute("SELECT * FROM watchlist_alerts ORDER BY created_at DESC")
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append(dict(r))
        return result
    except Exception as e:
        print(f"[history_db] Error fetching watchlist alerts: {e}")
        return []
    finally:
        conn.close()

def delete_watchlist_alert(alert_id):
    """Delete a watchlist alert by ID."""
    conn = get_connection()
    cursor = get_cursor(conn)
    try:
        if USING_POSTGRES:
            cursor.execute("DELETE FROM watchlist_alerts WHERE id = %s", (alert_id,))
        else:
            cursor.execute("DELETE FROM watchlist_alerts WHERE id = ?", (alert_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"[history_db] Error deleting watchlist alert: {e}")
        return False
    finally:
        conn.close()

def get_active_watchlist_alerts():
    """Get only active watchlist alerts."""
    init_db()
    conn = get_connection()
    cursor = get_cursor(conn)
    try:
        cursor.execute("SELECT * FROM watchlist_alerts WHERE is_active = 1")
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append(dict(r))
        return result
    except Exception as e:
        print(f"[history_db] Error fetching active alerts: {e}")
        return []
    finally:
        conn.close()

def mark_watchlist_alert_triggered(alert_id):
    """Mark a watchlist alert as triggered."""
    conn = get_connection()
    cursor = get_cursor(conn)
    try:
        if USING_POSTGRES:
            cursor.execute("""
                UPDATE watchlist_alerts 
                SET is_active = 0, triggered_at = CURRENT_TIMESTAMP 
                WHERE id = %s
            """, (alert_id,))
        else:
            cursor.execute("""
                UPDATE watchlist_alerts 
                SET is_active = 0, triggered_at = datetime('now', 'localtime') 
                WHERE id = ?
            """, (alert_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"[history_db] Error triggering watchlist alert: {e}")
        return False
    finally:
        conn.close()

def save_settings_to_db(settings_dict):
    """Persist settings dict to database cache to survive server restarts/deploys."""
    init_db()
    conn = get_connection()
    cursor = get_cursor(conn)
    try:
        import json
        json_str = json.dumps(settings_dict)
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if USING_POSTGRES:
            cursor.execute("""
                INSERT INTO settings_cache (id, json_data, updated_at)
                VALUES (1, %s, %s)
                ON CONFLICT (id) DO UPDATE 
                SET json_data = EXCLUDED.json_data, updated_at = EXCLUDED.updated_at
            """, (json_str, updated_at))
        else:
            cursor.execute("""
                INSERT OR REPLACE INTO settings_cache (id, json_data, updated_at)
                VALUES (1, ?, ?)
            """, (json_str, updated_at))
        conn.commit()
        return True
    except Exception as e:
        print(f"[history_db] Error saving settings cache to DB: {e}")
        return False
    finally:
        conn.close()

def load_settings_from_db():
    """Retrieve the persistently cached settings from database."""
    init_db()
    conn = get_connection()
    cursor = get_cursor(conn)
    try:
        cursor.execute("SELECT json_data FROM settings_cache WHERE id = 1")
        row = cursor.fetchone()
        if row:
            import json
            return json.loads(row["json_data"])
        return None
    except Exception as e:
        print(f"[history_db] Error loading settings cache from DB: {e}")
        return None
    finally:
        conn.close()


if __name__ == "__main__":
    print("[history_db] Initializing database...")
    init_db()
    print("[history_db] Test database check complete.")
