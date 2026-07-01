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
WEIGHTS = {
    # Core 100-pt scorecard
    "rsi_ideal":          20,   # RSI 52-65
    "rsi_ok":             12,   # RSI 65-70
    "rsi_recovering":      8,   # RSI 45-52
    "ema50_ideal":        25,   # 0-4% above EMA50 (PRIMARY signal)
    "ema50_ok":           18,   # 4-8% above EMA50
    "ema50_extended":      8,   # 8-15% above EMA50
    "macd_full":          15,   # MACD bull + rising histogram
    "macd_partial":        8,   # MACD bull only (line > signal)
    "macd_turning":        5,   # Histogram turning up
    "atr_ideal":          15,   # ATR% >= 3.0
    "atr_ok":             10,   # ATR% >= 2.0
    "atr_min":             5,   # ATR% >= 1.5
    "vol_ideal":          10,   # Volume >= 2x
    "vol_ok":              6,   # Volume >= 1.3x
    "adx_strong":         10,   # ADX >= 30
    "adx_ok":              6,   # ADX >= 25
    "ema20_ok":            5,   # 0-5% above EMA20
    "bb_mid":              5,   # BB position 40-75%
    # Bonuses
    "weekly_bull":         5,
    "supertrend_buy":      5,
    "breakout_52w":        5,
    "pullback_buy":        5,
    "mansfield_rs_bull":   5,
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
    adx_val = s.get("adxVal", s.get("adx", 0))
    if adx_val >= 30:   sc += 15
    elif adx_val >= 25: sc += 11
    else:               sc += 6

    # 4. Volume (13 pts)
    vol_ratio = s.get("volRatio", s.get("vol_ratio", 1.0))
    if vol_ratio >= 2.0:   sc += 13
    elif vol_ratio >= 1.5: sc += 9
    else:                  sc += 5

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

    # 7. EMA gap tightness (11 pts)
    ema9 = s.get("ema9", 0)
    ema25 = s.get("ema25", 0)
    if ema25 > 0 and ema9 >= ema25:
        ema_gap = ((ema9 - ema25) / ema25) * 100
        if ema_gap <= 3:    sc += 11
        elif ema_gap <= 6:  sc += 6
        else:               sc += 2
    else:
        sc += 0  # No points if ema9 is below ema25

    # Removed early return to allow bonus scoring logic

    # Weekly Uptrend alignment (+5)
    if s.get("weeklyTrend") == "UPTREND":
        sc += WEIGHTS["weekly_bull"]

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
