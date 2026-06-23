# =============================================================
# history_db.py — SQLITE HISTORY DATABASE OPERATIONS ONLY
# =============================================================
# This file handles connection, tables initialization, logging
# scans and querying stock score/price trends.
# =============================================================

import sqlite3
import os
from datetime import datetime

DB_FILE = "screener_history.db"

def get_connection():
    """Returns a SQLite connection with dict factory for easy access."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables if they do not exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Scans Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scanned_at TEXT NOT NULL,
            nifty_price REAL,
            nifty_change REAL,
            nifty_mood TEXT
        )
    """)

    # 2. History Records Table (Details per stock per scan)
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

    # Index for fast queries
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
    cursor = conn.cursor()

    try:
        scanned_at = summary.get("scanned_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        nifty = summary.get("nifty", {})
        nifty_price = nifty.get("price", 0.0)
        nifty_change = nifty.get("change", 0.0)
        nifty_mood = nifty.get("mood", "NEUTRAL")

        # Guard: skip if a scan already exists for today's date (prevent duplicates)
        cursor.execute("SELECT id FROM scans WHERE DATE(scanned_at) = DATE(?)", (scanned_at,))
        existing = cursor.fetchone()
        if existing:
            print(f"[history_db] Scan for {scanned_at[:10]} already exists (ID {existing['id']}) — updating instead of inserting duplicate.")
            # Update the existing scan's Nifty data
            cursor.execute(
                "UPDATE scans SET scanned_at=?, nifty_price=?, nifty_change=?, nifty_mood=? WHERE id=?",
                (scanned_at, nifty_price, nifty_change, nifty_mood, existing["id"])
            )
            scan_id = existing["id"]
            # Delete old records for this scan and re-insert fresh ones
            cursor.execute("DELETE FROM history_records WHERE scan_id=?", (scan_id,))
        else:
            # 1. Insert parent scan entry
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
            cursor.executemany("""
                INSERT INTO history_records (scan_id, sym, price, change, rsi, score, signal)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, stocks_to_insert)

        conn.commit()
        print(f"[history_db] Successfully saved scan ID {scan_id} to database history ({len(stocks_to_insert)} records).")
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
    cursor = conn.cursor()

    try:
        # Join to order by scan timestamp correctly
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


if __name__ == "__main__":
    # Test execution
    print("[history_db] Initializing database...")
    init_db()
    print("[history_db] Test database check complete.")
