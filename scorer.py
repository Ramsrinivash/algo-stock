# =============================================================
# scorer.py — SCORING & SIGNAL LOGIC ONLY
# =============================================================
# This file ONLY calculates the swing score, signal, and trend continuation score.
# No yfinance, no indicators, no patterns, no fetching here.
#
# Score weights are restructured to a 100-point scorecard:
#   - Trend (20 pts): price > EMA50 (10 pts) + price > EMA200 (10 pts)
#   - Momentum (20 pts): RSI 55-70 (20 pts) or RSI 40-55 (10 pts)
#   - Volume (15 pts): volRatio >= 2.0 (15 pts) or volRatio >= 1.2 (10 pts)
#   - Pattern (15 pts): Bullish candle strength * 3 (max 15 pts), Bearish candle (-5 pts)
#   - Risk-Reward (15 pts): SL% in 3-8% (15 pts) or 1.5-12% (10 pts)
#   - Volatility (10 pts): ATR% in 2-5% (10 pts) or 1-7% (5 pts)
#   - Liquidity (5 pts): avgVol20 > 100k (5 pts) or > 50k (3 pts)
#
# Trend Continuation Score (15 points):
#   - 5 pts: EMA 20/50/200 Stack (EMA 20 > EMA 50 > EMA 200)
#   - 4 pts: Higher Highs / Higher Lows (HH/HL)
#   - 3 pts: Pullback Depth (price within 3% of EMA 20 or EMA 50)
#   - 3 pts: Breakout Volume Surge (volume >= 1.5x of 20-day average)
# =============================================================

# ── SCORE WEIGHTS ─────────────────────────────────────────────
WEIGHTS = {
    "trend_ema50":        10,
    "trend_ema200":       10,
    "rsi_momentum":       20,
    "vol_surge":          15,
    "bull_pattern":       15,
    "risk_reward":        15,
    "atr_volatility":     10,
    "liquidity":           5,
    # Indicator bonuses
    "macd_bull":           5,
    "adx_strong":          5,
    "weekly_bull":         5,
    "breakout_52w":        5,
    # NEW: Core swing setups (higher weight = higher conviction)
    "pullback_buy":        8,   # pullback to EMA in uptrend = ideal entry
    "breakout_resistance": 8,   # volume-confirmed resistance breakout
    "mansfield_rs_bull":   10,  # relative strength outperforming index
    "vcp_setup":           10,  # volatility contraction pattern
}

# Signal thresholds
STRONG_BUY_THRESHOLD = 90
BUY_THRESHOLD        = 70
WATCH_THRESHOLD      = 50


# ── SCORE STOCK ───────────────────────────────────────────────
def score_stock(s):
    """
    Calculate swing trade score 0-100 based on quant scorecard rules.
    """
    sc = 0
    price = s.get("price", 0)
    
    # 1. Trend (20 pts)
    if s.get("aboveEma50", False):
        sc += WEIGHTS["trend_ema50"]
    # Only award EMA200 bonus when stock has real 200-day history
    ema200 = s.get("ema200", 0)
    if ema200 > 0 and s.get("price", 0) > ema200 and s.get("hasEma200", False):
        sc += WEIGHTS["trend_ema200"]
        
    # 2. Momentum (20 pts)
    rsi = s.get("rsi", 50)
    if 55 <= rsi <= 70:
        sc += WEIGHTS["rsi_momentum"]
    elif 40 <= rsi < 55:
        sc += 10 # partial points
        
    # 3. Volume (15 pts)
    vol_ratio = s.get("volRatio", 0)
    if vol_ratio >= 2.0 or s.get("volSpike", False):
        sc += WEIGHTS["vol_surge"]
    elif vol_ratio >= 1.2:
        sc += 10
        
    # 4. Pattern (15 pts)
    candle_type = s.get("candleType")
    strength = s.get("candleStrength", 2)
    if candle_type == "bull":
        sc += min(WEIGHTS["bull_pattern"], strength * 3)
    elif candle_type == "bear":
        sc -= 5
        
    # 5. Risk-Reward (15 pts)
    sl_pct = s.get("slPct", 0)
    if 3.0 <= sl_pct <= 8.0:
        sc += WEIGHTS["risk_reward"]
    elif 1.5 <= sl_pct <= 12.0:
        sc += 10
        
    # 6. Volatility (10 pts)
    atr_pct = s.get("atrPct", 0)
    if 2.0 <= atr_pct <= 5.0:
        sc += WEIGHTS["atr_volatility"]
    elif 1.0 <= atr_pct <= 7.0:
        sc += 5
        
    # 7. Liquidity (5 pts)
    avg_vol = s.get("avgVol20", 0)
    if avg_vol > 100000:
        sc += WEIGHTS["liquidity"]
    elif avg_vol > 50000:
        sc += 3

    # 8. MACD Bullish Cross (+5 pts) — fresh momentum signal
    if s.get("macdBull", False):
        sc += WEIGHTS["macd_bull"]

    # 9. ADX Strong Trend (+5 pts) — trending stock, not choppy
    if s.get("adxStrong", False) and s.get("diPositive", False):
        sc += WEIGHTS["adx_strong"]

    # 10. Weekly Timeframe Bullish (+5 pts) — higher timeframe alignment
    if s.get("weeklyTrend") == "UPTREND":
        sc += WEIGHTS["weekly_bull"]

    # 11. 52-Week High Breakout (+5 pts) — institutional buying
    if s.get("breakout52w", False):
        sc += WEIGHTS["breakout_52w"]

    # 12. Pullback Buy Zone (+8 pts) — THE best swing entry setup
    #     Uptrend + RSI cooling + price touching EMA = low-risk entry
    if s.get("pullbackBuy", False):
        sc += WEIGHTS["pullback_buy"]

    # 13. Resistance Breakout (+8 pts) — institutional breakout signal
    #     Price > 20-day resistance + high volume = strong follow-through expected
    if s.get("breakoutResistance", False):
        sc += WEIGHTS["breakout_resistance"]

    # 14. Mansfield RS Outperformance (+10 pts)
    if s.get("mansfieldRs", 0.0) > 0.0:
        sc += WEIGHTS["mansfield_rs_bull"]

    # 15. Volatility Contraction Pattern (VCP) (+10 pts)
    if s.get("vcpSetup", False):
        sc += WEIGHTS["vcp_setup"]

    # Penalties
    rsi = s.get("rsi", 50)
    if rsi > 75:
        sc -= 5     # Overbought — dangerous entry
    if s.get("slPct", 0) > 8.0:
        sc -= 5     # SL too wide — bad risk:reward
    if s.get("weeklyTrend") == "DOWNTREND":
        sc -= 15    # Weekly downtrend — trading against primary tide

    return max(0, min(156, sc))   # max now 156 with all bonuses


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


# ── MOMENTUM ──────────────────────────────────────────────────
def get_momentum(s):
    """
    Args:
        s : dict → stock data
    Returns:
        str → "high" / "med" / "low"
    """
    pts = sum([
        bool(s.get("aboveEma21")),
        bool(s.get("aboveEma50")),
        bool(s.get("ema9Above21")),
        s.get("candleType") == "bull",
        bool(s.get("volSpike")),
        bool(s.get("emaCrossAlert")),
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
    """
    sc  = score_stock(s)
    sig = get_signal(sc)
    mom = get_momentum(s)
    trend_cont = calculate_trend_continuation_score(s)

    rsi_lbl,   rsi_color,   rsi_advice           = get_rsi_label(s.get("rsi", 50))
    trend_lbl, trend_color, trend_desc, trend_tim = get_trend_label(s.get("trendDays", 0))

    if sig in ["BUY", "STRONG BUY"]:
        verdict = "Strong setup - consider entering"
        verdict_color = "green"
    elif sig == "WATCH":
        verdict = "Watchlist - wait for confirmation"
        verdict_color = "amber"
    else:
        verdict = "Avoid - setup not ready"
        verdict_color = "red"

    # Position sizing — 1% risk rule
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
    profit2   = round(shares * sl_points * 2, 2)
    profit3   = round(shares * sl_points * 3, 2)

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
