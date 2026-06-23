# =============================================================
# patterns.py — CANDLESTICK PATTERNS & SUPPORT/RESISTANCE ONLY
# =============================================================
# This file ONLY detects candlestick patterns and S&R levels.
# No yfinance, no indicators, no scoring here.
#
# If you want to add a new pattern  → add ONLY in this file.
# If you want to change S&R method  → fix ONLY this file.
# If pattern rules need tuning      → fix ONLY this file.
#
# Functions:
#   candle_parts(o, h, l, c)        → tuple of candle measurements
#   detect_pattern(df)              → (name, type, note, strength)
#   find_support_resistance(df)     → (sup, res, dist_sup, dist_res, near)
#   get_pattern_info()              → dict of all pattern metadata
#
# Test:
#   python patterns.py
# =============================================================

import pandas as pd


# ── PATTERN METADATA ──────────────────────────────────────────
# Central reference for all patterns.
# Used by HTML screener for color coding and entry instructions.

PATTERN_INFO = {
    "Morning Star": {
        "type":     "bull",
        "strength": 5,
        "icon":     "⭐",
        "color":    "green",
        "entry":    "Strong 3-candle reversal — Enter at tomorrow open",
        "detail":   "Day1 bearish + Day2 small doji + Day3 bullish closing above Day1 midpoint"
    },
    "Bullish Engulfing": {
        "type":     "bull",
        "strength": 5,
        "icon":     "🕯",
        "color":    "green",
        "entry":    "Strong reversal — Enter tomorrow open, SL below today Low",
        "detail":   "Today's bullish body fully covers yesterday's bearish body"
    },
    "Bullish Marubozu": {
        "type":     "bull",
        "strength": 4,
        "icon":     "▮",
        "color":    "green",
        "entry":    "Strong momentum — Enter above today High tomorrow",
        "detail":   "Almost no wicks — body covers 80%+ of candle range"
    },
    "Hammer": {
        "type":     "bull",
        "strength": 4,
        "icon":     "🔨",
        "color":    "green",
        "entry":    "Reversal at support — Enter if next candle confirms green",
        "detail":   "Long lower wick (2x body), small upper wick — rejection of lower prices"
    },
    "Bullish Harami": {
        "type":     "bull",
        "strength": 3,
        "icon":     "◈",
        "color":    "blue",
        "entry":    "Weak signal — Wait for next green candle to confirm",
        "detail":   "Small bullish candle inside yesterday's large bearish body"
    },
    "Bullish Candle": {
        "type":     "bull",
        "strength": 2,
        "icon":     "▲",
        "color":    "green",
        "entry":    "Normal green candle — Check RSI and EMA before entering",
        "detail":   "Standard bullish candle — no special pattern"
    },
    "Inside Bar": {
        "type":     "neutral",
        "strength": 2,
        "icon":     "□",
        "color":    "amber",
        "entry":    "Consolidation — Wait for breakout above today High",
        "detail":   "Today's range is completely inside yesterday's range"
    },
    "Doji": {
        "type":     "neutral",
        "strength": 2,
        "icon":     "✚",
        "color":    "amber",
        "entry":    "Indecision — Do NOT enter yet. Wait for next candle direction",
        "detail":   "Open and Close almost equal — buyers and sellers balanced"
    },
    "Bearish Harami": {
        "type":     "bear",
        "strength": 1,
        "icon":     "◇",
        "color":    "red",
        "entry":    "Possible reversal — Avoid new entry, watch carefully",
        "detail":   "Small bearish candle inside yesterday's large bullish body"
    },
    "Bearish Candle": {
        "type":     "bear",
        "strength": 1,
        "icon":     "▼",
        "color":    "red",
        "entry":    "Red candle — Wait for green confirmation before entering",
        "detail":   "Standard bearish candle — no special pattern"
    },
    "Shooting Star": {
        "type":     "bear",
        "strength": 0,
        "icon":     "💫",
        "color":    "red",
        "entry":    "AVOID — Rejection at high. Strong bearish signal",
        "detail":   "Long upper wick (2x body), small lower wick — rejection of higher prices"
    },
    "Bearish Engulfing": {
        "type":     "bear",
        "strength": 0,
        "icon":     "🔻",
        "color":    "red",
        "entry":    "AVOID — Strong bearish signal. Do not buy. Wait for recovery",
        "detail":   "Today's bearish body fully covers yesterday's bullish body"
    },
    "Bearish Marubozu": {
        "type":     "bear",
        "strength": 0,
        "icon":     "▮",
        "color":    "red",
        "entry":    "AVOID — Strong sell pressure candle. Wait for bounce",
        "detail":   "Almost no wicks — strong bearish momentum candle"
    },
}


# ── CANDLE PARTS ──────────────────────────────────────────────
def candle_parts(o, h, l, c):
    """
    Break a single candle into its measured parts.

    Args:
        o : float → Open price
        h : float → High price
        l : float → Low price
        c : float → Close price

    Returns tuple:
        body       → size of real body |Close - Open|
        body_top   → top of body (max of Open/Close)
        body_bot   → bottom of body (min of Open/Close)
        upper_wick → High - body_top
        lower_wick → body_bot - Low
        candle_rng → total High - Low (never zero)
        is_bull    → True if Close > Open
    """
    body       = abs(c - o)
    body_top   = max(o, c)
    body_bot   = min(o, c)
    upper_wick = h - body_top
    lower_wick = body_bot - l
    candle_rng = (h - l) if (h - l) > 0 else 0.001
    is_bull    = c > o

    return body, body_top, body_bot, upper_wick, lower_wick, candle_rng, is_bull


# ── DETECT CANDLESTICK PATTERN ────────────────────────────────
def detect_pattern(df):
    """
    Detect candlestick pattern from last 3 candles in DataFrame.

    Uses last 3 rows:
        df.iloc[-1] → today    (t)
        df.iloc[-2] → yesterday (y)
        df.iloc[-3] → day before (dy)

    Pattern priority (checked in this order):
        1. Morning Star        (3-candle, strongest bull)
        2. Bullish Engulfing   (2-candle, strong bull)
        3. Bearish Engulfing   (2-candle, strong bear)
        4. Marubozu            (1-candle, momentum)
        5. Hammer              (1-candle, reversal bull)
        6. Shooting Star       (1-candle, reversal bear)
        7. Doji                (1-candle, indecision)
        8. Inside Bar          (2-candle, consolidation)
        9. Bullish Harami      (2-candle, weak bull)
       10. Bearish Harami      (2-candle, weak bear)
       11. Default             (plain bull or bear candle)

    Args:
        df : DataFrame → needs Open, High, Low, Close columns
                         minimum 3 rows required

    Returns:
        tuple: (pattern_name, candle_type, entry_note, strength)
          pattern_name : str  → e.g. "Bullish Engulfing"
          candle_type  : str  → "bull" / "bear" / "neutral"
          entry_note   : str  → plain English action
          strength     : int  → 0 (avoid) to 5 (strongest)
    """
    if len(df) < 3:
        return "No Data", "neutral", "Not enough candle data", 1

    # Extract last 3 candles
    t  = df.iloc[-1]    # today
    y  = df.iloc[-2]    # yesterday
    dy = df.iloc[-3]    # day before yesterday

    # Unpack OHLC for each candle
    to, th, tl, tc   = float(t["Open"]),  float(t["High"]),  float(t["Low"]),  float(t["Close"])
    yo, yh, yl, yc   = float(y["Open"]),  float(y["High"]),  float(y["Low"]),  float(y["Close"])
    dyo,dyh,dyl,dyc  = float(dy["Open"]), float(dy["High"]), float(dy["Low"]), float(dy["Close"])

    # Get candle parts for each
    tb,  tbt,  tbb,  tuw, tlw, tr,  tbull  = candle_parts(to,  th,  tl,  tc)
    yb,  ybt,  ybb,  yuw, ylw, yr,  ybull  = candle_parts(yo,  yh,  yl,  yc)
    dyb, dybt, dybb, dyuw,dylw,dyr, dybull = candle_parts(dyo, dyh, dyl, dyc)

    # ── PATTERN CHECKS (priority order) ───────────────────

    # 1. MORNING STAR (3-candle bullish reversal)
    #    Day1: big bearish candle
    #    Day2: small body (doji-like) — indecision
    #    Day3: bullish candle closing above Day1 midpoint
    if (not dybull
            and yb < dyb * 0.4          # Day2 body much smaller than Day1
            and tbull                    # Day3 is bullish
            and tc > (dyo + dyc) / 2):  # Day3 closes above Day1 midpoint
        p = PATTERN_INFO["Morning Star"]
        return "Morning Star", p["type"], p["entry"], p["strength"]

    # 2. BULLISH ENGULFING (2-candle)
    #    Yesterday bearish, today bullish body completely covers yesterday
    if (not ybull                # yesterday was bearish
            and tbull            # today is bullish
            and to < yc          # today opened below yesterday close
            and tc > yo          # today closed above yesterday open
            and tb > yb):        # today body bigger than yesterday
        p = PATTERN_INFO["Bullish Engulfing"]
        return "Bullish Engulfing", p["type"], p["entry"], p["strength"]

    # 3. BEARISH ENGULFING (2-candle)
    if (ybull                    # yesterday was bullish
            and not tbull        # today is bearish
            and to > yc          # today opened above yesterday close
            and tc < yo          # today closed below yesterday open
            and tb > yb):        # today body bigger
        p = PATTERN_INFO["Bearish Engulfing"]
        return "Bearish Engulfing", p["type"], p["entry"], p["strength"]

    # 4. MARUBOZU (strong momentum — almost no wicks)
    #    Body covers 80%+ of total range
    if tb / tr > 0.80 and tuw < tb * 0.1 and tlw < tb * 0.1:
        if tbull:
            p = PATTERN_INFO["Bullish Marubozu"]
            return "Bullish Marubozu", p["type"], p["entry"], p["strength"]
        else:
            p = PATTERN_INFO["Bearish Marubozu"]
            return "Bearish Marubozu", p["type"], p["entry"], p["strength"]

    # 5. HAMMER (bullish reversal)
    #    Long lower wick (≥ 2x body), tiny upper wick, small body
    if (tlw >= tb * 2.0
            and tuw <= tb * 0.5
            and tb / tr < 0.4):
        p = PATTERN_INFO["Hammer"]
        return "Hammer", p["type"], p["entry"], p["strength"]

    # 6. SHOOTING STAR (bearish rejection)
    #    Long upper wick (≥ 2x body), tiny lower wick, small body
    if (tuw >= tb * 2.0
            and tlw <= tb * 0.5
            and tb / tr < 0.4):
        p = PATTERN_INFO["Shooting Star"]
        return "Shooting Star", p["type"], p["entry"], p["strength"]

    # 7. DOJI (indecision)
    #    Body is less than 10% of total candle range
    if tb / tr < 0.1:
        p = PATTERN_INFO["Doji"]
        return "Doji", p["type"], p["entry"], p["strength"]

    # 8. INSIDE BAR (consolidation)
    #    Today's entire range is inside yesterday's range
    if th < yh and tl > yl:
        p = PATTERN_INFO["Inside Bar"]
        return "Inside Bar", p["type"], p["entry"], p["strength"]

    # 9. BULLISH HARAMI (weak bullish signal)
    #    Small bullish candle fully contained inside large bearish candle
    if (not ybull
            and tbull
            and tbt < ybt          # today body top inside yesterday body top
            and tbb > ybb          # today body bottom inside yesterday body bottom
            and tb < yb * 0.5):
        p = PATTERN_INFO["Bullish Harami"]
        return "Bullish Harami", p["type"], p["entry"], p["strength"]

    # 10. BEARISH HARAMI (weak bearish signal)
    if (ybull
            and not tbull
            and tbt < ybt          # today body top inside yesterday body top
            and tbb > ybb          # today body bottom inside yesterday body bottom
            and tb < yb * 0.5):
        p = PATTERN_INFO["Bearish Harami"]
        return "Bearish Harami", p["type"], p["entry"], p["strength"]

    # 11. DEFAULT — plain directional candle
    if tbull:
        p = PATTERN_INFO["Bullish Candle"]
        return "Bullish Candle", p["type"], p["entry"], p["strength"]
    else:
        p = PATTERN_INFO["Bearish Candle"]
        return "Bearish Candle", p["type"], p["entry"], p["strength"]


# ── SUPPORT & RESISTANCE ──────────────────────────────────────
def find_support_resistance(df, lookback=20):
    """
    Find support and resistance levels from recent price action.

    Method: Simple swing high/low over last N candles.
      Support    = lowest Low  in last 20 trading days
      Resistance = highest High in last 20 trading days

    Why 20 days:
      20 trading days ≈ 1 month of price action.
      Gives meaningful near-term S&R for swing trading.

    Args:
        df       : DataFrame → needs High, Low, Close columns
        lookback : int       → number of candles to look back (default 20)

    Returns:
        tuple:
          support    → support price level
          resistance → resistance price level
          dist_sup   → % distance from current price to support
          dist_res   → % distance from current price to resistance
          near_sup   → True if price within 3% of support (good entry)
    """
    recent = df.tail(lookback)
    price  = float(df["Close"].iloc[-1])

    support    = round(float(recent["Low"].min()),  2)
    resistance = round(float(recent["High"].max()), 2)

    dist_sup   = round(((price - support)    / price) * 100, 2)
    dist_res   = round(((resistance - price) / price) * 100, 2)

    # Near support = within 3% — ideal swing entry zone
    near_sup   = bool(dist_sup <= 3.0)

    return support, resistance, dist_sup, dist_res, near_sup


# ── GET PATTERN INFO ──────────────────────────────────────────
def get_pattern_info():
    """
    Returns the full PATTERN_INFO dict.
    Used by HTML screener for icons, colors, descriptions.
    """
    return PATTERN_INFO


# ── TEST ──────────────────────────────────────────────────────
if __name__ == "__main__":
    from fetcher import fetch_ohlcv
    from datetime import datetime

    print("=" * 65)
    print("  patterns.py — TEST RUN")
    print("=" * 65)
    print(f"  Time : {datetime.now().strftime('%d %b %Y  %H:%M:%S')}")
    print()

    test_stocks = [
        ("HDFCBANK",  "HDFCBANK.NS"),
        ("COALINDIA", "COALINDIA.NS"),
        ("BEL",       "BEL.NS"),
        ("NTPC",      "NTPC.NS"),
        ("SUNPHARMA", "SUNPHARMA.NS"),
    ]

    all_ok = True

    for sym, yahoo_sym in test_stocks:
        print(f"─" * 65)
        print(f"  {sym}")
        print(f"─" * 65)

        df = fetch_ohlcv(yahoo_sym, period="1mo")
        if df is None:
            print(f"  ❌  Could not fetch data")
            all_ok = False
            continue

        # Show last 3 candles used for detection
        last3 = df.tail(3)[["Open", "High", "Low", "Close"]]
        print(f"  Last 3 candles:")
        for date, row in last3.iterrows():
            bull = "🟢" if row["Close"] > row["Open"] else "🔴"
            print(f"    {bull} {str(date.date())}  "
                  f"O:{row['Open']:>8.2f}  "
                  f"H:{row['High']:>8.2f}  "
                  f"L:{row['Low']:>8.2f}  "
                  f"C:{row['Close']:>8.2f}")
        print()

        # Detect pattern
        name, ctype, note, strength = detect_pattern(df)
        type_icon = "🟢" if ctype == "bull" else \
                    "🔴" if ctype == "bear" else "🟡"

        print(f"  Pattern    : {type_icon} {name}  (strength {strength}/5)")
        print(f"  Action     : {note}")
        print()

        # Support & Resistance
        sup, res, dsup, dres, near = find_support_resistance(df)
        near_icon = " ⚡ NEAR SUPPORT — good entry zone!" if near else ""
        print(f"  Support    : ₹{sup:>10,.2f}  ({dsup:.1f}% away){near_icon}")
        print(f"  Resistance : ₹{res:>10,.2f}  (+{dres:.1f}% away)")
        print()

    print("=" * 65)
    if all_ok:
        print("  ✅  patterns.py working correctly")
        print("  Next step: python scorer.py")
    else:
        print("  ⚠   Some stocks failed — check above")
    print("=" * 65)
