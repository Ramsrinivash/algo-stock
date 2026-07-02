# =============================================================
# indicators.py — TECHNICAL INDICATORS ONLY
# =============================================================
# This file ONLY calculates technical indicators.
# No yfinance, no stock symbols, no patterns, no scoring here.
#
# If you want to change RSI period  → fix ONLY this file.
# If you want to change ATR method  → fix ONLY this file.
# If you want to add a new indicator → add ONLY in this file.
#
# All functions take a pandas DataFrame or Series as input.
# All functions return a float, int, or bool — nothing else.
#
# Functions:
#   calc_ema(series, period)   → float
#   calc_rsi(series, period)   → float
#   calc_atr(df, period)       → (float, float)
#   calc_ema_cross(series)     → bool
#   calc_trend_days(df)        → int
#   calc_price_data(df)        → dict
#   calc_all(df)               → dict  ← main function
#
# Test:
#   python indicators.py
# =============================================================

import pandas as pd


# ── EMA — Exponential Moving Average ─────────────────────────
def calc_ema(series, period):
    """
    Standard Exponential Moving Average.

    adjust=False → matches TradingView / Dhan / Zerodha exactly.
    Each day's EMA = (Close × multiplier) + (prev EMA × (1 - multiplier))
    where multiplier = 2 / (period + 1)

    Args:
        series : pd.Series → Close prices
        period : int       → 9 / 21 / 50

    Returns:
        float → today's EMA value
    """
    ema = series.ewm(span=period, adjust=False).mean()
    return round(float(ema.iloc[-1]), 2)


# ── RSI — Relative Strength Index ────────────────────────────
def calc_rsi(series, period=14):
    """
    Wilder's RSI — same formula used by TradingView, Dhan, Zerodha.

    Steps:
      1. Daily change = today Close - yesterday Close
      2. Gain = change if positive, else 0
      3. Loss = |change| if negative, else 0
      4. Smooth gains and losses with Wilder's method
         (ewm with alpha = 1/period)
      5. RS  = avg_gain / avg_loss
      6. RSI = 100 - (100 / (1 + RS))

    RSI Zones:
      70+   → Overbought  → avoid buying
      60-70 → Strong      → momentum stocks
      40-60 → Buy zone    → ideal for swing entry
      30-40 → Weak        → recovering, watch
      0-30  → Oversold    → may bounce, risky

    Args:
        series : pd.Series → Close prices
        period : int       → 14 (standard)

    Returns:
        float → RSI value (0 to 100)
    """
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)

    # Wilder smoothing = ewm with alpha = 1/period
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()

    rs  = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return round(float(rsi.iloc[-1]), 2)


# ── ATR — Average True Range ──────────────────────────────────
def calc_atr(df, period=14):
    """
    Wilder's Average True Range — measures daily volatility.
    Used to calculate stop-loss distance.

    True Range (TR) = max of:
      1. High - Low              (today's range)
      2. |High - Previous Close| (gap up)
      3. |Low  - Previous Close| (gap down)

    ATR = Wilder smoothed average of TR (ewm alpha = 1/period)

    How we use it:
      Stop-loss = Current Price - (ATR × 1.5)
      This places SL outside normal daily noise.

    Args:
        df     : DataFrame → needs High, Low, Close columns
        period : int       → 14 (standard)

    Returns:
        tuple: (atr_value, atr_pct)
          atr_value → ATR in price points (e.g. ₹18.5)
          atr_pct   → ATR as % of price  (e.g. 2.4%)
    """
    high       = df["High"]
    low        = df["Low"]
    prev_close = df["Close"].shift(1)

    # True Range = max of the 3 measures
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)

    # Wilder smoothing
    atr_series = tr.ewm(alpha=1/period, adjust=False).mean()
    atr_value  = round(float(atr_series.iloc[-1]), 2)

    # ATR as % of current price
    price   = float(df["Close"].iloc[-1])
    atr_pct = round((atr_value / price) * 100, 2) if price > 0 else 0

    return atr_value, atr_pct


# ── EMA CROSS ALERT ───────────────────────────────────────────
def calc_ema_cross(series, fast=9, slow=21, lookback=3):
    """
    Detects if EMA9 crossed ABOVE EMA21 in last N trading days.
    This is the fresh momentum buy signal for swing trading.

    Logic:
      Check last 3 days (today, yesterday, day before):
      If on any of those days:
        EMA9 > EMA21   (today)  AND
        EMA9 < EMA21   (previous day)
      → Crossover happened → return True

    Args:
        series   : pd.Series → Close prices
        fast     : int       → fast EMA period (default 9)
        slow     : int       → slow EMA period (default 21)
        lookback : int       → how many days to check (default 3)

    Returns:
        bool → True if fresh crossover detected
    """
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()

    for i in range(-1, -(lookback + 1), -1):
        try:
            crossed_today = ema_fast.iloc[i]   > ema_slow.iloc[i]
            was_below     = ema_fast.iloc[i-1] < ema_slow.iloc[i-1]
            if crossed_today and was_below:
                return True
        except IndexError:
            pass

    return False


# ── CHECK FRESH CROSSOVERS (EMA9/EMA21 & SUPERTREND FLIP) ────────
def check_fresh_crossovers(ema9_series, ema21_series, st_dir_series, lookback=3):
    """
    Detects if EMA9 crossed above EMA21 (standard) or Supertrend flipped GREEN
    within the last N trading days.

    Standardized to EMA9/EMA21 (matches TradingView, Zerodha, Dhan default).
    The slow EMA21 is more widely watched than EMA25 by Indian retail.

    Args:
        ema9_series  : pd.Series → EMA9 values (daily)
        ema21_series : pd.Series → EMA21 values (daily)
        st_dir_series: pd.Series → Supertrend direction ('BUY'/'SELL')
        lookback     : int       → how many recent candles to check (default 3)

    Returns:
        tuple: (fresh_ema, fresh_st, days_ago, trigger)
    """
    fresh_ema = False
    fresh_st  = False
    days_ago  = 0
    trigger   = ""

    for i in range(-1, -(lookback + 1), -1):
        try:
            # EMA9 crossed above EMA21 on day i
            crossed_ema = (
                ema9_series.iloc[i]   > ema21_series.iloc[i]
                and ema9_series.iloc[i-1] <= ema21_series.iloc[i-1]
            )
            # Supertrend flipped from SELL to BUY on day i
            flipped_st = (
                st_dir_series.iloc[i]   == "BUY"
                and st_dir_series.iloc[i-1] == "SELL"
            )
            if crossed_ema and not fresh_ema:
                fresh_ema = True
                if not trigger:
                    trigger  = "EMA9 crossed above EMA21"
                    days_ago = abs(i)
            if flipped_st and not fresh_st:
                fresh_st = True
                if not trigger:
                    trigger  = "Supertrend flipped GREEN"
                    days_ago = abs(i)
        except IndexError:
            pass

    return fresh_ema, fresh_st, days_ago, trigger


# ── MOVEMENT PREDICTION (5-FACTOR MOVEMENT ESTIMATOR) ─────────
def calc_movement_prediction(df, rsi_series, adx_val, rsi_val, vol_ratio):
    """
    Predicts if stock is more likely to go UP or DOWN based on 5 factors.
    Supports both uppercase and lowercase DataFrame columns.
    """
    votes = 0
    factors = []

    # Get close, high, low series safely
    close_col = "Close" if "Close" in df.columns else "close"
    high_col = "High" if "High" in df.columns else "high"
    low_col = "Low" if "Low" in df.columns else "low"
    
    close = df[close_col]
    high = df[high_col]
    low = df[low_col]

    # Factor 1: EMA momentum (EMA9 vs EMA25)
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema25 = close.ewm(span=25, adjust=False).mean()
    if float(ema9.iloc[-1]) > float(ema25.iloc[-1]):
        votes += 1
        factors.append("✅ EMA momentum UP")
    else:
        votes -= 1
        factors.append("❌ EMA momentum DOWN")

    # Factor 2: MACD histogram (momentum shift)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal_line
    hist_now = float(hist.iloc[-1])
    hist_prev = float(hist.iloc[-2])
    if hist_now > hist_prev:
        votes += 1
        factors.append("✅ MACD histogram rising (momentum UP)")
    else:
        votes -= 1
        factors.append("❌ MACD histogram falling (momentum DOWN)")

    # Factor 3: RSI trend (rising or falling over 3 days)
    rsi_now = float(rsi_series.iloc[-1])
    rsi_3ago = float(rsi_series.iloc[-4]) if len(rsi_series) >= 4 else rsi_now
    if rsi_now > rsi_3ago:
        votes += 1
        factors.append(f"✅ RSI rising ({rsi_3ago:.0f} → {rsi_now:.0f})")
    else:
        votes -= 1
        factors.append(f"❌ RSI falling ({rsi_3ago:.0f} → {rsi_now:.0f})")

    # Factor 4: Volume trend
    if vol_ratio >= 1.5:
        votes += 1
        factors.append(f"✅ Volume surging ({vol_ratio}x avg)")
    elif vol_ratio >= 1.2:
        votes += 0
        factors.append(f"⚡ Volume adequate ({vol_ratio}x avg)")
    else:
        votes -= 1
        factors.append(f"❌ Volume weak ({vol_ratio}x avg)")

    # Factor 5: Candle structure (higher highs + higher lows last 3 days)
    highs = high.iloc[-3:].values
    lows = low.iloc[-3:].values
    if len(highs) >= 3 and len(lows) >= 3:
        higher_highs = highs[-1] > highs[-2] > highs[-3]
        higher_lows = lows[-1] > lows[-2] > lows[-3]
        if higher_highs and higher_lows:
            votes += 1
            factors.append("✅ Higher highs + higher lows (strong structure)")
        elif higher_highs or higher_lows:
            votes += 0
            factors.append("⚡ Partial higher structure")
        else:
            votes -= 1
            factors.append("❌ Lower highs or lower lows (weak structure)")
    else:
        votes -= 1
        factors.append("❌ Insufficient data for candle structure")

    # Convert votes to probability
    up_probability = 50 + (votes * 9)
    up_probability = max(10, min(95, up_probability))

    if votes >= 3:
        prediction = "⬆️ STRONG UP"
        confidence = "High"
    elif votes == 2:
        prediction = "⬆️ LIKELY UP"
        confidence = "Medium"
    elif votes == 1:
        prediction = "↗️ SLIGHT UP BIAS"
        confidence = "Low"
    elif votes == 0:
        prediction = "↔️ NEUTRAL / CHOPPY"
        confidence = "None"
    elif votes == -1:
        prediction = "↘️ SLIGHT DOWN BIAS"
        confidence = "Low"
    elif votes == -2:
        prediction = "⬇️ LIKELY DOWN"
        confidence = "Medium"
    else:
        prediction = "⬇️ STRONG DOWN"
        confidence = "High"

    return {
        "prediction":     prediction,
        "confidence":     confidence,
        "up_prob":        up_probability,
        "votes":          votes,
        "factors":        factors,
    }


# ── TREND DAYS ────────────────────────────────────────────────
def calc_trend_days(df):
    """
    Count consecutive trading days where Close > EMA50.
    Tells you how long the current uptrend has been running.

    Entry risk by trend age:
      0    days → No uptrend     → Avoid
      1-5  days → Fresh trend    → Best entry
      6-15 days → Active trend   → Good entry
      16-25 days → Mature trend  → Enter carefully
      25+  days → Extended       → High reversal risk

    Args:
        df : DataFrame → needs Close column

    Returns:
        int → number of consecutive days above EMA50
    """
    close = df["Close"]
    ema50 = close.ewm(span=50, adjust=False).mean()

    # Create boolean series: True = above EMA50
    above = (close > ema50).values.tolist()

    # Reverse to count from today backwards
    above.reverse()

    count = 0
    for is_above in above:
        if is_above:
            count += 1
        else:
            break   # stop at first day below EMA50

    return count


# ── HIGHER HIGHS & HIGHER LOWS ────────────────────────────────
def calc_higher_highs_lows(df, window=5):
    """
    Check if stock is making higher highs and higher lows in recent price action.
    Finds the last two confirmed swing highs (peaks) and swing lows (troughs).
    
    Args:
        df     : DataFrame -> needs High and Low columns
        window : int       -> lookback window to confirm pivot points
        
    Returns:
        bool -> True if higher highs and higher lows are detected, else False
    """
    highs = df["High"].values
    lows = df["Low"].values
    
    if len(highs) < 2 * window + 2:
        return False
        
    peaks = []
    troughs = []
    
    # Scan backwards to find local peaks (High is greater than all surrounding values within window)
    for i in range(len(highs) - window - 1, window, -1):
        val = highs[i]
        is_peak = True
        for j in range(i - window, i + window + 1):
            if highs[j] > val:
                is_peak = False
                break
        if is_peak:
            if not peaks or abs(peaks[-1][0] - i) > window:
                peaks.append((i, val))
                if len(peaks) >= 2:
                    break
                    
    # Scan backwards to find local troughs (Low is less than all surrounding values within window)
    for i in range(len(lows) - window - 1, window, -1):
        val = lows[i]
        is_trough = True
        for j in range(i - window, i + window + 1):
            if lows[j] < val:
                is_trough = False
                break
        if is_trough:
            if not troughs or abs(troughs[-1][0] - i) > window:
                troughs.append((i, val))
                if len(troughs) >= 2:
                    break
                    
    higher_high = False
    higher_low = False
    
    if len(peaks) >= 2:
        if peaks[0][1] > peaks[1][1]:
            higher_high = True
    else:
        higher_high = highs[-1] > highs[-10] if len(highs) >= 10 else False
        
    if len(troughs) >= 2:
        if troughs[0][1] > troughs[1][1]:
            higher_low = True
    else:
        higher_low = lows[-1] > lows[-10] if len(lows) >= 10 else False
        
    return bool(higher_high and higher_low)


# ── VWAP — Volume Weighted Average Price ─────────────────────
def calc_vwap(df, period=20):
    """
    Volume Weighted Average Price (VWAP) over a rolling period.
    VWAP = sum((High + Low + Close)/3 * Volume) / sum(Volume)
    Fills NaN with Close price to prevent missing data.
    """
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    tp_vol = tp * df["Volume"]
    
    rolling_tp_vol = tp_vol.rolling(window=period).sum()
    rolling_vol = df["Volume"].rolling(window=period).sum()
    
    # Replace zeros or Nans safely
    vwap = rolling_tp_vol / rolling_vol
    vwap = vwap.fillna(df["Close"])
    return vwap


# ── PIVOT & CPR — Central Pivot Range ────────────────────────
def calc_pivot_cpr(df):
    """
    Calculate Pivot Points and CPR (Central Pivot Range) based on the completed previous day's session.
    Returns:
        dict: pivot, bc, tc, cprWidth, cprSignal
    """
    if len(df) < 2:
        return {
            "pivot": 0.0,
            "bc": 0.0,
            "tc": 0.0,
            "cprWidth": 0.0,
            "cprSignal": "NEUTRAL"
        }
    
    # Completed previous session is df.iloc[-2]
    previous = df.iloc[-2]
    latest = df.iloc[-1]
    
    high_prev = float(previous["High"])
    low_prev = float(previous["Low"])
    close_prev = float(previous["Close"])
    
    pivot = (high_prev + low_prev + close_prev) / 3
    bc = (high_prev + low_prev) / 2
    tc = (2 * pivot) - bc
    
    # Width of CPR as % of Pivot
    cpr_width = round(abs(tc - bc) / pivot * 100, 3) if pivot > 0 else 0.0
    
    # Latest close price
    close_latest = float(latest["Close"])
    cpr_min = min(tc, bc)
    cpr_max = max(tc, bc)
    
    if close_latest > cpr_max:
        cpr_signal = "BULLISH"
    elif close_latest < cpr_min:
        cpr_signal = "BEARISH"
    else:
        cpr_signal = "NEUTRAL"
        
    return {
        "pivot": round(pivot, 2),
        "bc": round(bc, 2),
        "tc": round(tc, 2),
        "cprWidth": cpr_width,
        "cprSignal": cpr_signal
    }


# ── SUPERTREND (10, 3) ────────────────────────────────────────
def calc_supertrend_full(df, period=10, multiplier=3):
    """
    Supertrend Indicator (10, 3) - matches TradingView exactly.
    Returns full series: (st_series, direction_series)
    """
    high = df.get("High", df.get("high"))
    low = df.get("Low", df.get("low"))
    close = df.get("Close", df.get("close"))
    prev_close = close.shift(1)
    
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    
    # Wilder smoothing (RMA)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    
    hl2 = (high + low) / 2
    bub = hl2 + (multiplier * atr)
    blb = hl2 - (multiplier * atr)
    
    fub = [0.0] * len(df)
    flb = [0.0] * len(df)
    st = [0.0] * len(df)
    direction = ["BUY"] * len(df)
    
    for i in range(len(df)):
        if i == 0:
            fub[0] = bub.iloc[0]
            flb[0] = blb.iloc[0]
            st[0] = fub[0]
            direction[0] = "SELL" if close.iloc[0] <= st[0] else "BUY"
            continue
            
        prev_fub = fub[i-1]
        prev_flb = flb[i-1]
        prev_close_val = close.iloc[i-1]
        
        # Final Upper Band
        if bub.iloc[i] < prev_fub or prev_close_val > prev_fub:
            fub[i] = bub.iloc[i]
        else:
            fub[i] = prev_fub
            
        # Final Lower Band
        if blb.iloc[i] > prev_flb or prev_close_val < prev_flb:
            flb[i] = blb.iloc[i]
        else:
            flb[i] = prev_flb
            
        # Supertrend direction shift checks
        prev_st = st[i-1]
        curr_close = close.iloc[i]
        
        if prev_st == prev_fub:
            if curr_close <= fub[i]:
                st[i] = fub[i]
                direction[i] = "SELL"
            else:
                st[i] = flb[i]
                direction[i] = "BUY"
        else: # prev_st == prev_flb
            if curr_close >= flb[i]:
                st[i] = flb[i]
                direction[i] = "BUY"
            else:
                st[i] = fub[i]
                direction[i] = "SELL"
                
    return pd.Series(st, index=df.index), pd.Series(direction, index=df.index)


def calc_supertrend(df, period=10, multiplier=3):
    """
    Supertrend Indicator (10, 3) - matches TradingView exactly.
    Calculates rolling upper and lower bands using ATR, and checks direction.
    """
    st_s, dir_s = calc_supertrend_full(df, period, multiplier)
    return round(float(st_s.iloc[-1]), 2), dir_s.iloc[-1]


# ── MACD — Moving Average Convergence Divergence ─────────────
def calc_macd(series, fast=12, slow=26, signal=9):
    """
    Standard MACD (12, 26, 9) — matches TradingView exactly.
    macdLine = EMA12 - EMA26
    signalLine = EMA9 of macdLine
    histogram = macdLine - signalLine
    macdBull = True if MACD just crossed above signal line

    Returns:
        dict: macdLine, macdSignal, macdHist, macdBull
    """
    ema_fast   = series.ewm(span=fast,   adjust=False).mean()
    ema_slow   = series.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line= macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = macd_line - signal_line

    # Bullish cross: MACD crossed above signal in last 3 bars
    macd_bull = False
    for i in range(-1, -4, -1):
        try:
            if macd_line.iloc[i] > signal_line.iloc[i] and \
               macd_line.iloc[i-1] < signal_line.iloc[i-1]:
                macd_bull = True
                break
        except IndexError:
            pass

    return {
        "macdLine":   round(float(macd_line.iloc[-1]),   4),
        "macdSignal": round(float(signal_line.iloc[-1]), 4),
        "macdHist":   round(float(histogram.iloc[-1]),   4),
        "macdBull":   macd_bull,
        "macdAbove":  bool(macd_line.iloc[-1] > signal_line.iloc[-1]),
    }


# ── BOLLINGER BANDS (20, 2) ───────────────────────────────────
def calc_bollinger(df, period=20, std_dev=2):
    """
    Bollinger Bands (20, 2) — matches TradingView exactly.
    Mid = 20-day SMA
    Upper = Mid + 2 * StdDev
    Lower = Mid - 2 * StdDev
    Squeeze = Band width < 5% of mid price (breakout incoming)

    Returns:
        dict: bbUpper, bbMid, bbLower, bbWidth, bbSqueeze, nearLowerBand
    """
    close    = df["Close"]
    mid      = close.rolling(window=period).mean()
    std      = close.rolling(window=period).std()
    upper    = mid + std_dev * std
    lower    = mid - std_dev * std

    bb_mid   = round(float(mid.iloc[-1]),   2)
    bb_upper = round(float(upper.iloc[-1]), 2)
    bb_lower = round(float(lower.iloc[-1]), 2)
    price    = round(float(close.iloc[-1]), 2)

    # Band width as % of mid — squeeze when narrow
    bb_width   = round(((bb_upper - bb_lower) / bb_mid) * 100, 2) if bb_mid > 0 else 0.0
    bb_squeeze = bool(bb_width < 5.0)   # < 5% = tight squeeze = breakout incoming
    near_lower = bool(price <= bb_lower * 1.02)  # within 2% of lower band
    near_upper = bool(price >= bb_upper * 0.98)  # within 2% of upper band

    return {
        "bbUpper":     bb_upper,
        "bbMid":       bb_mid,
        "bbLower":     bb_lower,
        "bbWidth":     bb_width,
        "bbSqueeze":   bb_squeeze,
        "nearLowerBand": near_lower,
        "nearUpperBand": near_upper,
    }


# ── ADX — Average Directional Index (14) ─────────────────────
def calc_adx(df, period=14):
    """
    Average Directional Index — measures TREND STRENGTH (not direction).
    ADX > 25 = strong trend (good for swing entry)
    ADX < 20 = choppy / sideways (avoid)

    Uses Wilder's smoothing — matches TradingView.

    Returns:
        dict: adxVal, adxStrong, plusDI, minusDI
    """
    high  = df["High"]
    low   = df["Low"]
    close = df["Close"]

    prev_high  = high.shift(1)
    prev_low   = low.shift(1)
    prev_close = close.shift(1)

    # True Range
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)

    # Directional Movement
    plus_dm  = high - prev_high
    minus_dm = prev_low - low

    plus_dm  = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    # Wilder smoothing
    atr_s    = tr.ewm(alpha=1/period,       adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(alpha=1/period,  adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr_s

    dx       = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).fillna(0)
    adx      = dx.ewm(alpha=1/period, adjust=False).mean()

    adx_val   = round(float(adx.iloc[-1]),      2)
    plus_val  = round(float(plus_di.iloc[-1]),  2)
    minus_val = round(float(minus_di.iloc[-1]), 2)

    return {
        "adxVal":    adx_val,
        "adxStrong": bool(adx_val > 25),   # strong trending
        "adxTrend":  bool(adx_val > 20),   # mild trend
        "plusDI":    plus_val,
        "minusDI":   minus_val,
        "diPositive": bool(plus_val > minus_val),  # bullish direction
    }


# ── PRICE DATA FROM OHLCV ─────────────────────────────────────
def calc_price_data(df):
    """
    Extract price, change%, volume, 52W data from OHLCV DataFrame.
    Also includes: Gap-Up/Down detection, 52W High Breakout flag.
    """
    latest    = df.iloc[-1]
    previous  = df.iloc[-2]

    price      = round(float(latest["Close"]),   2)
    prev_close = round(float(previous["Close"]), 2)
    change_pct = round(((price - prev_close) / prev_close) * 100, 2)

    today_open = round(float(latest["Open"]),  2)
    prev_high  = round(float(previous["High"]), 2)
    prev_low   = round(float(previous["Low"]),  2)

    today_vol  = int(latest["Volume"])
    avg_vol_20 = int(df["Volume"].tail(21).iloc[:-1].mean())
    vol_spike  = bool(today_vol > avg_vol_20 * 2)
    vol_ratio  = round(today_vol / avg_vol_20, 2) if avg_vol_20 > 0 else 0.0

    high_52w   = round(float(df["High"].max()), 2)
    low_52w    = round(float(df["Low"].min()),  2)
    w52_range  = high_52w - low_52w
    w52_pct    = round(((price - low_52w) / w52_range) * 100, 1) \
                 if w52_range > 0 else 50.0

    # Gap detection: open > prev high = gap up; open < prev low = gap down
    gap_up   = bool(today_open > prev_high * 1.005)   # 0.5% buffer
    gap_down = bool(today_open < prev_low  * 0.995)

    # 52W Breakout: stock within top 10% of 52-week range with volume
    near52w_high    = bool(w52_pct >= 90)
    breakout52w     = bool(near52w_high and vol_spike)

    return {
        "price":       price,
        "prevClose":   prev_close,
        "change":      change_pct,
        "dayHigh":     round(float(latest["High"]), 2),
        "dayLow":      round(float(latest["Low"]),  2),
        "volume":      today_vol,
        "avgVol20":    avg_vol_20,
        "volSpike":    vol_spike,
        "volRatio":    vol_ratio,
        "high52w":     high_52w,
        "low52w":      low_52w,
        "w52Pct":      w52_pct,
        "gapUp":       gap_up,
        "gapDown":     gap_down,
        "near52wHigh": near52w_high,
        "breakout52w": breakout52w,
    }


# ── MANSFIELD RELATIVE STRENGTH ───────────────────────────────
def calc_mansfield_rs(stock_close, nifty_close, period=50):
    """
    Calculate Mansfield Relative Strength of a stock against a benchmark index.
    
    Formula:
        RS(t) = StockClose(t) / BenchmarkClose(t)
        BaseRS(t) = SMA(RS, period)
        MansfieldRS(t) = ((RS(t) / BaseRS(t)) - 1) * 10
        
    Args:
        stock_close : pd.Series → Close prices of the stock
        nifty_close : pd.Series → Close prices of Nifty 50
        period      : int       → SMA period (standard 50 daily logs)
        
    Returns:
        float → Mansfield RS value (positive indicates outperformance)
    """
    # Align the time series by date index
    ratio = stock_close / nifty_close
    
    # Fill any missing values after alignment
    ratio = ratio.ffill().bfill()
    
    if len(ratio) < period:
        return 0.0
        
    base_rs = ratio.rolling(window=period).mean()
    mansfield_rs = ((ratio / base_rs) - 1) * 10
    
    return round(float(mansfield_rs.iloc[-1]), 2)


# ── VOLATILITY CONTRACTION PATTERN (VCP) & VOL DRY-UP (VDU) ──
def calc_vcp_vdu(df):
    """
    Quantifies the Volatility Contraction Pattern (VCP) & Volume Dry-Up (VDU).
    Checks if stock price volatility is contracting over the last 5 days
    compared to the last 20 days, and if volume is significantly lower.
    
    Args:
        df : pd.DataFrame → OHLCV
        
    Returns:
        bool → True if VCP setup confirmed
    """
    if len(df) < 20:
        return False
        
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    volume = df["Volume"]
    
    # Calculate typical daily volatility range %
    range_pct = (high - low) / close * 100
    
    avg_range_5 = range_pct.iloc[-5:].mean()
    avg_range_20 = range_pct.iloc[-20:].mean()
    
    avg_vol_5 = volume.iloc[-5:].mean()
    avg_vol_20 = volume.iloc[-20:].mean()
    
    # Volatility is contracting (5-day range < 75% of 20-day range)
    # AND Volume is drying up (5-day volume < 70% of 20-day volume)
    vcp_setup = bool(avg_range_5 < avg_range_20 * 0.75 and avg_vol_5 < avg_vol_20 * 0.7)
    return vcp_setup


# ── RSI ZONE LABEL ────────────────────────────────────────────
def rsi_zone(rsi):
    """Convert RSI number to zone label."""
    if   rsi >= 70: return "OVERBOUGHT"
    elif rsi >= 60: return "STRONG"
    elif rsi >= 40: return "BUYZONE"
    elif rsi >= 30: return "WEAK"
    else:           return "OVERSOLD"


# ── CALC ALL — MAIN FUNCTION ──────────────────────────────────
def calc_all(df, df_nifty=None):
    """
    Run all indicator calculations on one stock's OHLCV DataFrame.
    This is the single function called by scanner.py.

    Args:
        df : DataFrame → OHLCV, minimum 60 rows recommended

    Returns:
        dict → all calculated values ready for screener
    """
    close = df["Close"]
    price = round(float(close.iloc[-1]), 2)

    # EMAs Series
    ema9_series = close.ewm(span=9, adjust=False).mean()
    ema25_series = close.ewm(span=25, adjust=False).mean()

    # EMAs
    e9   = round(float(ema9_series.iloc[-1]), 2)
    e21  = calc_ema(close, 21)
    e25  = round(float(ema25_series.iloc[-1]), 2)
    e50  = calc_ema(close, 50)
    e20  = calc_ema(close, 20)
    has_ema200 = len(close) >= 200
    e200 = calc_ema(close, 200) if has_ema200 else e50

    # Supertrend Series
    st_series, st_dir_series = calc_supertrend_full(df, 10, 3)
    st_val = round(float(st_series.iloc[-1]), 2)
    st_dir = st_dir_series.iloc[-1]

    # Fresh crossovers: EMA9/EMA21 (standardized) + Supertrend flip
    # Use ema21_series computed from close (not ema25 — standardized)
    ema21_series = close.ewm(span=21, adjust=False).mean()
    fresh_ema, fresh_st, days_ago, trigger = check_fresh_crossovers(
        ema9_series, ema21_series, st_dir_series, lookback=3
    )

    # EMA Crossover flag (legacy: EMA9/EMA21, lookback 3)
    ema_cross = calc_ema_cross(close)

    # RSI Series
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs       = avg_gain / avg_loss
    rsi_s    = 100 - (100 / (1 + rs))
    r        = round(float(rsi_s.iloc[-1]), 2)

    # ATR
    atr_val, atr_pct = calc_atr(df, 14)

    # ── R-Multiple Formula: 1R = 2 × ATR (industry standard) ─
    # risk per share = 2×ATR; all targets expressed as R-multiples
    R          = 2.0 * atr_val
    sl_price   = round(price - R, 2)
    sl_pct     = round(((price - sl_price) / price) * 100, 2) if price > 0 else 0.0
    sl_points  = R
    tgt1       = round(price + (1.0 * R), 2)
    tgt2       = round(price + (1.5 * R), 2)
    tgt3       = round(price + (2.5 * R), 2)
    rr_val     = round((tgt2 - price) / R, 1) if R > 0 else 0.0

    ema_bull_stack = bool(e9 > e21 > e50)

    # Quant Market Trend Classification
    if price > e50 and e20 > e50 and e50 > e200:
        market_trend = "UPTREND"
    elif price < e50 and e20 < e50 and e50 < e200:
        market_trend = "DOWNTREND"
    else:
        market_trend = "SIDEWAYS"

    # Price data (volRatio, gapUp, near52wHigh, breakout52w, etc.)
    _pd       = calc_price_data(df)
    vol_ratio = _pd.get("volRatio", 0)

    # ── Pullback Buy Zone ──────────────────────────────────────
    # Ideal swing entry: stock in uptrend, RSI cooling, price near key EMA
    near_ema20 = bool(e20 > 0 and abs(price - e20) / e20 <= 0.03)
    near_ema50 = bool(e50 > 0 and abs(price - e50) / e50 <= 0.03)
    pullback_buy = bool(
        price > e50         # above 50 EMA → in uptrend
        and 40 <= r <= 58   # RSI cooling but not breaking down
        and (near_ema20 or near_ema50)  # touching key EMA support
        and e9 > e21        # short-term momentum still positive
    )

    # ── Pullback Zone Details ───────────────────────────────────
    # Tell traders exactly WHICH EMA they're pulling back to and from where
    if pullback_buy:
        if near_ema20:
            pb_level    = "EMA20"
            pb_ema_val  = e20
        else:
            pb_level    = "EMA50"
            pb_ema_val  = e50
        # Zone: EMA ±2%
        pb_zone_low  = round(pb_ema_val * 0.98, 2)
        pb_zone_high = round(pb_ema_val * 1.02, 2)
        # Swing high it pulled back FROM: highest close in last 20 days (excluding today)
        pb_from_high = round(float(df["High"].iloc[-21:-1].max()), 2) if len(df) >= 22 else round(float(df["High"].max()), 2)
        pb_drop_pct  = round(((pb_from_high - price) / pb_from_high) * 100, 1) if pb_from_high > 0 else 0.0
    else:
        pb_level     = ""
        pb_zone_low  = 0.0
        pb_zone_high = 0.0
        pb_from_high = 0.0
        pb_drop_pct  = 0.0

    # ── NEW: Resistance-Level Breakout ──────────────────────
    # Classic breakout: today's close > previous 20-day high + volume
    if len(df) >= 22:
        prev_resistance = round(float(df["High"].iloc[-21:-1].max()), 2)
    else:
        prev_resistance = round(float(df["High"].max()), 2)

    breakout_resistance = bool(
        price > prev_resistance      # closed above resistance
        and vol_ratio >= 1.5         # volume confirms the move
        and price > e50              # above key EMA
    )

    # ── Supertrend (10, 3) ───────────────────────────────────
    st_val, st_dir = calc_supertrend(df, 10, 3)

    # ── Bollinger Bands (20, 2) ──────────────────────────────
    bb_data = calc_bollinger(df)

    # BB Position: 0% = at lower band, 100% = at upper band
    bb_range = bb_data["bbUpper"] - bb_data["bbLower"]
    if bb_range > 0:
        bb_pct = round(((price - bb_data["bbLower"]) / bb_range) * 100, 1)
        bb_pct = max(0.0, min(100.0, bb_pct))
    else:
        bb_pct = 50.0

    # ── VWAP (20) ────────────────────────────────────────────
    vwap_series = calc_vwap(df, 20)
    vwap_val = round(float(vwap_series.iloc[-1]), 2)
    close_above_vwap = bool(price > vwap_val)

    # ── CPR & Pivot ───────────────────────────────────────────
    cpr_data = calc_pivot_cpr(df)

    # ── MACD (12, 26, 9) ─────────────────────────────────────
    macd_data = calc_macd(close)

    # ── ADX (14) ─────────────────────────────────────────────
    adx_data = calc_adx(df)

    # ── VCP (Volatility Contraction Pattern) ─────────────────
    vcp_setup = calc_vcp_vdu(df)

    # Relative Strength vs Nifty 50
    if df_nifty is not None and not df_nifty.empty:
        mansfield_rs = calc_mansfield_rs(close, df_nifty["Close"])
    else:
        mansfield_rs = 0.0

    adx_val = adx_data.get("adxVal", 0)
    prediction = calc_movement_prediction(df, rsi_s, adx_val, r, vol_ratio)

    return {
        # Relative Strength & Volatility Contraction
        "mansfieldRs":      mansfield_rs,
        "vcpSetup":         vcp_setup,
        # CPR & Pivot
        **cpr_data,
        # VWAP
        "vwapVal":          vwap_val,
        "closeAboveVwap":   close_above_vwap,
        # Supertrend
        "supertrendVal":    st_val,
        "supertrendDir":    st_dir,
        # MACD (12, 26, 9)
        **macd_data,
        # Bollinger Bands (20, 2)
        **bb_data,
        "bbPct":            bb_pct,         # price position in BB range 0-100%
        # ADX (14)
        **adx_data,
        # EMA values
        "ema9":             e9,
        "ema20":            e20,
        "ema21":            e21,
        "ema25":            e25,
        "ema50":            e50,
        "ema200":           e200,
        # EMA flags
        "aboveEma21":       bool(price > e21),
        "aboveEma50":       bool(price > e50),
        "ema9Above21":      bool(e9 > e21),
        "ema9Above25":      bool(e9 > e25),
        "emaCrossAlert":    ema_cross,
        "emaBullStack":     ema_bull_stack,
        "hasEma200":        has_ema200,
        # Fresh crossovers
        "freshEmaCross":    fresh_ema,
        "freshStFlip":      fresh_st,
        "daysAgo":          days_ago,
        "trigger":          trigger,
        # Movement prediction
        "prediction":       prediction["prediction"],
        "predictionConfidence": prediction["confidence"],
        "predictionUpProb":     prediction["up_prob"],
        "predictionFactors":    prediction["factors"],
        # RSI
        "rsi":              r,
        "rsiZone":          rsi_zone(r),
        # ATR
        "atr":              atr_val,
        "atrPct":           atr_pct,
        # R-Multiple Trade levels (1R = 2×ATR)
        "R":                round(R, 2),      # 1R = risk per share
        "slPrice":          sl_price,         # Entry - 1R
        "slPct":            sl_pct,
        "tgt1":             tgt1,             # Entry + 1R   (R:R 1:1)
        "tgt2":             tgt2,             # Entry + 1.5R (R:R 1:1.5)
        "tgt3":             tgt3,             # Entry + 2.5R (R:R 1:2.5)
        "rr":               rr_val,           # R:R ratio (vs T2, always ~1.5)
        # EMA Distance metrics
        "distEma50":        round(((price - e50) / e50) * 100, 2) if e50 > 0 else 0.0,
        "distEma20":        round(((price - e20) / e20) * 100, 2) if e20 > 0 else 0.0,
        # Trend
        "trendDays":        calc_trend_days(df),
        "marketTrend":      market_trend,
        "higherHighsLows":  calc_higher_highs_lows(df),
        # Pullback Buy Zone
        "pullbackBuy":         pullback_buy,
        "nearEma20":           near_ema20,
        "nearEma50":           near_ema50,
        # Pullback Zone Details (populated only when pullbackBuy=True)
        "pullbackLevel":       pb_level,       # which EMA: "EMA20" or "EMA50"
        "pullbackZoneLow":     pb_zone_low,    # lower bound of the zone
        "pullbackZoneHigh":    pb_zone_high,   # upper bound of the zone
        "pullbackFromHigh":    pb_from_high,   # swing high stock pulled back from
        "pullbackDropPct":     pb_drop_pct,    # % drop from swing high to current price
        # Resistance Breakout
        "breakoutResistance":  breakout_resistance,
        "prevResistance20d":   prev_resistance,
        # Price data (includes gapUp, gapDown, near52wHigh, breakout52w, volRatio)
        **_pd,
    }



# ── WEEKLY TREND ──────────────────────────────────────────────
def calc_weekly(df_weekly):
    """
    Calculate weekly timeframe trend from weekly OHLCV data.
    Called separately by scanner.py with interval='1wk' data.

    Returns:
        dict: weeklyTrend, weeklyRsi, weeklyEma20AboveEma50, weeklySupertrendVal, weeklySupertrendDir, weeklyEma9, weeklyEma25, weeklyEmaBull
    """
    if df_weekly is None or len(df_weekly) < 30:
        return {
            "weeklyTrend":          "UNKNOWN",
            "weeklyRsi":            50.0,
            "weeklyEma20AboveEma50": False,
            "weeklySupertrendVal":  0.0,
            "weeklySupertrendDir":  "SELL",
            "weeklyEma9":           0.0,
            "weeklyEma25":          0.0,
            "weeklyEmaBull":        False,
        }

    close   = df_weekly["Close"]
    price   = float(close.iloc[-1])
    we20    = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    we50    = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
    wrsi    = calc_rsi(close, 14)

    we9     = float(close.ewm(span=9, adjust=False).mean().iloc[-1])
    we25    = float(close.ewm(span=25, adjust=False).mean().iloc[-1])
    weekly_ema_bull = bool(we9 > we25)

    st_val, st_dir = calc_supertrend(df_weekly, 10, 3)

    if price > we20 > we50:
        weekly_trend = "UPTREND"
    elif price < we20 and we20 < we50:
        weekly_trend = "DOWNTREND"
    else:
        weekly_trend = "SIDEWAYS"

    return {
        "weeklyTrend":          weekly_trend,
        "weeklyRsi":            wrsi,
        "weeklyEma20AboveEma50": bool(we20 > we50),
        "weeklySupertrendVal":  st_val,
        "weeklySupertrendDir":  st_dir,
        "weeklyEma9":           round(we9, 2),
        "weeklyEma25":          round(we25, 2),
        "weeklyEmaBull":        weekly_ema_bull,
    }


# ── HOURLY TIMEFRAME INDICATORS ───────────────────────────────
def calc_1h_indicators(df_1h):
    """
    Calculate key indicators from 1H (hourly) OHLCV data.
    Called ONLY for stocks that already scored BUY on the daily scan,
    to add multi-timeframe confirmation without slowing the full scan.

    Args:
        df_1h : DataFrame -> OHLCV with hourly candles (minimum 50 rows)

    Returns:
        dict:
            hourlyEmaBull    : bool -> EMA9 above EMA21 on 1H
            hourlyStDir      : str  -> 'BUY' or 'SELL' on 1H Supertrend
            hourlyTrend      : str  -> 'UPTREND' / 'DOWNTREND' / 'SIDEWAYS'
            hourlyFreshCross : bool -> EMA9 crossed EMA21 in last 3 hourly bars
    """
    _empty = {
        "hourlyEmaBull":    False,
        "hourlyStDir":      "SELL",
        "hourlyTrend":      "UNKNOWN",
        "hourlyFreshCross": False,
    }
    if df_1h is None or len(df_1h) < 50:
        return _empty

    try:
        close   = df_1h["Close"]
        h_e9    = close.ewm(span=9,  adjust=False).mean()
        h_e21   = close.ewm(span=21, adjust=False).mean()
        h_e50   = close.ewm(span=50, adjust=False).mean()
        price_h = float(close.iloc[-1])

        he9_v  = float(h_e9.iloc[-1])
        he21_v = float(h_e21.iloc[-1])
        he50_v = float(h_e50.iloc[-1])

        # Fresh EMA9/EMA21 cross on hourly (last 3 bars)
        h_fresh = False
        for i in range(-1, -4, -1):
            try:
                if h_e9.iloc[i] > h_e21.iloc[i] and h_e9.iloc[i-1] <= h_e21.iloc[i-1]:
                    h_fresh = True
                    break
            except IndexError:
                pass

        # Hourly Supertrend
        try:
            _, h_st_dir = calc_supertrend(df_1h, 10, 3)
        except Exception:
            h_st_dir = "SELL"

        # Hourly trend classification
        if price_h > he21_v > he50_v:
            h_trend = "UPTREND"
        elif price_h < he21_v and he21_v < he50_v:
            h_trend = "DOWNTREND"
        else:
            h_trend = "SIDEWAYS"

        return {
            "hourlyEmaBull":    bool(he9_v > he21_v),
            "hourlyStDir":      h_st_dir,
            "hourlyTrend":      h_trend,
            "hourlyFreshCross": h_fresh,
        }
    except Exception:
        return _empty



# ── TEST ──────────────────────────────────────────────────────
if __name__ == "__main__":
    from fetcher import fetch_ohlcv
    from datetime import datetime

    print("=" * 60)
    print("  indicators.py - TEST RUN")
    print("=" * 60)
    print(f"  Time : {datetime.now().strftime('%d %b %Y  %H:%M:%S')}")
    print()

    # Fetch HDFCBANK and COALINDIA (we know these work)
    test_stocks = [
        ("HDFCBANK",  "HDFCBANK.NS"),
        ("COALINDIA", "COALINDIA.NS"),
        ("BEL",       "BEL.NS"),
    ]

    for sym, yahoo_sym in test_stocks:
        print("-" * 60)
        print(f"  {sym}")
        print("-" * 60)

        df = fetch_ohlcv(yahoo_sym, period="1y")
        if df is None:
            print(f"  [x]  Could not fetch data")
            continue

        result = calc_all(df)

        print(f"  Price      : Rs.{result['price']:>10,.2f}")
        print(f"  Change     : {result['change']:>+6.2f}%")
        print(f"  RSI 14     : {result['rsi']:>6.1f}  ({result['rsiZone']})")
        print(f"  EMA 9      : Rs.{result['ema9']:>10,.2f}")
        print(f"  EMA 21     : Rs.{result['ema21']:>10,.2f}")
        print(f"  EMA 50     : Rs.{result['ema50']:>10,.2f}")
        print(f"  Above EMA21: {result['aboveEma21']}")
        print(f"  Above EMA50: {result['aboveEma50']}")
        print(f"  EMA9>EMA21 : {result['ema9Above21']}")
        print(f"  EMA Cross  : {result['emaCrossAlert']}")
        print(f"  ATR 14     : Rs.{result['atr']:>8,.2f}  ({result['atrPct']}%)")
        print(f"  Trend Days : {result['trendDays']} days")
        print(f"  Stop Loss  : Rs.{result['slPrice']:>10,.2f}  (-{result['slPct']}%)")
        print(f"  Target 2:1 : Rs.{result['tgt2']:>10,.2f}")
        print(f"  Target 3:1 : Rs.{result['tgt3']:>10,.2f}")
        print(f"  52W Pct    : {result['w52Pct']}%")
        print(f"  Vol Spike  : {result['volSpike']}")
        print(f"  HH/HL      : {result['higherHighsLows']}")
        print(f"  Supertrend : {result['supertrendDir']} ({result['supertrendVal']})")
        print(f"  VWAP (20)  : Rs.{result['vwapVal']:,.2f}  (Above: {result['closeAboveVwap']})")
        print(f"  CPR        : {result['cprSignal']} (Width: {result['cprWidth']}%, P:{result['pivot']}, TC:{result['tc']}, BC:{result['bc']})")
        print()

    print("=" * 60)
    print("  [x]  If numbers match Module 2 output -> indicators.py OK")
    print("  Next step: python patterns.py")
    print("=" * 60)
