# =============================================================
# fetcher.py — YAHOO FINANCE DATA FETCH ONLY
# =============================================================
# This file ONLY talks to yfinance.
# No calculations, no patterns, no scoring here.
#
# If Yahoo Finance changes their API → fix ONLY this file.
# If yfinance library updates → fix ONLY this file.
#
# Functions:
#   fetch_ohlcv(yahoo_sym, period)  → DataFrame or None
#   fetch_nifty()                   → dict
#   fetch_all_stocks(stocks_list)   → dict of DataFrames
#
# Test:
#   python fetcher.py
# =============================================================

import yfinance as yf
import time

# Delay between requests — avoids Yahoo rate limiting
REQUEST_DELAY = 0.5   # seconds


# ── FETCH ONE STOCK OHLCV ─────────────────────────────────────
def fetch_ohlcv(yahoo_sym, period="1y"):
    """
    Fetch daily OHLCV data for one stock from Yahoo Finance.

    Args:
        yahoo_sym : str  → e.g. "HDFCBANK.NS"
        period    : str  → "1y" / "6mo" / "3mo" / "1mo" / "5d"
                           1y  = ~250 trading days (for 52W + EMA50)
                           6mo = ~130 trading days (enough for all indicators)

    Returns:
        DataFrame with columns: Open High Low Close Volume
        None if fetch fails or data is empty

    Why history() only:
        We use ONLY ticker.history() — no fast_info, no .info
        history() is the most stable API across all yfinance versions.
        It works as long as Yahoo Finance exists.
    """
    try:
        df = yf.Ticker(yahoo_sym).history(period=period, interval="1d")

        # Safety checks
        if df is None or df.empty:
            return None

        if len(df) < 10:
            # Less than 10 rows — not enough for any calculation
            return None

        # Return only OHLCV columns — clean and consistent
        return df[["Open", "High", "Low", "Close", "Volume"]].copy()

    except Exception:
        return None


# ── FETCH NIFTY 50 ────────────────────────────────────────────
def fetch_nifty(symbol="^NSEI"):
    """
    Fetch Nifty 50 index price and change%.

    Returns dict:
        price   → current Nifty value
        change  → day change %
        status  → "ok" or "error"
    """
    try:
        df = yf.Ticker(symbol).history(period="5d", interval="1d")

        if df is None or df.empty or len(df) < 2:
            raise ValueError("Not enough Nifty data")

        price  = round(float(df["Close"].iloc[-1]), 2)
        prev   = round(float(df["Close"].iloc[-2]), 2)
        change = round(((price - prev) / prev) * 100, 2)

        return {
            "price":  price,
            "change": change,
            "status": "ok"
        }

    except Exception as e:
        return {
            "price":  0,
            "change": 0,
            "status": "error",
            "error":  str(e)
        }


# ── FETCH ALL STOCKS ──────────────────────────────────────────
def fetch_all_stocks(stocks_list, period="1y", verbose=True):
    """
    Fetch OHLCV for all stocks in the list.
    Handles errors per stock — one failure won't stop others.

    Args:
        stocks_list : list of tuples → from stocks.py STOCKS
        period      : str            → how much history to fetch
        verbose     : bool           → print progress

    Returns:
        dict  →  { "HDFCBANK": DataFrame, "BEL": DataFrame, ... }
                 failed stocks are not included in the dict
    """
    results   = {}
    ok_count  = 0
    err_count = 0
    errors    = []

    total = len(stocks_list)

    for i, (sym, yahoo_sym, name, sector) in enumerate(stocks_list):

        if verbose:
            print(f"  [{i+1:>3}/{total}]  {sym:<14} ({yahoo_sym})",
                  end="  ", flush=True)

        df = fetch_ohlcv(yahoo_sym, period=period)

        if df is not None:
            results[sym] = {
                "df":     df,
                "yahoo":  yahoo_sym,
                "name":   name,
                "sector": sector,
            }
            ok_count += 1
            if verbose:
                print(f"✅  {len(df)} rows")
        else:
            err_count += 1
            errors.append(sym)
            if verbose:
                print("❌  Failed")

        # Polite delay — avoid Yahoo rate limiting
        time.sleep(REQUEST_DELAY)

    if verbose:
        print()
        print(f"  Fetched : {ok_count}/{total}")
        if errors:
            print(f"  Failed  : {', '.join(errors)}")
            print(f"  Tip     : Check these symbols on finance.yahoo.com")

    return results


def fetch_live_price(yahoo_sym):
    """
    Fetch the latest live price of a stock from Yahoo Finance.
    Returns the price (float) or None if fetch fails.
    """
    try:
        # Fetching with period="1d" is extremely fast
        df = yf.Ticker(yahoo_sym).history(period="1d")
        if df is not None and not df.empty:
            return round(float(df["Close"].iloc[-1]), 2)
        return None
    except Exception as e:
        print(f"[fetcher] Error fetching live price for {yahoo_sym}: {e}")
        return None


# ── TEST ──────────────────────────────────────────────────────
if __name__ == "__main__":
    from stocks import STOCKS, NIFTY_SYM
    from datetime import datetime

    print("=" * 60)
    print("  fetcher.py — TEST RUN")
    print("=" * 60)
    print(f"  yfinance : {yf.__version__}")
    print(f"  Time     : {datetime.now().strftime('%d %b %Y  %H:%M:%S')}")
    print()

    # Test 1 — Nifty
    print("─" * 60)
    print("  TEST 1 : Nifty 50")
    print("─" * 60)
    nifty = fetch_nifty(NIFTY_SYM)
    if nifty["status"] == "ok":
        sign = "+" if nifty["change"] >= 0 else ""
        print(f"  ✅  ₹{nifty['price']:,.2f}  "
              f"({sign}{nifty['change']}%)")
    else:
        print(f"  ❌  {nifty.get('error')}")
    print()

    # Test 2 — Single stock
    print("─" * 60)
    print("  TEST 2 : Single stock (HDFCBANK)")
    print("─" * 60)
    df = fetch_ohlcv("HDFCBANK.NS", period="1y")
    if df is not None:
        print(f"  ✅  {len(df)} rows fetched")
        print(f"  Columns  : {list(df.columns)}")
        print(f"  Latest   : {df.index[-1].date()}")
        print(f"  Close    : ₹{df['Close'].iloc[-1]:,.2f}")
        print(f"  Volume   : {int(df['Volume'].iloc[-1]):,}")
    else:
        print("  ❌  Failed")
    print()

    # Test 3 — First 5 stocks from stocks.py
    print("─" * 60)
    print(f"  TEST 3 : First 5 stocks from stocks.py")
    print("─" * 60)
    test_batch = STOCKS[:5]
    fetched = fetch_all_stocks(test_batch, period="1y", verbose=True)
    print()

    # Summary
    print("─" * 60)
    if len(fetched) == len(test_batch):
        print(f"  ✅  ALL GOOD — fetcher.py is working correctly")
        print(f"  Next step: python indicators.py")
    else:
        failed = [s[0] for s in test_batch if s[0] not in fetched]
        print(f"  ⚠   {len(fetched)}/{len(test_batch)} ok")
        print(f"  Failed: {failed}")
        print(f"  Fix: check Yahoo symbol for these stocks")
    print("=" * 60)
