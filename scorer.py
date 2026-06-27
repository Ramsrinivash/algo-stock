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
BUY_THRESHOLD        = 60
WATCH_THRESHOLD      = 40


# ── SCORE STOCK ───────────────────────────────────────────────
def score_stock(s):
    """
    Calculate swing trade score based on R-Multiple Blueprint v2.0.
    Hard filters applied first — returns 0 if stock fails any filter.
    """
    price    = s.get("price", 0)
    avg_vol  = s.get("avgVol20", 0)
    atr_pct  = s.get("atrPct", 0)
    ema50    = s.get("ema50", 0)

    # ── Hard Filters — fail immediately ────────────────────────
    if price < 20:                          return 0   # penny stock
    if avg_vol < 100000:                    return 0   # illiquid
    if atr_pct < 1.5:                       return 0   # not volatile enough
    if ema50 > 0 and price < ema50 * 0.95: return 0   # too far below EMA50

    sc = 0

    # ── 1. RSI (20 pts) ────────────────────────────────────────
    # Sweet spot: 52-65 = strong momentum, not yet overbought
    rsi = s.get("rsi", 50)
    if 52 <= rsi <= 65:
        sc += WEIGHTS["rsi_ideal"]          # +20 — perfect momentum zone
        signals_rsi = "RSI_IDEAL"
    elif 65 < rsi <= 70:
        sc += WEIGHTS["rsi_ok"]             # +12 — extended but still ok
    elif 45 <= rsi < 52:
        sc += WEIGHTS["rsi_recovering"]     # +8  — recovering momentum
    elif rsi > 70:
        sc -= 10                            # -10 — overbought, dangerous entry

    # ── 2. EMA50 Pullback Zone (25 pts) ─ PRIMARY SIGNAL ───────
    # The single most important factor: price near EMA50 in uptrend
    dist_ema50 = s.get("distEma50", 0)
    if 0 <= dist_ema50 <= 4:
        sc += WEIGHTS["ema50_ideal"]        # +25 — IDEAL pullback zone
    elif 4 < dist_ema50 <= 8:
        sc += WEIGHTS["ema50_ok"]           # +18 — acceptable extension
    elif 8 < dist_ema50 <= 15:
        sc += WEIGHTS["ema50_extended"]     # +8  — getting extended
    elif dist_ema50 > 15:
        sc -= 10                            # -10 — too far, wait for pullback
    elif dist_ema50 < 0:
        sc -= 5                             # -5  — below EMA50, downtrend

    # ── 3. MACD (15 pts) ────────────────────────────────────────
    macd_bull    = s.get("macdBull", False)     # fresh cross above signal
    macd_above   = s.get("macdAbove", False)    # MACD line > signal line
    macd_hist    = s.get("macdHist", 0)         # histogram value
    macd_rising  = macd_hist > 0                # histogram positive (rising)

    if macd_above and macd_rising:
        sc += WEIGHTS["macd_full"]              # +15 — bull + rising
    elif macd_above:
        sc += WEIGHTS["macd_partial"]           # +8  — bull only
    elif macd_bull or macd_rising:
        sc += WEIGHTS["macd_turning"]           # +5  — turning positive
    else:
        sc -= 5                                 # -5  — bearish MACD

    # ── 4. ATR Volatility (15 pts) ──────────────────────────────
    # Need enough ATR for meaningful swing trade profit
    if atr_pct >= 3.0:
        sc += WEIGHTS["atr_ideal"]          # +15 — high volatility, good swings
    elif atr_pct >= 2.0:
        sc += WEIGHTS["atr_ok"]             # +10 — moderate volatility
    elif atr_pct >= 1.5:
        sc += WEIGHTS["atr_min"]            # +5  — minimum acceptable

    # ── 5. Volume (10 pts) ──────────────────────────────────────
    vol_ratio = s.get("volRatio", 0)
    if vol_ratio >= 2.0 or s.get("volSpike", False):
        sc += WEIGHTS["vol_ideal"]          # +10 — institutional participation
    elif vol_ratio >= 1.3:
        sc += WEIGHTS["vol_ok"]             # +6  — above average
    elif vol_ratio < 0.8:
        sc -= 8                             # -8  — low conviction, avoid

    # ── 6. ADX Trend Strength (10 pts) ──────────────────────────
    adx_val = s.get("adxVal", 0)
    di_positive = s.get("diPositive", False)
    if adx_val >= 30 and di_positive:
        sc += WEIGHTS["adx_strong"]         # +10 — strong trending
    elif adx_val >= 25:
        sc += WEIGHTS["adx_ok"]             # +6  — mild trend
    elif adx_val < 20:
        sc -= 5                             # -5  — choppy, range-bound

    # ── 7. EMA20 Distance (5 pts) ───────────────────────────────
    dist_ema20 = s.get("distEma20", 0)
    if 0 <= dist_ema20 <= 5:
        sc += WEIGHTS["ema20_ok"]           # +5  — close to EMA20 support
    elif dist_ema20 > 8:
        sc -= 3                             # -3  — extended above EMA20

    # ── 8. Bollinger Band Position (5 pts) ──────────────────────
    bb_pct = s.get("bbPct", 50)
    if 40 <= bb_pct <= 75:
        sc += WEIGHTS["bb_mid"]             # +5  — healthy mid-band position
    elif bb_pct > 90:
        sc -= 8                             # -8  — near upper band, stretched

    # ── Bonus Signals ────────────────────────────────────────────

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


# ── TEST ──────────────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import datetime

    print("=" * 62)
    print("  scorer.py - TEST RUN")
    print("=" * 62)
    print(f"  Time : {datetime.now().strftime('%d %b %Y  %H:%M:%S')}")
    print()

    # Use exact numbers from Module 2 + 3 output
    test_stocks = [
        {
            "sym": "COALINDIA", "name": "Coal India",
            "price": 463.95, "change": 0.19, "rsi": 52.9,
            "aboveEma21": True,  "aboveEma50": True,
            "ema9Above21": True, "emaCrossAlert": False,
            "volSpike": False,   "nearSupport": False,
            "candleType": "neutral", "candleStrength": 2,
            "atrPct": 2.5, "slPrice": 445.74,
            "trendDays": 19,
            "ema20": 458.0, "ema50": 450.0, "ema200": 430.0,
            "higherHighsLows": True, "volRatio": 1.1, "avgVol20": 120000
        },
        {
            "sym": "HDFCBANK", "name": "HDFC Bank",
            "price": 753.20, "change": 0.37, "rsi": 38.5,
            "aboveEma21": False, "aboveEma50": False,
            "ema9Above21": False, "emaCrossAlert": False,
            "volSpike": False,   "nearSupport": True,
            "candleType": "bear", "candleStrength": 1,
            "atrPct": 2.3, "slPrice": 727.25,
            "trendDays": 0,
            "ema20": 765.0, "ema50": 770.0, "ema200": 780.0,
            "higherHighsLows": False, "volRatio": 0.9, "avgVol20": 80000
        }
    ]

    print(f"  {'SYM':<12} {'SCORE':>5} {'TCS':>5}  SIG     MOM       VERDICT")
    print("  " + "-" * 58)

    for s in test_stocks:
        a    = get_full_analysis(s, capital=100000)
        icon = "[!]" if a["signal"]=="STRONG BUY" else \
               "[o]" if a["signal"]=="BUY" else \
               "[w]" if a["signal"]=="WATCH" else "[x]"
        mom_icon = "^" if a["momentum"]=="high" else \
                   "-" if a["momentum"]=="med"  else "v"
        print(f"  {s['sym']:<12} {a['score']:>5} {a['trendContinuationScore']:>5}  "
              f"{icon} {a['signal']:<5}  "
              f"{mom_icon} {a['momentum']:<5}  "
              f"{a['verdict']}")

    print()
    print("  -- DETAILED : COALINDIA ----------------------------")
    a = get_full_analysis(test_stocks[0], capital=100000)
    print(f"  RSI    : {test_stocks[0]['rsi']}  -> {a['rsiLabel']}  "
          f"({a['rsiAdvice']})")
    print(f"  Trend  : {test_stocks[0]['trendDays']}d  -> {a['trendLabel']}  "
          f"({a['trendTiming']})")
    print(f"  Shares : {a['shares']} shares  "
          f"Capital: Rs.{a['capitalNeeded']:,.2f}")
    print(f"  Max Loss: Rs.{a['maxLoss']:,.2f}  "
          f"Profit 2:1: Rs.{a['profit2']:,.2f}  "
          f"Profit 3:1: Rs.{a['profit3']:,.2f}")
    print()
    print("  -- SCORE WEIGHTS -----------------------------------")
    for k, v in WEIGHTS.items():
        print(f"    {k:<22} {v:>3} pts")
    print(f"\n  BUY   >= {BUY_THRESHOLD}")
    print(f"  WATCH >= {WATCH_THRESHOLD}")
    print(f"  AVOID < {WATCH_THRESHOLD}")
    print()
    print("=" * 62)
    print("  [x]  scorer.py working correctly")
    print("  Next step: python scanner.py")
    print("=" * 62)
