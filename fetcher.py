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
    Fetch Nifty 50 index price, change%, and calculate circuit breaker status.
    """
    try:
        # Use Ticker.history for consistency with fetcher.py guidelines
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="120d", interval="1d")

        if df is None or df.empty or len(df) < 50:
            raise ValueError("Not enough Nifty data")

        today_close = float(df["Close"].iloc[-1])
        prev_close  = float(df["Close"].iloc[-2])
        day_change  = round(((today_close - prev_close) / prev_close) * 100, 2)

        # Calculate EMAs on Nifty
        close_series = df["Close"]
        ema50 = close_series.ewm(span=50, adjust=False).mean()
        above_ema50 = bool(today_close > ema50.iloc[-1])

        ema9 = close_series.ewm(span=9, adjust=False).mean()
        ema25 = close_series.ewm(span=25, adjust=False).mean()
        nifty_bull = bool(ema9.iloc[-1] > ema25.iloc[-1])

        # Circuit breaker conditions
        circuit_open = False
        reason = ""

        if day_change <= -1.0:
            circuit_open = True
            reason = f"Nifty fell {day_change:.2f}% today (>1% drop — no trades)"
        elif not above_ema50:
            circuit_open = True
            reason = f"Nifty below 50-EMA — market in downtrend, avoid fresh buys"
        elif not nifty_bull:
            circuit_open = True
            reason = f"Nifty EMA9 below EMA25 — short term trend bearish"
        elif day_change <= -0.5:
            reason = f"Nifty weak ({day_change:.2f}%) — reduce position size to 50%"

        return {
            "price":         round(today_close, 2),
            "change":        day_change,
            "status":        "ok",
            "above_ema50":   above_ema50,
            "nifty_bull":    nifty_bull,
            "circuit_open":  circuit_open,
            "reason":        reason,
            "reduce_size":   (day_change <= -0.5 and not circuit_open),
        }

    except Exception as e:
        return {
            "price":  0,
            "change": 0,
            "status": "error",
            "error":  str(e),
            "above_ema50": True,
            "nifty_bull": True,
            "circuit_open": False,
            "reason": f"Could not fetch Nifty: {e}",
            "reduce_size": False,
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


def fetch_ohlcv_1h(yahoo_sym, period="60d"):
    """
    Fetch hourly (1h) OHLCV data for one stock from Yahoo Finance.
    Used for multi-timeframe analysis of top candidates.
    """
    try:
        df = yf.Ticker(yahoo_sym).history(period=period, interval="1h")
        if df is None or df.empty:
            return None
        if len(df) < 10:
            return None
        return df[["Open", "High", "Low", "Close", "Volume"]].copy()
    except Exception as e:
        print(f"[fetcher] Error fetching 1h data for {yahoo_sym}: {e}")
        return None

