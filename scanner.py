# =============================================================
# scanner.py — ORCHESTRATOR ONLY
# =============================================================
# This file ONLY connects all modules together.
# It contains NO logic of its own.
#
# Imports from:
#   stocks.py     → STOCKS list, NIFTY_SYM
#   fetcher.py    → fetch_ohlcv(), fetch_nifty()
#   indicators.py → calc_all()
#   patterns.py   → detect_pattern(), find_support_resistance()
#   scorer.py     → score_stock(), get_signal(),
#                   get_momentum(), get_full_analysis()
#
# If any module changes internally → scanner.py stays the same.
# Only change scanner.py if the CONNECTION between modules changes.
#
# Functions:
#   scan_one(sym, yahoo_sym, name, sector) → dict
#   scan_all(stocks_list, verbose)         → list of dicts
#   save_json(data, filename)              → saves JSON file
#   run_full_scan(verbose)                 → main entry point
#
# Test:
#   python scanner.py
# =============================================================

import json
import time
from datetime import datetime, timezone, timedelta

from stocks     import STOCKS, NIFTY_SYM
from fetcher    import fetch_ohlcv, fetch_nifty
from indicators import calc_all, calc_weekly
from patterns   import detect_pattern, find_support_resistance
from scorer     import (score_stock, get_signal,
                        get_momentum, get_full_analysis)

# Output file — read by app.py and HTML screener
OUTPUT_FILE = "screener_data.json"

# Delay between stocks — avoids Yahoo rate limiting
SCAN_DELAY  = 0.5   # seconds

import math

def clean_nan(obj):
    """
    Recursively replaces NaN and Inf float values in dicts/lists/values with None.
    This prevents generating invalid JSON (NaN) which crashes JavaScript JSON.parse.
    """
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan(x) for x in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


# ── SCAN ONE STOCK ────────────────────────────────────────────
def scan_one(sym, yahoo_sym, name, sector, capital=100000, df_nifty=None):
    """
    Full pipeline for a single stock:
      fetch → indicators → patterns → score

    Args:
        sym       : str → screener ID e.g. "HDFCBANK"
        yahoo_sym : str → Yahoo symbol e.g. "HDFCBANK.NS"
        name      : str → display name
        sector    : str → sector name
        capital   : int → trading capital for position sizing
        df_nifty  : DataFrame → optional pre-fetched Nifty index benchmark

    Returns:
        dict → complete stock data ready for screener
               status = "ok" if successful
               status = "error" if any step failed
    """
    # Fallback to fetch Nifty 50 if not provided
    if df_nifty is None:
        try:
            df_nifty = fetch_ohlcv(NIFTY_SYM, period="1y")
        except Exception:
            pass

    # ── Step 1: Fetch OHLCV (daily) ───────────────────────
    df = fetch_ohlcv(yahoo_sym, period="1y")
    if df is None or len(df) < 60:
        return {
            "sym":    sym,
            "yahoo":  yahoo_sym,
            "name":   name,
            "sector": sector,
            "status": "error",
            "error":  "Could not fetch data or insufficient history"
        }

    # ── Step 1b: Weekly OHLCV + Market Cap (single Ticker session) ─
    try:
        import yfinance as yf
        ticker     = yf.Ticker(yahoo_sym)
        df_weekly  = ticker.history(period="2y", interval="1wk")
        if df_weekly is not None and not df_weekly.empty:
            df_weekly = df_weekly[["Open","High","Low","Close","Volume"]].copy()
        else:
            df_weekly = None

        # Market Cap — from fast_info (cached, minimal cost)
        try:
            raw_cap    = getattr(ticker.fast_info, "market_cap", None) or 0
            mkt_cap_cr = round(raw_cap / 1e7, 0)   # Convert to ₹Crore (1Cr = 10M)
            if mkt_cap_cr >= 50000:
                cap_cat = "Large Cap"
            elif mkt_cap_cr >= 5000:
                cap_cat = "Mid Cap"
            elif mkt_cap_cr > 0:
                cap_cat = "Small Cap"
            else:
                mkt_cap_cr = 0
                cap_cat    = "Unknown"
        except Exception:
            mkt_cap_cr = 0
            cap_cat    = "Unknown"

    except Exception:
        df_weekly  = None
        mkt_cap_cr = 0
        cap_cat    = "Unknown"

    # ── Step 2: Calculate Indicators ──────────────────────
    try:
        ind = calc_all(df, df_nifty=df_nifty)
    except Exception as e:
        return {
            "sym":    sym,
            "yahoo":  yahoo_sym,
            "name":   name,
            "sector": sector,
            "status": "error",
            "error":  f"Indicator error: {e}"
        }

    # ── Step 3: Detect Pattern + S&R ──────────────────────
    try:
        pat_name, pat_type, entry_note, strength = detect_pattern(df)
        sup, res, dist_sup, dist_res, near_sup   = find_support_resistance(df)
    except Exception as e:
        return {
            "sym":    sym,
            "yahoo":  yahoo_sym,
            "name":   name,
            "sector": sector,
            "status": "error",
            "error":  f"Pattern error: {e}"
        }

    # ── Step 3b: Weekly Timeframe Confirmation ─────────────
    weekly_data = calc_weekly(df_weekly)

    # ── Step 4: Today's OHLC ──────────────────────────────
    today = df.iloc[-1]

    # ── Step 5: Merge Everything ──────────────────────────
    stock = {
        # Identity
        "sym":           sym,
        "yahoo":         yahoo_sym,
        "name":          name,
        "sector":        sector,
        "status":        "ok",
        # From indicators (includes MACD, BB, ADX, Gap, gapUp, etc.)
        **ind,
        # Weekly timeframe
        **weekly_data,
        # Today's OHLC
        "todayOpen":     round(float(today["Open"]),  2),
        "todayHigh":     round(float(today["High"]),  2),
        "todayLow":      round(float(today["Low"]),   2),
        "todayClose":    round(float(today["Close"]), 2),
        # Candlestick pattern
        "candle":        pat_name,
        "candleType":    pat_type,
        "entryNote":     entry_note,
        "candleStrength":strength,
        # Support & Resistance
        "support":       sup,
        "resistance":    res,
        "distToSup":     dist_sup,
        "distToRes":     dist_res,
        "nearSupport":   near_sup,
        # Market Cap classification
        "marketCap":     mkt_cap_cr,
        "capCategory":   cap_cat,
    }

    # -- Step 6: Score + Signal ----------------------------
    analysis         = get_full_analysis(stock, capital=capital)
    stock["score"]   = analysis["score"]
    stock["trendContinuationScore"] = analysis["trendContinuationScore"]
    stock["signal"]  = analysis["signal"]
    stock["momentum"]= analysis["momentum"]

    # Add position sizing to stock dict
    stock["shares"]        = analysis["shares"]
    stock["capitalNeeded"] = analysis["capitalNeeded"]
    stock["maxLoss"]       = analysis["maxLoss"]
    stock["profit2"]       = analysis["profit2"]
    stock["profit3"]       = analysis["profit3"]
    stock["holdDuration"]  = analysis["holdDuration"]
    stock["rrGatePassed"]  = analysis["rrGatePassed"]

    return clean_nan(stock)


# ── SCAN ALL STOCKS ───────────────────────────────────────────
def scan_all(stocks_list=None, capital=100000, verbose=True, progress_callback=None):
    """
    Scan all stocks in list through full pipeline.

    Args:
        stocks_list : list → from stocks.py (default: all STOCKS)
        capital     : int  → trading capital
        verbose     : bool → print progress
        progress_callback : func → function receiving (current, total, symbol)

    Returns:
        list of dicts → all scanned stocks sorted by score
    """
    if stocks_list is None:
        stocks_list = STOCKS

    # Fetch Nifty 50 daily history once for Relative Strength calculations
    df_nifty = None
    try:
        if verbose:
            print("  Fetching Nifty 50 benchmark index data...", end=" ", flush=True)
        df_nifty = fetch_ohlcv(NIFTY_SYM, period="1y")
        if verbose:
            print("done.")
    except Exception as ne:
        print(f"[scanner] Warning: Could not fetch Nifty index benchmark: {ne}")

    total     = len(stocks_list)
    results   = []
    ok_count  = 0
    err_count = 0

    for i, (sym, yahoo_sym, name, sector) in enumerate(stocks_list):
        if progress_callback:
            try:
                progress_callback(i + 1, total, sym)
            except Exception as pe:
                print(f"[scanner] Error in progress_callback: {pe}")

        if verbose:
            print(f"  [{i+1:>3}/{total}]  {sym:<14}", end="  ", flush=True)

        stock = scan_one(sym, yahoo_sym, name, sector, capital=capital, df_nifty=df_nifty)

        if stock["status"] == "ok":
            # Signal icon for terminal
            sig_icon = "[o]" if stock["signal"] == "BUY"   else \
                       "[w]" if stock["signal"] == "WATCH" else "[x]"
            flags = ""
            if stock.get("emaCrossAlert"): flags += " [CR]"
            if stock.get("volSpike"):      flags += " [VOL]"
            if stock.get("nearSupport"):   flags += " [SUP]"

            if verbose:
                print(
                    f"[ok] Rs.{stock['price']:>9,.2f}  "
                    f"{stock['change']:>+6.2f}%  "
                    f"RSI:{stock['rsi']:>5.1f}  "
                    f"ATR:{stock['atrPct']:>4.1f}%  "
                    f"{stock['trendDays']:>2}d  "
                    f"{stock['candle']:<20}  "
                    f"{sig_icon} {stock['signal']}"
                    f"{flags}"
                )
            ok_count += 1
        else:
            if verbose:
                print(f"[FAIL] {stock.get('error','failed')[:45]}")
            err_count += 1

        results.append(stock)
        time.sleep(SCAN_DELAY)

    # Sort by score descending
    results.sort(key=lambda x: x.get("score", 0), reverse=True)

    if verbose:
        print()
        print(f"  Scanned : {ok_count}/{total} ok  |  {err_count} failed")

    return results


# ── SAVE JSON ─────────────────────────────────────────────────
def save_json(data, filename=OUTPUT_FILE):
    """
    Save scan results to JSON file.
    This file is read by app.py (Flask) and the HTML screener.

    Args:
        data     : dict → full scan output
        filename : str  → output path (default: screener_data.json)
    """
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)


# ── BUILD SUMMARY ─────────────────────────────────────────────
def build_summary(results, nifty):
    """
    Build the complete output dict for JSON + Telegram.

    Args:
        results : list  -> from scan_all()
        nifty   : dict  -> from fetch_nifty()

    Returns:
        dict -> full output ready for save_json()
    """
    ok_stocks  = [s for s in results if s["status"] == "ok"]
    buy_list   = [s for s in ok_stocks if s["signal"] == "BUY"]
    watch_list = [s for s in ok_stocks if s["signal"] == "WATCH"]
    avoid_list = [s for s in ok_stocks if s["signal"] == "AVOID"]

    # Trend distribution
    uptrend_count   = sum(1 for s in ok_stocks if s.get("marketTrend") == "UPTREND")
    downtrend_count = sum(1 for s in ok_stocks if s.get("marketTrend") == "DOWNTREND")
    sideways_count  = sum(1 for s in ok_stocks if s.get("marketTrend") == "SIDEWAYS")

    # Market mood from Nifty
    chg  = nifty.get("change", 0)
    mood = "BULLISH"  if chg >=  0.5 else \
           "NEUTRAL"  if chg >= -0.3 else \
           "CAUTIOUS" if chg >= -1.0 else "BEARISH"
    advice = {
        "BULLISH":  "Buy quality dips",
        "NEUTRAL":  "Wait and watch",
        "CAUTIOUS": "Reduce position size",
        "BEARISH":  "Stay in cash today"
    }[mood]

    nifty["mood"]   = mood
    nifty["advice"] = advice

    utc_now = datetime.now(timezone.utc)
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    scanned_at_str = ist_now.strftime("%Y-%m-%d %H:%M:%S")

    return {
        "scanned_at":      scanned_at_str,
        "total":           len(results),
        "ok":              len(ok_stocks),
        "errors":          len(results) - len(ok_stocks),
        "buy_count":       len(buy_list),
        "watch_count":     len(watch_list),
        "avoid_count":     len(avoid_list),
        "uptrend_count":   uptrend_count,
        "downtrend_count": downtrend_count,
        "sideways_count":  sideways_count,
        "nifty":           nifty,
        "stocks":          results,
    }


# ── RUN FULL SCAN — MAIN ENTRY POINT ─────────────────────────
def run_full_scan(stocks_list=None, capital=100000, verbose=True, progress_callback=None):
    """
    Main entry point called by app.py and Telegram bot.
    Runs complete scan and saves screener_data.json.

    Args:
        stocks_list : list -> stocks to scan (default: all from stocks.py)
        capital     : int  -> trading capital for position sizing
        verbose     : bool -> print progress to terminal
        progress_callback : func -> function receiving (current, total, symbol)

    Returns:
        dict -> full scan summary
    """
    if stocks_list is None:
        stocks_list = STOCKS

    if verbose:
        print("=" * 72)
        print("  SWING SCREENER - FULL SCAN")
        print("=" * 72)
        print(f"  Stocks  : {len(stocks_list)}")
        print(f"  Capital : Rs.{capital:,}")
        print(f"  Started : {datetime.now().strftime('%d %b %Y  %H:%M:%S')}")
        print()

    # Fetch Nifty
    if verbose:
        print("  Fetching Nifty 50...", end="  ", flush=True)
    nifty = fetch_nifty(NIFTY_SYM)
    if verbose:
        if nifty["status"] == "ok":
            sign = "+" if nifty["change"] >= 0 else ""
            print(f"Rs.{nifty['price']:,.2f}  "
                  f"{sign}{nifty['change']}%")
        else:
            print("FAILED")
    print()

    # Print header
    if verbose:
        print("-" * 72)
        print(f"  {'#':>3}  {'SYM':<14} {'PRICE':>10}  "
              f"{'CHG%':>6}  {'RSI':>5}  {'ATR%':>5}  "
              f"{'TREND':>5}  {'PATTERN':<20} SIG")
        print("  " + "-" * 68)

    # Scan all stocks
    results = scan_all(stocks_list, capital=capital, verbose=verbose, progress_callback=progress_callback)

    # Build and save summary
    summary = build_summary(results, nifty)
    summary = clean_nan(summary)
    save_json(summary)

    # Save to SQLite history
    try:
        import history_db
        history_db.save_scan_to_history(summary)
    except Exception as he:
        print(f"[scanner] Error saving to history DB: {he}")

    # Send Telegram alert (if configured and enabled)
    try:
        import alert_bot
        alert_bot.send_scan_alert(summary)
    except Exception as ae:
        print(f"[scanner] Telegram alert skipped: {ae}")

    # Print final report
    if verbose:
        ok_stocks  = [s for s in results if s["status"] == "ok"]
        buy_list   = [s for s in ok_stocks if s["signal"] == "BUY"]
        watch_list = [s for s in ok_stocks if s["signal"] == "WATCH"]

        print()
        print("=" * 72)
        print(f"  Nifty  : Rs.{nifty['price']:,.2f}  "
              f"({'+' if nifty['change']>=0 else ''}"
              f"{nifty['change']}%)  "
              f"-> {nifty['mood']}  |  {nifty['advice']}")
        print(f"  Result : {len(ok_stocks)}/{len(results)} ok  "
              f"[BUY]: {len(buy_list)}  "
              f"[WATCH]: {len(watch_list)}  "
              f"[AVOID]: {len(ok_stocks)-len(buy_list)-len(watch_list)}")

        if buy_list:
            print()
            print("  -- BUY SETUPS ----------------------------------------")
            for s in buy_list:
                flags = ("  [CR] EMA CROSS" if s.get("emaCrossAlert") else "") + \
                        ("  [VOL] VOL SPIKE" if s.get("volSpike")      else "") + \
                        ("  [SUP] NEAR SUP"  if s.get("nearSupport")   else "")
                print(f"\n  {s['sym']}  ({s['sector']})  "
                      f"Score:{s['score']}{flags}")
                print(f"  Price  : Rs.{s['price']:,.2f}  "
                      f"({'+' if s['change']>=0 else ''}{s['change']}%)")
                print(f"  RSI    : {s['rsi']}  "
                      f"ATR: {s['atrPct']}%  "
                      f"Trend: {s['trendDays']} days")
                print(f"  Candle : {s['candle']}")
                print(f"  Action : {s['entryNote']}")
                print(f"  SL     : Rs.{s['slPrice']:,.2f}  "
                      f"Shares: {s['shares']}  "
                      f"Capital: Rs.{s['capitalNeeded']:,.2f}")
                print(f"  T1: Rs.{s.get('tgt1',0):,.2f} (+1R)  "
                      f"T2: Rs.{s.get('tgt2',0):,.2f} (+1.5R)  "
                      f"T3: Rs.{s.get('tgt3',0):,.2f} (+2.5R)")
                hold = s.get('holdDuration', '')
                if hold:
                    print(f"  Hold   : {hold}")

        print()
        print(f"  Saved -> {OUTPUT_FILE}")
        print(f"  Done  : {datetime.now().strftime('%H:%M:%S')}")
        print()
        print("  [x] SCAN COMPLETE")
        print("  Next: python app.py  (starts Flask server)")
        print("=" * 72)

    return summary


# ── TEST ──────────────────────────────────────────────────────
if __name__ == "__main__":
    # Test with 5 stocks first
    test_stocks = STOCKS[:5]
    print(f"  Testing with first 5 stocks from stocks.py")
    print(f"  To scan all {len(STOCKS)} stocks: "
          f"change STOCKS[:5] to STOCKS")
    print()
    run_full_scan(stocks_list=test_stocks, capital=100000, verbose=True)
