# =============================================================
# stock_manager.py — Manage the custom stock list dynamically
# =============================================================
# Reads and writes stocks_custom.json
# Called by app.py API endpoints to add / remove stocks.
#
# The custom list MERGES with stocks.py at runtime:
#   Final list = STOCKS (stocks.py) + custom_stocks.json
#   (deduplication by sym)
# =============================================================

import json
import os

CUSTOM_FILE = "stocks_custom.json"

VALID_SECTORS = [
    "Auto", "Banking", "Power", "Metal", "Defence",
    "IT", "Pharma", "NBFC", "Infra", "Realty",
    "Consumer", "Chemical", "Finance", "Other"
]


def load_custom() -> list:
    """Load custom stocks from JSON file. Returns [] if not found."""
    if not os.path.exists(CUSTOM_FILE):
        return []
    try:
        with open(CUSTOM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_custom(stocks: list) -> bool:
    """Save the custom stock list to JSON. Returns True on success."""
    try:
        with open(CUSTOM_FILE, "w", encoding="utf-8") as f:
            json.dump(stocks, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[stock_manager] ERROR saving: {e}")
        return False


def get_all_stocks(base_stocks: list) -> list:
    """
    Merge base stocks.py list with custom JSON list.
    Deduplicates by sym — custom entries override base entries.

    Args:
        base_stocks : list of tuples (sym, yahoo, name, sector)

    Returns:
        list of tuples (sym, yahoo, name, sector)
    """
    # Convert base to dict
    merged = {s[0]: s for s in base_stocks}

    # Overlay custom stocks
    for c in load_custom():
        sym = c["sym"].upper()
        merged[sym] = (sym, c["yahoo"], c["name"], c["sector"])

    return list(merged.values())


def add_stock(sym: str, yahoo: str, name: str, sector: str) -> dict:
    """
    Add a stock to the custom list.

    Returns:
        { "status": "ok" | "error", "message": "..." }
    """
    sym   = sym.strip().upper()
    yahoo = yahoo.strip().upper()
    name  = name.strip()
    sector = sector.strip()

    # Validate
    if not sym:
        return {"status": "error", "message": "Symbol is required"}
    if not yahoo:
        return {"status": "error", "message": "Yahoo ticker is required"}
    if not yahoo.endswith(".NS"):
        yahoo = yahoo + ".NS"
    if not name:
        name = sym
    if not sector:
        sector = "Other"

    stocks = load_custom()

    # Check for duplicate
    for s in stocks:
        if s["sym"].upper() == sym:
            return {"status": "error", "message": f"'{sym}' already exists in custom list"}

    stocks.append({"sym": sym, "yahoo": yahoo, "name": name, "sector": sector})
    save_custom(stocks)

    return {"status": "ok", "message": f"'{sym}' added successfully", "stock": {
        "sym": sym, "yahoo": yahoo, "name": name, "sector": sector
    }}


def remove_stock(sym: str) -> dict:
    """
    Remove a stock from the custom list only.
    Base stocks.py stocks cannot be deleted from the frontend.

    Returns:
        { "status": "ok" | "error", "message": "..." }
    """
    sym    = sym.strip().upper()
    stocks = load_custom()

    original_len = len(stocks)
    stocks = [s for s in stocks if s["sym"].upper() != sym]

    if len(stocks) == original_len:
        return {"status": "error", "message": f"'{sym}' not found in custom list (base stocks cannot be removed from frontend)"}

    save_custom(stocks)
    return {"status": "ok", "message": f"'{sym}' removed successfully"}


def list_custom() -> list:
    """Return the full custom stock list."""
    return load_custom()
