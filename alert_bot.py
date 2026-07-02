# =============================================================
# alert_bot.py — TELEGRAM ALERT ENGINE (FREE)
# =============================================================
# Sends Telegram messages after every scan.
# Uses Telegram Bot API directly via HTTP — no library needed.
#
# Setup (one-time):
#   1. Open @BotFather in Telegram → /newbot → copy Bot Token
#   2. Open @userinfobot in Telegram → copy your Chat ID
#   3. Enter both in the app Settings modal → Test → Save
#
# Functions:
#   load_settings()              → dict
#   save_settings(data)          → bool
#   test_connection(token, chat_id) → (bool, message)
#   send_telegram(token, chat_id, text) → bool
#   send_scan_alert(summary)     → bool
# =============================================================

import json
import os
import requests
from datetime import datetime, timezone, timedelta

SETTINGS_FILE = "settings.json"
TELEGRAM_API  = "https://api.telegram.org/bot{token}/sendMessage"

DEFAULT_SETTINGS = {
    "telegram_token":   "",
    "telegram_chat_id": "",
    "alerts_enabled":   False,
    "alert_on_scan":    True,
    "alert_min_score":  70,   # Minimum score for Telegram alerts (matches UI slider default)
    "alert_limit":      10,
    "alert_signals":    ["BUY", "STRONG BUY"],
    "scan_hour":        17,
}


# ── LOAD / SAVE SETTINGS ─────────────────────────────────────
def load_settings():
    """Load settings.json and fallback to environment variables."""
    settings = dict(DEFAULT_SETTINGS)
    saved = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                saved = json.load(f)
        except Exception as e:
            print(f"[alert_bot] Error loading settings: {e}")

    # Fallback to Environment Variables if not saved or empty in settings.json
    if saved.get("telegram_token"):
        settings["telegram_token"] = saved["telegram_token"]
    else:
        env_token = os.environ.get("TELEGRAM_TOKEN")
        if env_token:
            settings["telegram_token"] = env_token.strip()

    if saved.get("telegram_chat_id"):
        settings["telegram_chat_id"] = saved["telegram_chat_id"]
    else:
        env_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if env_chat_id:
            settings["telegram_chat_id"] = env_chat_id.strip()

    if "alerts_enabled" in saved:
        settings["alerts_enabled"] = saved["alerts_enabled"]
    else:
        env_enabled = os.environ.get("ALERTS_ENABLED")
        if env_enabled is not None:
            settings["alerts_enabled"] = env_enabled.lower() in ["true", "1", "yes"]

    # Load other config keys from settings.json
    for k, v in saved.items():
        if k not in ["telegram_token", "telegram_chat_id", "alerts_enabled"]:
            settings[k] = v

    return settings


def save_settings(data):
    """Save settings dict to settings.json. Returns True on success."""
    try:
        current = load_settings()
        current.update(data)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(current, f, indent=2)
        return True
    except Exception as e:
        print(f"[alert_bot] Error saving settings: {e}")
        return False


# ── TELEGRAM SEND ─────────────────────────────────────────────
def send_telegram(token, chat_id, text):
    """
    Send a plain text message to a Telegram chat via Bot API.
    Returns True on success, False on failure.
    """
    if not token or not chat_id:
        return False
    try:
        url = TELEGRAM_API.format(token=token)
        payload = {
            "chat_id":    str(chat_id),
            "text":       text,
            "parse_mode": "HTML"
        }
        resp = requests.post(url, json=payload, timeout=8)
        data = resp.json()
        if data.get("ok"):
            return True
        else:
            print(f"[alert_bot] Telegram error: {data.get('description', 'unknown')}")
            return False
    except Exception as e:
        print(f"[alert_bot] Exception sending Telegram: {e}")
        return False


# ── TEST CONNECTION ───────────────────────────────────────────
def test_connection(token, chat_id):
    """
    Send a test ping to verify credentials.
    Returns (success: bool, message: str)
    """
    if not token or not token.strip():
        return False, "Bot Token is required."
    if not chat_id or not str(chat_id).strip():
        return False, "Chat ID is required."

    test_text = (
        "✅ <b>Finrio AI — Connection Test</b>\n\n"
        "🎉 Your Telegram alert is configured correctly!\n"
        f"📅 {datetime.now().strftime('%d %b %Y  %H:%M')}\n\n"
        "You will now receive scan alerts automatically after each scan."
    )
    ok = send_telegram(token.strip(), str(chat_id).strip(), test_text)
    if ok:
        return True, "Test message sent! Check your Telegram."
    return False, "Failed to send. Check your Bot Token and Chat ID."


# ── FORMAT SCAN ALERT ─────────────────────────────────────────
def format_scan_alert(summary):
    """
    Format the scan summary into a clean Telegram message.
    """
    settings   = load_settings()
    min_score  = settings.get("alert_min_score", 70)
    signals    = settings.get("alert_signals", ["BUY", "STRONG BUY"])

    scanned_at = summary.get("scanned_at", "—")
    nifty      = summary.get("nifty", {})
    nifty_price= nifty.get("price", 0)
    nifty_chg  = nifty.get("change", 0)
    mood       = nifty.get("mood", "—")
    advice     = nifty.get("advice", "—")

    stocks     = summary.get("stocks", [])
    ok_stocks  = [s for s in stocks if s.get("status") == "ok"]

    # Filter BUY/STRONG BUY picks above min score
    picks = [
        s for s in ok_stocks
        if s.get("signal") in signals and s.get("score", 0) >= min_score
    ]
    picks.sort(key=lambda x: x.get("score", 0), reverse=True)

    nifty_sign = "+" if nifty_chg >= 0 else ""
    mood_emoji = "🟢" if mood == "BULLISH" else "🟡" if mood in ["NEUTRAL", "CAUTIOUS"] else "🔴"

    lines = [
        "📊 <b>Finrio AI — Scan Complete</b>",
        f"📅 {scanned_at}",
        "",
        f"{mood_emoji} <b>Nifty 50:</b> ₹{nifty_price:,.2f}  ({nifty_sign}{nifty_chg}%)  — {mood}",
        f"💡 <i>{advice}</i>",
        "",
        f"📈 Scanned: {len(ok_stocks)} stocks",
        f"🔥 BUY signals found: {len(picks)}",
        "",
    ]

    if picks:
        limit = settings.get("alert_limit", 10)
        try:
            limit = int(limit)
            if limit <= 0:
                limit = 10
        except (ValueError, TypeError):
            limit = 10

        lines.append("─────────────────────────")
        lines.append(f"🏆 <b>TOP {limit} BUY PICKS</b>" if limit < len(picks) else "🏆 <b>TOP BUY PICKS</b>")
        lines.append("─────────────────────────")
        for i, s in enumerate(picks[:limit], 1):
            sig_emoji  = "⭐" if s.get("signal") == "STRONG BUY" else "✅"
            lines.append(f"{i}. {sig_emoji} <b>{s['sym']}</b> ({s.get('sector','Other')}) — <b>Score: {s.get('score',0)}</b>")
            lines.append(f"   Price: ₹{s.get('price',0):,.2f} | SL: ₹{s.get('slPrice',0):,.2f} | Tgt: ₹{s.get('tgt2',0):,.2f}")
            lines.append("")
    else:
        lines.append("⚠️ No BUY signals meeting the minimum score threshold.")

    lines.append("─────────────────────────")
    lines.append("🤖 <i>Finrio AI — Automated Swing Screener</i>")

    return "\n".join(lines)


# ── FORMAT SINGLE RECOMMENDATION ──────────────────────────────
def format_single_recommendation(s, scanned_at, market_mood):
    """
    Format a clean, actionable recommendation card for a single stock.
    All dynamic — no static boilerplate. Every field reflects the stock's data.
    """
    price     = s.get("price", 0.0)
    sl_price  = s.get("slPrice", 0.0)
    sl_points = max(price - sl_price, 0.01)

    sl_pct = s.get("slPct", 0.0)
    if not sl_pct and price > 0:
        sl_pct = (sl_points / price) * 100

    # R-Multiple targets (pre-calculated by indicators.py, fallback to 1R/1.5R/2.5R)
    R    = s.get("R", sl_points)
    tgt1 = s.get("tgt1", round(price + 1.0 * R, 2))
    tgt2 = s.get("tgt2", round(price + 1.5 * R, 2))
    tgt3 = s.get("tgt3", round(price + 2.5 * R, 2))

    tgt1_pct = round(((tgt1 - price) / price) * 100, 1) if price > 0 else 0
    tgt2_pct = round(((tgt2 - price) / price) * 100, 1) if price > 0 else 0
    tgt3_pct = round(((tgt3 - price) / price) * 100, 1) if price > 0 else 0

    rr = s.get("rr", round((tgt2 - price) / R, 1) if R > 0 else 1.5)

    # Dynamic holding estimate from scorer.py (based on ATR%: 2–5d / 5–8d / 8–14d)
    hold_duration = s.get("holdDuration", "5–14 days")

    # Star rating
    score = s.get("score", 0)
    if score >= 95:
        stars   = "★★★★★"
        verdict = "Strong Buy — Exceptional Setup"
    elif score >= 80:
        stars   = "★★★★☆"
        verdict = "Strong Buy"
    elif score >= 65:
        stars   = "★★★☆☆"
        verdict = "Buy"
    elif score >= 50:
        stars   = "★★☆☆☆"
        verdict = "Watch Setup"
    else:
        stars   = "★☆☆☆☆"
        verdict = "Avoid Setup"

    # Sector rank (if grouped before sending)
    rank_str = ""
    if "sector_rank" in s:
        rank, total = s["sector_rank"]
        rank_str = f" | #{rank}/{total} in Sector"

    # Entry type and buy zone
    is_pullback = s.get("pullbackBuy", False)
    is_breakout = s.get("breakoutResistance", False) or s.get("breakout52w", False)

    if is_pullback:
        pb_level = s.get("pullbackLevel", "EMA")
        pb_low   = s.get("pullbackZoneLow", price * 0.98)
        pb_high  = s.get("pullbackZoneHigh", price * 1.02)
        buy_zone_str = f"₹{pb_low:,.2f} – ₹{pb_high:,.2f}"
        trade_type   = f"Pullback to {pb_level}"
    elif is_breakout:
        low_zone     = price
        high_zone    = price * 1.015
        buy_zone_str = f"₹{low_zone:,.2f} – ₹{high_zone:,.2f}"
        trade_type   = "Breakout"
    else:
        low_zone     = price * 0.99
        high_zone    = price * 1.01
        buy_zone_str = f"₹{low_zone:,.2f} – ₹{high_zone:,.2f}"
        trade_type   = "Trend Following"

    # Setup reasons — only include what's actually true for this stock
    st_dir      = s.get("supertrendDir", "")
    weekly_trend = s.get("weeklyTrend", "")
    macd_bull   = s.get("macdBull", False)
    adx_strong  = s.get("adxStrong", False)
    rsi         = s.get("rsi", 50.0)

    reasons = []
    if st_dir == "BUY":
        reasons.append("✅ Supertrend BUY")
    if weekly_trend == "UPTREND":
        reasons.append("✅ Weekly Trend Positive")
    if macd_bull:
        reasons.append("✅ MACD Bullish")
    if adx_strong:
        reasons.append("✅ ADX Strong (Trend Confirmed)")
    if rsi:
        reasons.append(f"✅ RSI: {rsi:.0f}")
    if s.get("aboveEma21"):
        reasons.append("✅ Above 21 EMA")
    if s.get("aboveEma50"):
        reasons.append("✅ Above 50 EMA")
    if s.get("ema200") and price > s.get("ema200", 0):
        reasons.append("✅ Above 200 EMA")
    if s.get("higherHighsLows"):
        reasons.append("✅ Higher High Formation")
    if s.get("volSpike"):
        reasons.append(f"✅ Volume Spike ({s.get('volRatio', 1.0):.1f}x avg)")

    # If it is a pullback setup, append pull back details under reasons
    if is_pullback and s.get("pullbackFromHigh", 0) > 0:
        pb_from = s.get("pullbackFromHigh", 0.0)
        pb_drop = s.get("pullbackDropPct", 0.0)
        reasons.append(f"↘️ Pulled back from high of ₹{pb_from:,.2f} (-{pb_drop:.1f}%)")

    reasons_str = "\n".join([f"  {r}" for r in reasons]) if reasons else "  Trend Following Setup"

    # Timeframe Alignment Status (1W, 1D, 1H)
    tf_align = []
    # 1W
    weekly_st = s.get("weeklySupertrendDir", "SELL")
    if weekly_trend == "UPTREND" and weekly_st == "BUY":
        w_status = "🟢 Bullish (Uptrend + Supertrend)"
    elif weekly_trend == "UPTREND" or weekly_st == "BUY":
        w_status = "🟡 Neutral"
    else:
        w_status = "🔴 Bearish"
    tf_align.append(f"  • 1W (Weekly) : {w_status}")

    # 1D
    daily_trend = s.get("marketTrend", "UNKNOWN")
    d_status = "🟢 Bullish" if daily_trend == "UPTREND" else "🟡 Neutral" if daily_trend == "SIDEWAYS" else "🔴 Bearish"
    tf_align.append(f"  • 1D (Daily)  : {d_status}")

    # 1H
    h_trend = s.get("hourlyTrend", "UNKNOWN")
    if h_trend != "UNKNOWN":
        h_bull  = s.get("hourlyEmaBull", False)
        h_status = "🟢 Bullish" if h_trend == "UPTREND" and h_bull else "🟡 Neutral" if h_trend == "UPTREND" or h_bull else "🔴 Bearish"
        tf_align.append(f"  • 1H (Hourly) : {h_status}")
    else:
        tf_align.append(f"  • 1H (Hourly) : ── (No trigger yet)")
    tf_align_str = "\n".join(tf_align)

    # Market mood
    mood_upper    = str(market_mood).upper()
    nifty_emoji   = "🟢" if "BULLISH" in mood_upper else "🟡" if "NEUTRAL" in mood_upper or "CAUTIOUS" in mood_upper else "🔴"
    position_size = "Normal / Aggressive" if "BULLISH" in mood_upper else "Normal" if "NEUTRAL" in mood_upper else "Conservative (Half Position)"

    message = (
        f"📊 <b>Finrio — Swing Pick</b>\n"
        f"📅 {scanned_at} (IST)\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⭐ <b>{s.get('signal', 'BUY')} | {s.get('sym')}</b>\n"
        f"Sector: {s.get('sector', 'Other')}{rank_str}\n"
        f"Score: {score}  {stars}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Price      ₹{price:,.2f}\n"
        f"✅ Buy Zone   {buy_zone_str}\n"
        f"🛑 Stop Loss  ₹{sl_price:,.2f}  (-{sl_pct:.1f}%)\n\n"
        f"🎯 T1  ₹{tgt1:,.2f}  (+{tgt1_pct:.1f}%)  →  1:1.0\n"
        f"🎯 T2  ₹{tgt2:,.2f}  (+{tgt2_pct:.1f}%)  →  1:1.5\n"
        f"🎯 T3  ₹{tgt3:,.2f}  (+{tgt3_pct:.1f}%)  →  1:2.5\n\n"
        f"⚖️ Risk:Reward   1 : {rr:.1f}\n"
        f"⏳ Hold Est.     {hold_duration}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Trade Setup — {trade_type}</b>\n"
        f"{reasons_str}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ <b>Timeframe Alignment</b>\n"
        f"{tf_align_str}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 Market: {market_mood} {nifty_emoji}\n"
        f"Position: {position_size}\n\n"
        f"🏆 <b>{verdict}</b>"
    )
    return message



# ── SEND SCAN ALERT ───────────────────────────────────────────
def send_scan_alert(summary):
    """
    Main entry point called by scanner.py after every full scan.
    Reads settings, checks if alerts are enabled, sends messages.
    Returns True if sent successfully.
    """
    settings = load_settings()

    if not settings.get("alerts_enabled", False):
        return False   # Alerts disabled

    token   = settings.get("telegram_token", "").strip()
    chat_id = settings.get("telegram_chat_id", "").strip()

    if not token or not chat_id:
        print("[alert_bot] Telegram not configured. Skipping alert.")
        return False

    # 1. Format and send summary message
    summary_text = format_scan_alert(summary)
    ok_summary = send_telegram(token, chat_id, summary_text)

    # 2. Format and send individual stock recommendation messages
    min_score  = settings.get("alert_min_score", 70)
    signals    = settings.get("alert_signals", ["BUY", "STRONG BUY"])
    
    stocks = summary.get("stocks", [])
    ok_stocks = [s for s in stocks if s.get("status") == "ok"]
    picks = [
        s for s in ok_stocks
        if s.get("signal") in signals and s.get("score", 0) >= min_score
    ]
    picks.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Group by sector and rank
    sector_groups = {}
    for s in ok_stocks:
        sec = s.get("sector", "Other")
        sector_groups.setdefault(sec, []).append(s)
    
    for sec, group in sector_groups.items():
        group.sort(key=lambda x: x.get("score", 0), reverse=True)
        for index, s in enumerate(group):
            s["sector_rank"] = (index + 1, len(group))

    alert_limit = settings.get("alert_limit", 10)
    try:
        alert_limit = int(alert_limit)
    except (ValueError, TypeError):
        alert_limit = 10
        
    # Send detailed messages for each top pick (capped at 10 to avoid hitting limits)
    detail_limit = min(alert_limit, 10)
    
    import time
    
    # Generate ist datetime if missing
    scanned_at = summary.get("scanned_at")
    if not scanned_at:
        utc_now = datetime.now(timezone.utc)
        ist_now = utc_now + timedelta(hours=5, minutes=30)
        scanned_at = ist_now.strftime("%Y-%m-%d %H:%M:%S")
        
    market_mood = summary.get("nifty", {}).get("mood", "NEUTRAL")
    
    for s in picks[:detail_limit]:
        time.sleep(0.5)  # Pause to avoid Telegram rate limits
        stock_text = format_single_recommendation(s, scanned_at, market_mood)
        send_telegram(token, chat_id, stock_text)

    if ok_summary:
        print(f"[alert_bot] Telegram alert summary and detailed cards sent to chat {chat_id}")
    else:
        print(f"[alert_bot] Failed to send Telegram alert summary")
        
    return ok_summary


# ── TEST ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing alert_bot.py...")
    s = load_settings()
    print(f"Settings: {s}")
    token   = s.get("telegram_token", "")
    chat_id = s.get("telegram_chat_id", "")
    if token and chat_id:
        ok, msg = test_connection(token, chat_id)
        print(f"Test: {ok} — {msg}")
    else:
        print("No credentials configured. Enter them in the Settings modal.")
