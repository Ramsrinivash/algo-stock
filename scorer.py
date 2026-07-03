# =============================================================
# scorer.py — SCORING & SIGNAL LOGIC ONLY
# =============================================================
# Scoring based on new R-Multiple Blueprint (v2.0)
#
# 100-point scorecard:
#   1. RSI (20 pts)          — 52-65 ideal, 65-70 partial, >70 = -10
#   2. EMA50 Distance (25 pts) — PRIMARY: 0-4% pullback ideal
#   3. MACD (15 pts)         — bull+rising = +15, bull only = +8
#   4. ATR Volatility (15 pts)— ≥3% = +15, ≥2% = +10, ≥1.5% = +5
#   5. Volume (10 pts)       — ≥2x = +10, ≥1.3x = +6, <0.8x = -8
#   6. ADX Trend (10 pts)    — ≥30 = +10, ≥25 = +6, <20 = -5
#   7. EMA20 Distance (5 pts) — 0-5% = +5, >8% = -3
#   8. BB Position (5 pts)   — 40-75% = +5, >90% = -8
# Bonuses (up to +25 more):
#   9. Weekly Uptrend       +5
#  10. Supertrend BUY       +5  / Supertrend SELL -10
#  11. 52W Breakout         +5
#  12. Pullback Buy Zone    +5
#  13. Mansfield RS > 0     +5
#
# Hard Filters (return 0 if any fail):
#   price < 20 | avgVol < 100k | ATR% < 1.5% | price < EMA50×0.95
#
# Signal Thresholds:
#   STRONG BUY >= 85
#   BUY        >= 60
#   WATCH      >= 40
#   AVOID      <  40
# =============================================================

# ── SCORE WEIGHTS ─────────────────────────────────────────────
# These values MUST match the max pts in each section of score_stock() below.
# If you change a section's max pts, update the corresponding key here too.
WEIGHTS = {
    # Core scoring sections (max pts per section)
    "freshness_max":      20,   # 1-day old cross = 20pts, 2d = 14, 3d = 9, else 0
    "supertrend_dist":    15,   # ST BUY within 4% = 15, within 8% = 9, else 4
    "adx_strong":         15,   # ADX >= 30 = 15, >= 25 = 11, >= 20 = 6, < 20 = 0
    "volume_max":         13,   # >= 2x = 13, >= 1.5x = 9, >= 0.8x = 5, < 0.8x = -5
    "rsi_max":            13,   # RSI near 60 = 13, near 50-70 = 8, else = 4
    "atr_max":            13,   # ATR% >= 2.5 = 13, >= 1.8 = 8, else = 4
    "ema_gap_max":        11,   # EMA9/EMA21 gap <= 3% = 11, <= 6% = 6, else = 2
    # Bonus points
    "weekly_bull":         5,   # Weekly trend UPTREND
    "weekly_ema_bull":     3,   # Weekly EMA9 > EMA25
    "weekly_st_buy":       3,   # Weekly Supertrend BUY
    "supertrend_buy":      5,   # Daily Supertrend BUY
    "supertrend_sell":   -10,   # Daily Supertrend SELL (penalty)
    "breakout_52w":        5,   # 52-week high breakout
    "pullback_buy":        5,   # Pullback to key EMA
    "mansfield_rs_bull":   5,   # Outperforming Nifty 50
}

# Signal thresholds (recalibrated for new scoring system)
STRONG_BUY_THRESHOLD = 85
BUY_THRESHOLD = 60
WATCH_THRESHOLD = 40

def score_stock(s):
    """
    Calculate swing trade score based on Fresh Signal Scanner v4 scorecard (out of 100).
    Returns 0 if hard filters fail.
    """
    price    = s.get("price", 0)
    avg_vol  = s.get("avgVol20", 0)
    atr_pct  = s.get("atrPct", 0)
    ema50    = s.get("ema50", 0)

    # ── Hard Filters — fail immediately ────────────────────────
    if price < 20:                          return 0   # penny stock
    if avg_vol < 100000:                    return 0   # illiquid
    if atr_pct < 1.5:                       return 0   # not volatile enough
    if ema50 > 0 and price < ema50 * 0.95:  return 0   # too far below EMA50

    sc = 0

    # 1. Freshness (20 pts)
    days_ago = s.get("daysAgo", s.get("days_ago", 0))
    if 0 < days_ago <= 1: sc += 20
    elif days_ago == 2:   sc += 14
    elif days_ago == 3:   sc += 9
    else:                 sc += 0  # No fresh signal

    # 2. Distance from Supertrend line (15 pts)
    st_line = s.get("supertrendVal", 0)
    st_dir = s.get("supertrendDir", "")
    if price > 0 and st_line > 0 and st_dir == "BUY" and price >= st_line:
        st_dist = ((price - st_line) / price) * 100
        if st_dist <= 4:    sc += 15
        elif st_dist <= 8:  sc += 9
        else:               sc += 4
    else:
        sc += 0  # No Supertrend BUY proximity bonus if in SELL mode

    # 3. ADX strength (15 pts)
    # ADX measures trend strength, NOT direction.
    # Weak trend (< 20) = no trend worth trading = 0 pts (S3 fix: was wrongly 6)
    adx_val = s.get("adxVal", s.get("adx", 0))
    if adx_val >= 30:   sc += 15
    elif adx_val >= 25: sc += 11
    elif adx_val >= 20: sc += 6
    else:               sc += 0   # Directionless / choppy — no bonus

    # 4. Volume (13 pts)
    # Low volume (< 0.8x avg) is penalized — accumulation requires participation (S4 fix)
    vol_ratio = s.get("volRatio", s.get("vol_ratio", 1.0))
    if vol_ratio >= 2.0:    sc += 13
    elif vol_ratio >= 1.5:  sc += 9
    elif vol_ratio >= 0.8:  sc += 5
    else:                   sc -= 5   # Very low volume = negative signal

    # 5. RSI (13 pts)
    rsi_val = s.get("rsi", 50)
    rsi_mid = abs(rsi_val - 60)
    if rsi_mid <= 5:    sc += 13
    elif rsi_mid <= 10: sc += 8
    else:               sc += 4

    # 6. ATR% (13 pts)
    if atr_pct >= 2.5:   sc += 13
    elif atr_pct >= 1.8: sc += 8
    else:                sc += 4

    # 7. EMA gap tightness — EMA9 vs EMA21 (11 pts)
    # Fixed: now uses ema21 to match standardized EMA9/EMA21 crossover (S2 fix)
    ema9  = s.get("ema9", 0)
    ema21 = s.get("ema21", 0)
    if ema21 > 0 and ema9 >= ema21:
        ema_gap = ((ema9 - ema21) / ema21) * 100
        if ema_gap <= 3:    sc += 11   # Very tight — just crossed, fresh
        elif ema_gap <= 6:  sc += 6
        else:               sc += 2    # Wide gap — too extended
    else:
        sc += 0  # ema9 below ema21 = bearish momentum — no bonus

    # Removed early return to allow bonus scoring logic

    # Weekly Uptrend alignment (+5)
    if s.get("weeklyTrend") == "UPTREND":
        sc += WEIGHTS["weekly_bull"]

    # Weekly EMA momentum — EMA9 > EMA25 on weekly chart (+3)
    # (computed by calc_weekly but was never scored — now used)
    if s.get("weeklyEmaBull", False):
        sc += 3

    # Weekly Supertrend also BUY (+3 extra)
    if s.get("weeklySupertrendDir") == "BUY":
        sc += 3

    # Supertrend: +5 if BUY, -10 if SELL (strong penalty)
    if s.get("supertrendDir") == "BUY":
        sc += WEIGHTS["supertrend_buy"]
    elif s.get("supertrendDir") == "SELL":
        sc -= 10                            # ST🔴 = strong penalty

    # 52-Week High Breakout with volume (+5)
    if s.get("breakout52w", False):
        sc += WEIGHTS["breakout_52w"]

    # Pullback Buy Zone confirmed (+5)
    # (uptrend + RSI cooling + touching EMA = lowest-risk entry)
    if s.get("pullbackBuy", False):
        sc += WEIGHTS["pullback_buy"]

    # Mansfield RS outperforming index (+5)
    if s.get("mansfieldRs", 0.0) > 0.0:
        sc += WEIGHTS["mansfield_rs_bull"]

    return max(0, sc)




# ── TREND CONTINUATION SCORE ──────────────────────────────────
def calculate_trend_continuation_score(s):
    """
    Calculate the Trend Continuation Score (0 to 15 points).
    """
    score = 0
    
    # 1. EMA stack (5 pts)
    e20 = s.get("ema20", 0)
    e50 = s.get("ema50", 0)
    e200 = s.get("ema200", 0)
    if e20 > e50 > e200:
        score += 5
        
    # 2. HH/HL (4 pts)
    if s.get("higherHighsLows", False):
        score += 4
        
    # 3. Pullback depth (3 pts)
    price = s.get("price", 0)
    if price > 0:
        near_ema20 = (e20 > 0 and abs(price - e20) / e20 <= 0.03)
        near_ema50 = (e50 > 0 and abs(price - e50) / e50 <= 0.03)
        if near_ema20 or near_ema50:
            score += 3
            
    # 4. Breakout volume surge (3 pts)
    vol_ratio = s.get("volRatio", 0)
    if vol_ratio >= 1.5 or s.get("volSpike", False):
        score += 3
        
    return score


# ── SIGNAL ────────────────────────────────────────────────────
def get_signal(score):
    """
    Args:
        score : int → 0-100
    Returns:
        str → "STRONG BUY" / "BUY" / "WATCH" / "AVOID"
    """
    if score >= STRONG_BUY_THRESHOLD: return "STRONG BUY"
    if score >= BUY_THRESHOLD:        return "BUY"
    if score >= WATCH_THRESHOLD:      return "WATCH"
    return "AVOID"


# ── MOMENTUM ───────────────────────────────────────────────
def get_momentum(s):
    """
    Returns high/med/low momentum label based on indicator alignment.
    Updated to use new R-Multiple blueprint indicators.
    """
    pts = sum([
        bool(s.get("aboveEma50")),            # in uptrend
        bool(s.get("macdAbove")),             # MACD above signal
        bool(s.get("adxStrong")),             # ADX > 25
        bool(s.get("supertrendDir") == "BUY"),# Supertrend BUY
        bool(s.get("volSpike")),              # volume spike
        bool(s.get("weeklyTrend") == "UPTREND"), # weekly aligned
    ])
    if pts >= 4: return "high"
    if pts >= 2: return "med"
    return "low"


# ── TREND LABEL ───────────────────────────────────────────────
def get_trend_label(days):
    """
    Args:
        days : int → consecutive days above EMA50
    Returns:
        tuple: (label, color, description, entry_timing)
    """
    if days == 0:
        return ("No Trend",       "red",    "Below EMA50 - downtrend",         "AVOID")
    elif days <= 5:
        return ("Fresh Trend",    "blue",   "Just started - lowest risk",       "IDEAL ENTRY")
    elif days <= 15:
        return ("Active Trend",   "green",  "Healthy - still good to enter",    "GOOD ENTRY")
    elif days <= 25:
        return ("Mature Trend",   "amber",  "Getting older - enter carefully",  "LATE ENTRY")
    elif days <= 35:
        return ("Extended Trend", "orange", "May reverse - high risk",          "RISKY")
    else:
        return ("Exhausted",      "red",    "Too old - reversal likely",        "AVOID")


# ── RSI LABEL ─────────────────────────────────────────────────
def get_rsi_label(rsi):
    """
    Args:
        rsi : float → 0-100
    Returns:
        tuple: (label, color, advice)
    """
    if rsi >= 70:
        return ("Overbought", "red",   "Too high - avoid buying now")
    elif rsi >= 60:
        return ("Strong",     "green", "Momentum - can enter, watch carefully")
    elif rsi >= 40:
        return ("Buy Zone",   "green", "Ideal swing entry - not overbought")
    elif rsi >= 30:
        return ("Weak",       "amber", "Recovering - wait for RSI to cross 40")
    else:
        return ("Oversold",   "amber", "Very oversold - may bounce, still risky")


# ── FULL ANALYSIS ─────────────────────────────────────────────
def get_full_analysis(s, capital=100000):
    """
    Complete analysis for one stock, including position sizing with 1% risk rule.
    Applies R:R minimum gate: if rr < 1.5 → downgrade to AVOID.
    """
    sc  = score_stock(s)
    sig = get_signal(sc)
    mom = get_momentum(s)
    trend_cont = calculate_trend_continuation_score(s)

    rsi_lbl,   rsi_color,   rsi_advice           = get_rsi_label(s.get("rsi", 50))
    trend_lbl, trend_color, trend_desc, trend_tim = get_trend_label(s.get("trendDays", 0))

    # ── R:R Minimum Gate ─────────────────────────────────
    # Even a perfect setup is skipped if R:R < 1.5 (T2 not worth the risk)
    rr = s.get("rr", 0)
    if rr > 0 and rr < 1.5 and sig in ["BUY", "STRONG BUY", "WATCH"]:
        sig = "AVOID"  # R:R too low to trade

    # ── Freshness Gate ────────────────────────────────────
    # A BUY/STRONG BUY requires a FRESH trigger:
    #   - Fresh EMA9/EMA21 crossover (within 3 days), OR
    #   - Fresh Supertrend flip GREEN (within 3 days), OR
    #   - Fresh 52-week breakout, OR
    #   - Fresh resistance breakout
    # Without any of these, the signal is capped at WATCH.
    # This prevents stale crossover stocks from scoring BUY.
    has_fresh_trigger = (
        s.get("freshEmaCross", False)        # EMA9 crossed above EMA21 ≤ 3 days ago
        or s.get("freshStFlip", False)       # Supertrend flipped GREEN ≤ 3 days ago
        or s.get("breakout52w", False)       # 52-week breakout today
        or s.get("breakoutResistance", False) # Resistance breakout today
    )
    if sig in ["BUY", "STRONG BUY"] and not has_fresh_trigger:
        sig = "WATCH"   # Good stock, but no fresh entry trigger yet

    if sig in ["BUY", "STRONG BUY"]:
        verdict = "Strong setup - consider entering"
        verdict_color = "green"
    elif sig == "WATCH":
        verdict = "Watchlist - wait for confirmation"
        verdict_color = "amber"
    else:
        verdict = "Avoid - setup not ready"
        verdict_color = "red"

    # ── Position sizing — 1% risk rule ──────────────────────
    price     = s.get("price", 0)
    sl_price  = s.get("slPrice", price)
    sl_points = max(price - sl_price, 0.01)
    max_risk  = capital * 0.01
    # Capital and risk calculations
    shares_risk = int(max_risk / sl_points)
    shares_cap  = int(capital / price) if price > 0 else 0

    if shares_cap > 0:
        shares = max(1, min(shares_risk, shares_cap))
    else:
        shares = 0

    cap_used  = round(shares * price, 2)
    max_loss  = round(shares * sl_points, 2)
    profit2   = round(shares * sl_points * 1.5, 2)   # T2 = +1.5R
    profit3   = round(shares * sl_points * 2.5, 2)   # T3 = +2.5R

    # ── Hold Duration Estimate ──────────────────────────────────
    atr_pct = s.get("atrPct", 0)
    if atr_pct >= 2.5:
        duration = "2–5 days"
    elif atr_pct >= 1.8:
        duration = "5–8 days"
    else:
        duration = "8–14 days"

    return {
        # Signal
        "score":                  sc,
        "trendContinuationScore": trend_cont,
        "signal":                 sig,
        "momentum":               mom,
        "verdict":                verdict,
        "verdictColor":           verdict_color,
        # RSI
        "rsiLabel":               rsi_lbl,
        "rsiColor":               rsi_color,
        "rsiAdvice":              rsi_advice,
        # Trend
        "trendLabel":             trend_lbl,
        "trendColor":             trend_color,
        "trendDesc":              trend_desc,
        "trendTiming":            trend_tim,
        # Position sizing
        "shares":                 shares,
        "capitalNeeded":          cap_used,
        "maxLoss":                max_loss,
        "profit2":                profit2,
        "profit3":                profit3,
        # Trade metadata
        "holdDuration":           duration,
        "rrGatePassed":           bool(rr >= 1.5),
    }
