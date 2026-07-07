# =============================================================
# app.py — FLASK SERVER & API ROUTES ONLY
# =============================================================
# This file ONLY handles HTTP routes and serves the frontend.
# No scanning logic, no indicators, no patterns here.
#
# If you want to add a new API route  → add ONLY in this file.
# If you want to change port          → change PORT below.
# If you want to add authentication   → add ONLY in this file.
#
# Routes:
#   GET  /                    → serves frontend/index.html
#   GET  /api/scan            → runs full scan, returns JSON
#   GET  /api/data            → returns last screener_data.json
#   GET  /api/nifty           → returns Nifty 50 live data
#   GET  /api/stock/<sym>     → returns single stock data
#   GET  /api/status          → server health check
#
# HOW TO RUN:
#   pip install flask
#   python app.py
#
# Then open browser:
#   http://localhost:5000
# =============================================================

import sys
import io

# Force UTF-8 encoding on standard output/error to prevent UnicodeEncodeErrors on Windows
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import json
import os
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, send_from_directory, request
from functools import wraps

from scanner import run_full_scan, scan_one
from fetcher import fetch_nifty
from stocks  import STOCKS, NIFTY_SYM

# ── CONFIG ────────────────────────────────────────────────────
PORT        = int(os.environ.get("PORT", 5000))
DEBUG       = os.environ.get("DEBUG", "False").lower() in ("true", "1", "t")
DATA_FILE   = "screener_data.json"
FRONTEND    = "frontend"              # folder with index.html

app = Flask(__name__, static_folder=FRONTEND)

# ── AUTHENTICATION DECORATOR ──────────────────────────────────
def require_password(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        import alert_bot
        s = alert_bot.load_settings()
        correct_pwd = os.environ.get("SCREENER_PASSCODE") or s.get("settings_password", "5001")
        
        # Check header first
        provided_pwd = request.headers.get("X-Api-Password")
        # Fallback to query parameter (e.g., /api/scan?password=5001) for easy cron-job integration
        if not provided_pwd:
            provided_pwd = request.args.get("password") or request.args.get("api_password") or request.args.get("X-Api-Password")
            
        if provided_pwd != correct_pwd:
            return jsonify({"status": "error", "message": "Unauthorized: Password incorrect or missing."}), 401
        return f(*args, **kwargs)
    return decorated_function

# Disable caching for static files during development/testing
@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r


# ── HELPER ────────────────────────────────────────────────────
def load_data_file():
    """
    Load screener_data.json if it exists.
    If the file is missing (e.g. Render restart), fall back to loading from database.
    """
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            # AP4 fix: log what went wrong instead of silently ignoring it
            print(f"[app] Warning: screener_data.json could not be read ({e}). Falling back to DB.")

    # Recovery: Load from database cache if local file is missing/corrupted
    try:
        import history_db
        db_data = history_db.load_latest_scan_cache()
        if db_data:
            print("[app] Restored screener_data.json from PostgreSQL database cache.")
            # Cache it locally for subsequent fast reads
            with open(DATA_FILE, "w") as f:
                json.dump(db_data, f, indent=2)
            return db_data
    except Exception as e:
        print(f"[app] Error recovering data file from DB: {e}")

    return None


import threading
import pandas as pd

# Global variables for background scanning
scan_lock = threading.Lock()
scan_progress = {
    "is_scanning": False,
    "current": 0,
    "total": 0,
    "symbol": ""
}

def background_scan_task(stocks_list, capital):
    global scan_progress
    def progress_cb(current, total, symbol):
        scan_progress["current"] = current
        scan_progress["total"] = total
        scan_progress["symbol"] = symbol

    try:
        run_full_scan(
            stocks_list=stocks_list,
            capital=capital,
            verbose=True,
            progress_callback=progress_cb
        )
    except Exception as e:
        print(f"[app] Background scan error: {e}")
    finally:
        with scan_lock:
            scan_progress["is_scanning"] = False

def get_ist_time():
    utc_now = datetime.now(timezone.utc)
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    return ist_now

def keep_awake_and_schedule_loop():
    global scan_progress
    import requests
    import time
    
    # Wait 30 seconds after server starts before starting loops/pings
    time.sleep(30)
    
    external_url = os.environ.get("RENDER_EXTERNAL_URL", "")
    if not external_url:
        external_url = f"http://127.0.0.1:{PORT}"
        
    print(f"[scheduler] Keep-awake scheduler active. Target URL: {external_url}", flush=True)
    
    last_ping_time = time.time()
    
    while True:
        try:
            # 1. Self-ping every 13 minutes to keep Render instance awake
            now_time = time.time()
            if now_time - last_ping_time >= 13 * 60:
                last_ping_time = now_time
                print(f"[scheduler] Sending keep-awake ping to {external_url}/api/status", flush=True)
                resp = requests.get(f"{external_url}/api/status", timeout=15)
                print(f"[scheduler] Keep-awake ping response status: {resp.status_code}", flush=True)
                
            # Load settings dynamically to fetch target scan hour
            try:
                import alert_bot
                settings = alert_bot.load_settings()
                scan_hour = settings.get("scan_hour", 17)
                scan_hour = int(scan_hour)
            except Exception:
                scan_hour = 17

            # 2. Check if it's the daily scan hour or later for daily scan
            ist_now = get_ist_time()
            if ist_now.hour >= scan_hour:
                current_date = ist_now.strftime("%Y-%m-%d")
                
                # File locking to prevent double execution under multi-worker gunicorn deployments
                lock_file = "daily_scan.lock"
                already_run = False
                if os.path.exists(lock_file):
                    try:
                        with open(lock_file, "r") as lf:
                            lock_date = lf.read().strip()
                        if lock_date == current_date:
                            already_run = True
                    except Exception:
                        pass
                        
                # Check database as a persistent backup if local lock is missing
                if not already_run:
                    try:
                        import history_db
                        if history_db.has_scan_run_today():
                            already_run = True
                            # Update local lock to prevent database queries in subsequent loops
                            with open(lock_file, "w") as lf:
                                lf.write(current_date)
                    except Exception as db_err:
                        print(f"[scheduler] DB check error: {db_err}", flush=True)
                        
                if not already_run:
                    try:
                        with open(lock_file, "w") as lf:
                            lf.write(current_date)
                    except Exception as le:
                        print(f"[scheduler] Lock file write error: {le}", flush=True)
                        
                    print(f"[scheduler] Starting daily automated scan (after 5:00 PM IST) for date: {current_date}", flush=True)
                    
                    import stock_manager
                    stocks_to_scan = stock_manager.get_all_stocks(STOCKS)
                    
                    with scan_lock:
                        scan_progress["is_scanning"] = True
                        scan_progress["current"] = 0
                        scan_progress["total"] = 0
                        scan_progress["symbol"] = ""
                        
                    t = threading.Thread(target=background_scan_task, args=(stocks_to_scan, 100000))
                    t.daemon = True
                    t.start()
        except Exception as ex:
            print(f"[scheduler] Loop exception: {ex}", flush=True)
            
        time.sleep(30) # check time every 30 seconds

# Call init_db once at startup so tables are ready before any scan runs (H1 companion fix)
try:
    import history_db as _hdb
    _hdb.init_db()
except Exception as _e:
    print(f"[app] Warning: DB init failed: {_e}")

# Start keep-awake scheduler thread on app initialization
scheduler_thread = threading.Thread(target=keep_awake_and_schedule_loop)
scheduler_thread.daemon = True
scheduler_thread.start()

def stocks_dict():
    """Convert STOCKS list (merged with custom list) to dict for quick lookup by sym."""
    import stock_manager
    merged = stock_manager.get_all_stocks(STOCKS)
    return {s[0]: {"yahoo": s[1], "name": s[2], "sector": s[3]}
            for s in merged}


# ── ROUTES ────────────────────────────────────────────────────

# ── Serve Frontend ────────────────────────────────────────────
@app.route("/")
def index():
    """Serve the main screener HTML page."""
    return send_from_directory(FRONTEND, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    """Serve CSS, JS and other static files from frontend/."""
    return send_from_directory(FRONTEND, filename)


# ── API: Full Scan ────────────────────────────────────────────
@app.route("/api/scan")
@require_password
def api_scan():
    """
    Run a full scan of all stocks in the background.
    Fetches fresh data from Yahoo Finance.
    Saves result to screener_data.json.
    Returns JSON.

    Query params:
        capital : int -> trading capital (default 100000)
    """
    global scan_progress
    capital = int(request.args.get("capital", 100000))

    with scan_lock:
        if scan_progress["is_scanning"]:
            return jsonify({
                "status": "scanning",
                "message": "A scan is already in progress.",
                "progress": scan_progress
            }), 409

        scan_progress["is_scanning"] = True
        scan_progress["current"] = 0
        scan_progress["total"] = 0
        scan_progress["symbol"] = ""

    # Get dynamic stock list
    import stock_manager
    stocks_to_scan = stock_manager.get_all_stocks(STOCKS)

    # Start scanning thread
    t = threading.Thread(target=background_scan_task, args=(stocks_to_scan, capital))
    t.daemon = True
    t.start()

    return jsonify({
        "status": "ok",
        "message": "Scan started in background.",
        "total_stocks": len(stocks_to_scan)
    })


# ── API: Scan Status ───────────────────────────────────────────────
@app.route("/api/scan/status")
def api_scan_status():
    """Return the progress status of the background scan (thread-safe read)."""
    global scan_progress
    with scan_lock:                      # guard against torn reads from background thread
        progress_copy = dict(scan_progress)
    return jsonify(progress_copy)


# ── API: Get Last Scan Data ───────────────────────────────────
@app.route("/api/data")
def api_data():
    """
    Return the last saved screener_data.json.
    Much faster than /api/scan — no Yahoo fetch needed.
    Use this when the screener HTML loads.

    Returns:
        JSON → full screener data or error if no scan yet
    """
    data = load_data_file()

    if data is None:
        return jsonify({
            "status":  "no_data",
            "message": "No scan data yet. Run /api/scan first.",
            "stocks":  []
        }), 404

    return jsonify({
        "status": "ok",
        "data":   data
    })


# ── API: Nifty Live ───────────────────────────────────────────
@app.route("/api/nifty")
def api_nifty():
    """
    Fetch live Nifty 50 value from Yahoo Finance.
    Fast call — used to update Market Mood in real time.

    Returns:
        JSON → price, change%, mood, advice
    """
    nifty = fetch_nifty(NIFTY_SYM)

    if nifty["status"] == "ok":
        chg  = nifty["change"]
        mood = "BULLISH"  if chg >=  0.5 else \
               "NEUTRAL"  if chg >= -0.3 else \
               "CAUTIOUS" if chg >= -1.0 else "BEARISH"
        advice = {
            "BULLISH":  "Buy quality dips",
            "NEUTRAL":  "Wait and watch",
            "CAUTIOUS": "Reduce position size",
            "BEARISH":  "Stay in cash today"
        }[mood]
        return jsonify({
            "status": "ok",
            "price":  nifty["price"],
            "change": nifty["change"],
            "mood":   mood,
            "advice": advice
        })

    return jsonify({
        "status":  "error",
        "message": nifty.get("error", "Failed to fetch Nifty")
    }), 500


# ── API: Single Stock ─────────────────────────────────────────
@app.route("/api/stock/<sym>")
def api_stock(sym):
    """
    Scan and return data for a single stock.
    Useful for refreshing one stock without full scan.

    Args:
        sym : str → stock ID e.g. "HDFCBANK"

    Example:
        GET /api/stock/HDFCBANK
        GET /api/stock/BEL?capital=20000

    Returns:
        JSON → full stock data
    """
    capital   = int(request.args.get("capital", 100000))
    sym       = sym.upper()
    stocks    = stocks_dict()

    if sym not in stocks:
        return jsonify({
            "status":  "error",
            "message": f"Symbol '{sym}' not found in stocks list"
        }), 404

    info  = stocks[sym]
    stock = scan_one(
        sym       = sym,
        yahoo_sym = info["yahoo"],
        name      = info["name"],
        sector    = info["sector"],
        capital   = capital
    )

    if stock["status"] == "ok":
        return jsonify({"status": "ok", "stock": stock})

    return jsonify({
        "status":  "error",
        "message": stock.get("error", "Scan failed")
    }), 500


# ── API: Top 10 Picks ─────────────────────────────────────────
@app.route("/api/top10")
def api_top10():
    """
    Return top 10 stocks with BUY or STRONG BUY signals.
    Sorted by score descending.
    """
    data = load_data_file()

    if data is None:
        return jsonify({
            "status":  "no_data",
            "message": "No scan data yet. Run /api/scan first.",
            "stocks":  []
        }), 404

    buys = [
        s for s in data.get("stocks", [])
        if s.get("signal") in ["BUY", "STRONG BUY"]
    ]

    # Sort by score descending and take top 10
    buys.sort(key=lambda x: x.get("score", 0), reverse=True)
    top_picks = buys[:10]

    return jsonify({
        "status": "ok",
        "stocks": top_picks
    })


# ── API: Status Check ─────────────────────────────────────────
@app.route("/api/status")
def api_status():
    """
    Health check endpoint.
    Returns server status and last scan time.
    Used by Railway.app to verify the server is alive.
    """
    import stock_manager
    data        = load_data_file()
    last_scan   = data.get("scanned_at", "Never") if data else "Never"
    stock_count = len(data.get("stocks", [])) if data else 0
    total_len   = len(stock_manager.get_all_stocks(STOCKS))

    return jsonify({
        "status":      "ok",
        "server":      "Finrio AI API",
        "time":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_scan":   last_scan,
        "stocks_in_db":stock_count,
        "total_stocks":total_len,
        "routes": {
            "GET /":                      "Frontend screener HTML",
            "GET /api/scan":              "Run background full scan",
            "GET /api/scan/status":       "Background scan status",
            "GET /api/data":              "Last scan results (fast)",
            "GET /api/nifty":             "Live Nifty 50",
            "GET /api/stock/SYM":         "Single stock scan",
            "GET /api/stock/SYM/history": "Historical daily chart data (EMA 9/21/50)",
            "GET /api/stock/SYM/score-history": "Historical score trend (SQLite)",
            "GET /api/custom-stocks":     "List dynamic tickers",
            "POST /api/custom-stocks":    "Add dynamic ticker",
            "DELETE /api/custom-stocks/SYM": "Delete dynamic ticker",
            "GET /api/status":            "This health check details"
        }
    })


# ── API: Verify Password ──────────────────────────────────────
@app.route("/api/verify-password", methods=["POST"])
def api_verify_password():
    """Verify passcode on the backend."""
    import alert_bot
    s = alert_bot.load_settings()
    correct_pwd = os.environ.get("SCREENER_PASSCODE") or s.get("settings_password", "5001")
    
    data = request.json or {}
    pwd = data.get("password", "")
    if str(pwd) == str(correct_pwd):
        return jsonify({"status": "ok", "message": "Access granted."})
    return jsonify({"status": "error", "message": "Incorrect passcode."}), 401


# ── API: Dynamic Custom Stock List APIs ───────────────────────
@app.route("/api/custom-stocks")
@require_password
def api_get_custom():
    import stock_manager
    return jsonify(stock_manager.list_custom())


@app.route("/api/custom-stocks", methods=["POST"])
@require_password
def api_add_custom():
    import stock_manager
    data = request.json or {}
    res = stock_manager.add_stock(
        sym=data.get("sym", ""),
        yahoo=data.get("yahoo", ""),
        name=data.get("name", ""),
        sector=data.get("sector", "")
    )
    if res["status"] == "ok":
        return jsonify(res)
    return jsonify(res), 400


@app.route("/api/custom-stocks/<sym>", methods=["DELETE"])
@require_password
def api_delete_custom(sym):
    import stock_manager
    res = stock_manager.remove_stock(sym)
    if res["status"] == "ok":
        return jsonify(res)
    return jsonify(res), 400


import csv
import io
import requests

def search_ticker(name):
    url = "https://query2.finance.yahoo.com/v1/finance/search"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    params = {
        "q": name,
        "quotesCount": 5,
        "newsCount": 0
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            quotes = data.get("quotes", [])
            # Filter for NSE symbols ending in .NS
            nse_quotes = [q for q in quotes if q.get("symbol", "").endswith(".NS")]
            if nse_quotes:
                yahoo_symbol = nse_quotes[0]["symbol"]
                sym = yahoo_symbol.replace(".NS", "")
                company_name = nse_quotes[0].get("shortname", nse_quotes[0].get("longname", name))
                return {
                    "sym": sym,
                    "yahoo": yahoo_symbol,
                    "name": company_name,
                    "sector": "Other"
                }
    except Exception as e:
        print(f"[app] Error searching ticker for '{name}': {e}")
    return None


@app.route("/api/upload-csv", methods=["POST"])
@require_password
def api_upload_csv():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400
        
    file = request.files["file"]
    if not file.filename.endswith(".csv"):
        return jsonify({"status": "error", "message": "File must be a CSV"}), 400
        
    try:
        content = file.read().decode("utf-8-sig", errors="replace")
        csv_file = io.StringIO(content)
        reader = csv.reader(csv_file)
        rows = list(reader)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to read CSV: {e}"}), 400
        
    if not rows:
        return jsonify({"status": "error", "message": "Empty CSV file"}), 400
        
    # Get headers
    headers = [h.strip().lower() for h in rows[0]]
    
    symbol_idx = -1
    name_idx = -1
    
    # Try to find headers
    for idx, h in enumerate(headers):
        if h in ["symbol", "ticker", "nse symbol", "stock symbol"]:
            symbol_idx = idx
            break
            
    for idx, h in enumerate(headers):
        if h in ["name", "company", "company name"]:
            name_idx = idx
            break
            
    # Default fallback
    if symbol_idx == -1 and name_idx == -1:
        name_idx = 0
        
    import stock_manager
    existing_stocks = stocks_dict()
    
    imported = 0
    skipped_duplicates = 0
    failed_resolutions = 0
    details = []
    
    for row in rows[1:]:
        if not row or not any(row):
            continue
            
        sym = None
        yahoo = None
        name = None
        
        # 1. Direct symbol check
        if symbol_idx != -1 and symbol_idx < len(row):
            val = row[symbol_idx].strip().upper()
            if val:
                sym = val
                if not sym.endswith(".NS"):
                    yahoo = sym + ".NS"
                else:
                    yahoo = sym
                    sym = sym[:-3]
                    
        # 2. Resolution check via name
        if not sym and name_idx != -1 and name_idx < len(row):
            val = row[name_idx].strip()
            if val:
                resolved = search_ticker(val)
                if resolved:
                    sym = resolved["sym"]
                    yahoo = resolved["yahoo"]
                    name = resolved["name"]
                else:
                    failed_resolutions += 1
                    details.append({"row": row, "status": "failed_resolution", "message": f"Could not resolve name '{val}' to ticker"})
                    continue
                    
        if not sym:
            failed_resolutions += 1
            details.append({"row": row, "status": "invalid_row", "message": "No symbol or name in row"})
            continue
            
        # 3. Duplication check
        if sym in existing_stocks:
            skipped_duplicates += 1
            details.append({"sym": sym, "status": "skipped", "message": "Symbol already exists"})
            continue
            
        # 4. Fallback name
        if not name:
            if name_idx != -1 and name_idx < len(row):
                name = row[name_idx].strip()
            if not name:
                name = sym
                
        # 5. Save custom stock
        resolved_sector = "Other"
        if not sym and name_idx != -1:
            pass  # sector already set from resolved above if it was from search_ticker
        res = stock_manager.add_stock(
            sym=sym,
            yahoo=yahoo,
            name=name,
            sector=resolved_sector
        )
        if res["status"] == "ok":
            imported += 1
            existing_stocks[sym] = {"yahoo": yahoo, "name": name, "sector": "Other"}
            details.append({"sym": sym, "status": "imported", "message": "Successfully imported"})
        else:
            failed_resolutions += 1
            details.append({"sym": sym, "status": "error", "message": res.get("message", "Add stock error")})
            
    return jsonify({
        "status": "ok",
        "imported": imported,
        "skipped_duplicates": skipped_duplicates,
        "failed_resolutions": failed_resolutions,
        "details": details
    })


# ── API: Settings (load / save / test) ───────────────────────
@app.route("/api/settings", methods=["GET"])
@require_password
def api_settings_get():
    """Return current settings (masks token for security)."""
    import alert_bot
    s = alert_bot.load_settings()
    token = s.get("telegram_token", "")
    # Mask all but last 5 chars of token
    if token and len(token) > 10:
        s["telegram_token_masked"] = "••••••" + token[-5:]
    else:
        s["telegram_token_masked"] = ""
    return jsonify({"status": "ok", "settings": s})


@app.route("/api/settings", methods=["POST"])
@require_password
def api_settings_save():
    """Save settings to settings.json."""
    import alert_bot
    data = request.json or {}
    # Don't overwrite token if a masked value is sent
    if "telegram_token" in data and "••" in str(data["telegram_token"]):
        data.pop("telegram_token")
    ok = alert_bot.save_settings(data)
    if ok:
        return jsonify({"status": "ok", "message": "Settings saved successfully."})
    return jsonify({"status": "error", "message": "Failed to save settings."}), 500


@app.route("/api/settings/test", methods=["POST"])
@require_password
def api_settings_test():
    """Test Telegram connection with provided credentials."""
    import alert_bot
    data = request.json or {}
    token   = data.get("telegram_token", "").strip()
    chat_id = data.get("telegram_chat_id", "").strip()

    # Fall back to saved token if masked value was sent
    if not token or "••" in token:
        saved = alert_bot.load_settings()
        token = saved.get("telegram_token", "")

    ok, message = alert_bot.test_connection(token, chat_id)
    return jsonify({"status": "ok" if ok else "error", "message": message})


# ── API: Watchlist & Price Alerts CRUD ────────────────────────
@app.route("/api/watchlist")
@require_password
def api_get_watchlist():
    """Get all watchlist alerts."""
    import history_db
    alerts = history_db.get_watchlist_alerts()
    return jsonify({"status": "ok", "alerts": alerts})


@app.route("/api/watchlist", methods=["POST"])
@require_password
def api_add_watchlist():
    """Add a new alert to the watchlist."""
    import history_db
    data = request.json or {}
    sym = data.get("sym", "").strip().upper()
    yahoo = data.get("yahoo", "").strip().upper()
    target_price = data.get("target_price")
    condition = data.get("condition", "ABOVE").strip().upper()

    if not sym:
        return jsonify({"status": "error", "message": "Symbol is required."}), 400
    if not target_price:
        return jsonify({"status": "error", "message": "Target price is required."}), 400
    try:
        target_price = float(target_price)
    except ValueError:
        return jsonify({"status": "error", "message": "Target price must be a number."}), 400

    if not yahoo:
        yahoo = sym + ".NS"
    elif not yahoo.endswith(".NS") and "." not in yahoo:
        yahoo = yahoo + ".NS"

    if condition not in ["ABOVE", "BELOW"]:
        return jsonify({"status": "error", "message": "Condition must be ABOVE or BELOW."}), 400

    ok = history_db.add_watchlist_alert(sym, yahoo, target_price, condition)
    if ok:
        return jsonify({"status": "ok", "message": f"Alert for {sym} added successfully."})
    return jsonify({"status": "error", "message": "Failed to add alert to database."}), 500


@app.route("/api/watchlist/<int:alert_id>", methods=["DELETE"])
@require_password
def api_delete_watchlist(alert_id):
    """Delete an alert from the watchlist."""
    import history_db
    ok = history_db.delete_watchlist_alert(alert_id)
    if ok:
        return jsonify({"status": "ok", "message": "Alert deleted successfully."})
    return jsonify({"status": "error", "message": "Failed to delete alert."}), 500


@app.route("/api/check-alerts")
@require_password
def api_check_alerts():
    """
    Check all active price alerts.
    Fetches the live price for active alert symbols.
    Sends Telegram messages for triggered alerts and disables them.
    """
    import history_db
    import fetcher
    import alert_bot

    active_alerts = history_db.get_active_watchlist_alerts()
    if not active_alerts:
        return jsonify({
            "status": "ok",
            "message": "No active alerts to check.",
            "checked": 0,
            "triggered": 0
        })

    # Load settings to get Telegram config
    settings = alert_bot.load_settings()
    token = settings.get("telegram_token", "").strip()
    chat_id = settings.get("telegram_chat_id", "").strip()

    if not token or not chat_id:
        print("[app] Telegram alerts not configured. Checked alerts locally only.")

    checked_count = 0
    triggered_count = 0
    triggered_list = []

    price_cache = {}

    for alert in active_alerts:
        yahoo_sym = alert["yahoo"]
        sym = alert["sym"]
        target = float(alert["target_price"])
        cond = alert["alert_condition"]
        alert_id = alert["id"]

        if yahoo_sym not in price_cache:
            live_price = fetcher.fetch_live_price(yahoo_sym)
            if live_price is not None:
                price_cache[yahoo_sym] = live_price
                import time
                time.sleep(0.2)
        else:
            live_price = price_cache[yahoo_sym]

        if live_price is None:
            print(f"[app] Failed to fetch live price for {yahoo_sym}")
            continue

        checked_count += 1
        is_triggered = False
        if cond == "ABOVE" and live_price >= target:
            is_triggered = True
        elif cond == "BELOW" and live_price <= target:
            is_triggered = True

        if is_triggered:
            triggered_count += 1
            triggered_list.append(f"{sym} ({live_price} vs {cond} {target})")

            # 1. Update database first
            history_db.mark_watchlist_alert_triggered(alert_id)

            # 2. Send Telegram notification
            if token and chat_id:
                ist_now = get_ist_time()
                formatted_time = ist_now.strftime("%d %b %Y  %I:%M %p IST")
                
                alert_text = (
                    "🚨 <b>Finrio AI — Price Alert Triggered!</b> 🚨\n\n"
                    f"📈 Stock: <b>{sym}</b>\n"
                    f"🎯 Target Price: <b>₹{target:,.2f}</b> ({cond})\n"
                    f"💵 Live Price: <b>₹{live_price:,.2f}</b>\n"
                    f"⏰ Time: {formatted_time}\n\n"
                    "👉 Visit <a href='https://finrio-ai.onrender.com'>Finrio AI Dashboard</a>"
                )
                alert_bot.send_telegram(token, chat_id, alert_text)

    return jsonify({
        "status": "ok",
        "message": f"Checked {checked_count} active alerts. Triggered {triggered_count} alerts.",
        "checked": checked_count,
        "triggered": triggered_count,
        "details": triggered_list
    })


# ── API: Sector Rotation Heatmap ──────────────────────────────
@app.route("/api/sector-analysis")
def api_sector_analysis():
    """
    Return sector-wise BUY count, avg score, and trend distribution.
    Used by the frontend Sector Heatmap widget.
    """
    data = load_data_file()
    if data is None:
        return jsonify({"status": "no_data", "sectors": []}), 404

    stocks = [s for s in data.get("stocks", []) if s.get("status") == "ok"]

    # Group by sector
    sector_map = {}
    for s in stocks:
        sec = s.get("sector", "Other") or "Other"
        if sec not in sector_map:
            sector_map[sec] = {
                "sector": sec,
                "total": 0,
                "buy": 0,
                "strong_buy": 0,
                "watch": 0,
                "avoid": 0,
                "scores": [],
                "uptrend": 0,
                "downtrend": 0,
                "sideways": 0,
            }
        entry = sector_map[sec]
        entry["total"] += 1
        entry["scores"].append(s.get("score", 0))
        sig = s.get("signal", "AVOID")
        if sig == "STRONG BUY": entry["strong_buy"] += 1
        elif sig == "BUY":      entry["buy"] += 1
        elif sig == "WATCH":    entry["watch"] += 1
        else:                   entry["avoid"] += 1

        trend = s.get("marketTrend", "SIDEWAYS")
        if trend == "UPTREND":   entry["uptrend"] += 1
        elif trend == "DOWNTREND": entry["downtrend"] += 1
        else:                     entry["sideways"] += 1

    # Build final list
    result = []
    for sec, d in sector_map.items():
        avg_score = round(sum(d["scores"]) / len(d["scores"]), 1) if d["scores"] else 0
        buy_rate  = round((d["buy"] + d["strong_buy"]) / d["total"] * 100, 1) if d["total"] > 0 else 0
        result.append({
            "sector":     sec,
            "total":      d["total"],
            "buy":        d["buy"] + d["strong_buy"],
            "strong_buy": d["strong_buy"],
            "watch":      d["watch"],
            "avoid":      d["avoid"],
            "avgScore":   avg_score,
            "buyRate":    buy_rate,
            "uptrend":    d["uptrend"],
            "downtrend":  d["downtrend"],
            "sideways":   d["sideways"],
        })

    # Sort by buy_rate descending (hottest sector first)
    result.sort(key=lambda x: x["buyRate"], reverse=True)

    return jsonify({"status": "ok", "sectors": result})


# ── API: Performance Evaluation (EOD comparison) ──────────────
@app.route("/api/performance")
def api_performance():
    import history_db
    try:
        history_db.init_db()              # ensure tables exist (fresh deploy safety)
        conn = history_db.get_connection()
        cursor = history_db.get_cursor(conn)
    except Exception as db_err:
        print(f"[app] Database connection/init error: {db_err}")
        return jsonify({
            "status": "error",
            "message": f"Database connection or initialization failed: {db_err}"
        }), 500
    
    try:
        # 1. Fetch all scans sorted by date descending
        cursor.execute("SELECT id, scanned_at, nifty_price, nifty_change, nifty_mood FROM scans ORDER BY scanned_at DESC")
        scans = [dict(row) for row in cursor.fetchall()]
        
        if len(scans) < 2:
            return jsonify({
                "status": "insufficient_data",
                "message": "At least 2 scans are required in history to evaluate performance. Please run another scan first.",
                "scans_list": scans
            })
            
        # Latest scan is always the first one in DESC order
        latest_scan = scans[0]
        latest_scan_id = latest_scan["id"]
        
        # 2. Determine compare scan (previous scan or specified compare_scan_id)
        compare_scan_id = request.args.get("compare_scan_id", type=int)
        compare_scan = None
        
        if compare_scan_id:
            for s in scans:
                if s["id"] == compare_scan_id:
                    compare_scan = s
                    break
        
        # Default: second-most-recent scan (scans[1])
        if compare_scan is None:
            compare_scan = scans[1]
            compare_scan_id = compare_scan["id"]
            
        # Avoid comparing latest scan with itself
        if compare_scan_id == latest_scan_id:
            if len(scans) >= 2:
                compare_scan = scans[1]
                compare_scan_id = compare_scan["id"]
            else:
                return jsonify({
                    "status": "error",
                    "message": "Cannot compare the latest scan with itself."
                }), 400
                
        # 3. Fetch latest scan stock records (using dynamic placeholders)
        placeholder = "%s" if history_db.DATABASE_URL else "?"
        cursor.execute(f"SELECT sym, price, change, signal FROM history_records WHERE scan_id = {placeholder}", (latest_scan_id,))
        latest_records = {row["sym"].upper(): dict(row) for row in cursor.fetchall()}
        
        # 4. Fetch compare scan stock records
        cursor.execute(f"SELECT sym, price, change, score, signal FROM history_records WHERE scan_id = {placeholder}", (compare_scan_id,))
        compare_records = [dict(row) for row in cursor.fetchall()]
        
        # 5. Filter for recommended BUY or STRONG BUY in the compare scan
        recommended = [r for r in compare_records if r["signal"] in ["BUY", "STRONG BUY"]]
        
        results = []
        avg_return = 0.0
        success_count = 0
        best_stock = "—"
        best_return = -999.0
        worst_stock = "—"
        worst_return = 999.0
        
        for r in recommended:
            sym = r["sym"].upper()
            initial_price = r["price"]
            
            if sym in latest_records and initial_price > 0:
                current_price = latest_records[sym]["price"]
                change_pct = ((current_price - initial_price) / initial_price) * 100
                
                if change_pct > best_return:
                    best_return = change_pct
                    best_stock = sym
                if change_pct < worst_return:
                    worst_return = change_pct
                    worst_stock = sym
                    
                if change_pct > 0:
                    success_count += 1
                    
                results.append({
                    "sym": sym,
                    "initialPrice": initial_price,
                    "currentPrice": current_price,
                    "performance": round(change_pct, 2),
                    "score": r["score"],
                    "signal": r["signal"]
                })
                
        # Calculate aggregates
        total_count = len(results)
        if total_count > 0:
            avg_return = sum(r["performance"] for r in results) / total_count
            win_rate = (success_count / total_count) * 100
        else:
            win_rate = 0.0
            best_return = 0.0
            worst_return = 0.0
            
        # Nifty Return
        nifty_compare = compare_scan.get("nifty_price", 0.0)
        nifty_latest = latest_scan.get("nifty_price", 0.0)
        nifty_return = 0.0
        if nifty_compare > 0:
            nifty_return = ((nifty_latest - nifty_compare) / nifty_compare) * 100
            
        metrics = {
            "totalCount": total_count,
            "avgReturn": round(avg_return, 2),
            "winRate": round(win_rate, 2),
            "niftyReturn": round(nifty_return, 2),
            "bestStock": best_stock,
            "bestReturn": round(best_return, 2) if best_stock != "—" else 0.0,
            "worstStock": worst_stock,
            "worstReturn": round(worst_return, 2) if worst_stock != "—" else 0.0
        }
        
        return jsonify({
            "status": "ok",
            "scans_list": scans,
            "compare_scan": compare_scan,
            "latest_scan": latest_scan,
            "results": results,
            "metrics": metrics
        })
        
    except Exception as e:
        print(f"[app] ERROR in api_performance: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()


# ── API: Stock Chart Daily History ────────────────────────────
@app.route("/api/stock/<sym>/history")
def api_stock_history(sym):
    sym = sym.upper()
    stocks = stocks_dict()
    if sym not in stocks:
        return jsonify({"status": "error", "message": f"Symbol '{sym}' not found"}), 404
    
    yahoo_sym = stocks[sym]["yahoo"]
    from fetcher import fetch_ohlcv
    df = fetch_ohlcv(yahoo_sym, period="1y")
    if df is None or df.empty:
        return jsonify({"status": "error", "message": "Failed to fetch stock history"}), 500
    
    try:
        # Calculate EMAs for historical charts
        df["ema9"]   = df["Close"].ewm(span=9,   adjust=False).mean()
        df["ema20"]  = df["Close"].ewm(span=20,  adjust=False).mean()
        df["ema21"]  = df["Close"].ewm(span=21,  adjust=False).mean()
        df["ema50"]  = df["Close"].ewm(span=50,  adjust=False).mean()
        df["ema200"] = df["Close"].ewm(span=200, adjust=False).mean() if len(df) >= 200 else df["ema50"]
        
        history = []
        for index, row in df.iterrows():
            history.append({
                "time": index.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
                "ema9": round(float(row["ema9"]), 2) if not pd.isna(row["ema9"]) else None,
                "ema20": round(float(row["ema20"]), 2) if not pd.isna(row["ema20"]) else None,
                "ema21": round(float(row["ema21"]), 2) if not pd.isna(row["ema21"]) else None,
                "ema50": round(float(row["ema50"]), 2) if not pd.isna(row["ema50"]) else None,
                "ema200": round(float(row["ema200"]), 2) if not pd.isna(row["ema200"]) else None
            })
        return jsonify({"status": "ok", "history": history})
    except Exception as ex:
        return jsonify({"status": "error", "message": str(ex)}), 500


# ── API: Stock Score History (SQLite logs) ────────────────────
@app.route("/api/stock/<sym>/score-history")
def api_stock_score_history(sym):
    import history_db
    history = history_db.get_score_history(sym, limit=15)
    return jsonify({"status": "ok", "history": history})


# ── STARTUP ───────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  FINRIO AI — FLASK SERVER")
    print("=" * 55)
    print(f"  Stocks loaded : {len(STOCKS)}")
    print(f"  Frontend      : {FRONTEND}/index.html")
    print(f"  Data file     : {DATA_FILE}")
    print()

    # Check if data file exists
    data = load_data_file()
    if data:
        print(f"  Last scan     : {data.get('scanned_at','unknown')}")
        print(f"  Stocks in DB  : {len(data.get('stocks',[]))}")
    else:
        print(f"  Last scan     : No data yet")
        print(f"  Tip           : Call GET /api/scan to run first scan")
    print()
    print(f"  Server URL    : http://localhost:{PORT}")
    print(f"  API routes    : http://localhost:{PORT}/api/status")
    print()
    print("  Starting server...")
    print("  Press CTRL+C to stop")
    print("=" * 55)

    # Create frontend folder if missing
    os.makedirs(FRONTEND, exist_ok=True)

    app.run(
        host  = "0.0.0.0",   # accessible on local network
        port  = PORT,
        debug = DEBUG
    )
