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
from datetime import datetime

SETTINGS_FILE = "settings.json"
TELEGRAM_API  = "https://api.telegram.org/bot{token}/sendMessage"

DEFAULT_SETTINGS = {
    "telegram_token":   "",
    "telegram_chat_id": "",
    "alerts_enabled":   False,
    "alert_on_scan":    True,
    "alert_min_score":  70,
    "alert_signals":    ["BUY", "STRONG BUY"],
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

    # Fallback to Environment Variables only if not saved in settings.json
    if "telegram_token" in saved:
        settings["telegram_token"] = saved["telegram_token"]
    else:
        env_token = os.environ.get("TELEGRAM_TOKEN")
        if env_token:
            settings["telegram_token"] = env_token.strip()

    if "telegram_chat_id" in saved:
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
        lines.append("─────────────────────────")
        lines.append("🏆 <b>TOP BUY PICKS</b>")
        lines.append("─────────────────────────")
        for i, s in enumerate(picks[:10], 1):
            sig_emoji  = "⭐" if s.get("signal") == "STRONG BUY" else "✅"
            st_emoji   = "🟢" if s.get("supertrendDir") == "BUY" else "🔴"
            macd_emoji = "📈" if s.get("macdBull")  else ""
            adx_emoji  = "💪" if s.get("adxStrong") else ""
            week_emoji = "🌟" if s.get("weeklyTrend") == "UPTREND" else ""
            gap_emoji  = "🚀" if s.get("gapUp") else ""

            lines.append(
                f"{i}. {sig_emoji} <b>{s['sym']}</b>  ({s.get('sector','—')})  "
                f"Score: {s.get('score',0)}"
            )
            lines.append(
                f"   ₹{s.get('price',0):,.2f}  |  RSI: {s.get('rsi',0):.1f}  |  "
                f"ATR: {s.get('atrPct',0):.1f}%"
            )
            lines.append(
                f"   SL: ₹{s.get('slPrice',0):,.2f}  "
                f"Tgt2: ₹{s.get('tgt2',0):,.2f}  "
                f"Tgt3: ₹{s.get('tgt3',0):,.2f}"
            )
            tags = " ".join(filter(None, [
                "ST" + st_emoji,
                "MACD" + macd_emoji if macd_emoji else "",
                "ADX" + adx_emoji  if adx_emoji  else "",
                "WEEKLY" + week_emoji if week_emoji else "",
                "GAP🚀" if gap_emoji else "",
            ]))
            if tags.strip():
                lines.append(f"   {tags}")
            lines.append("")
    else:
        lines.append("⚠️ No BUY signals meeting the minimum score threshold.")

    lines.append("─────────────────────────")
    lines.append("🤖 <i>Finrio AI — Automated Swing Screener</i>")

    return "\n".join(lines)


# ── SEND SCAN ALERT ───────────────────────────────────────────
def send_scan_alert(summary):
    """
    Main entry point called by scanner.py after every full scan.
    Reads settings, checks if alerts are enabled, sends message.
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

    text = format_scan_alert(summary)
    ok   = send_telegram(token, chat_id, text)

    if ok:
        print(f"[alert_bot] Telegram alert sent to chat {chat_id}")
    else:
        print(f"[alert_bot] Failed to send Telegram alert")
    return ok


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
