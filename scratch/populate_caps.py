import json
import os
import concurrent.futures
import yfinance as yf

DATA_FILE = "screener_data.json"

def fetch_cap(stock):
    sym = stock.get("sym")
    yahoo_sym = stock.get("yahoo") or (sym + ".NS")
    try:
        ticker = yf.Ticker(yahoo_sym)
        raw_cap = getattr(ticker.fast_info, "market_cap", None) or 0
        mkt_cap_cr = round(raw_cap / 1e7, 0)
        
        if mkt_cap_cr >= 50000:
            cap_cat = "Large Cap"
        elif mkt_cap_cr >= 5000:
            cap_cat = "Mid Cap"
        elif mkt_cap_cr > 0:
            cap_cat = "Small Cap"
        else:
            mkt_cap_cr = 0
            cap_cat = "Unknown"
            
        print(f"[+] {sym}: {cap_cat} ({mkt_cap_cr} Cr)")
        return sym, mkt_cap_cr, cap_cat
    except Exception as e:
        print(f"[-] {sym}: Error {e}")
        return sym, 0, "Unknown"

def main():
    if not os.path.exists(DATA_FILE):
        print("Data file not found!")
        return

    with open(DATA_FILE, "r") as f:
        data = json.load(f)

    stocks = data.get("stocks", [])
    print(f"Loaded {len(stocks)} stocks. Fetching market caps in parallel...")

    # Fetch in parallel with 30 worker threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        results = list(executor.map(fetch_cap, stocks))

    # Create mapping
    cap_map = {sym: (cap, cat) for sym, cap, cat in results}

    # Update stocks
    updated_count = 0
    for s in stocks:
        sym = s.get("sym")
        if sym in cap_map:
            cap, cat = cap_map[sym]
            s["marketCap"] = cap
            s["capCategory"] = cat
            updated_count += 1

    # Update headers
    large_count = sum(1 for s in stocks if s.get("capCategory") == "Large Cap")
    mid_count = sum(1 for s in stocks if s.get("capCategory") == "Mid Cap")
    small_count = sum(1 for s in stocks if s.get("capCategory") == "Small Cap")
    unknown_count = sum(1 for s in stocks if s.get("capCategory") == "Unknown")

    data["uptrend_count"] = sum(1 for s in stocks if s.get("marketTrend") == "UPTREND")
    data["downtrend_count"] = sum(1 for s in stocks if s.get("marketTrend") == "DOWNTREND")
    data["sideways_count"] = sum(1 for s in stocks if s.get("marketTrend") == "SIDEWAYS")

    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Updated {updated_count} stocks.")
    print(f"Stats: Large: {large_count}, Mid: {mid_count}, Small: {small_count}, Unknown: {unknown_count}")

if __name__ == "__main__":
    main()
