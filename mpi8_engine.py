#!/usr/bin/env python3
"""
MPI 8 Index Engine - Cloud Deployment Edition
Description: Autonomous single-fire data generation block for MPI 8.
             Features: Safe-write backups, dynamic market trend analysis, 
             standardized 1,000-point baselining, and Historical Backfilling.
"""

import os
import json
import random
import shutil
from datetime import datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
YSX_URL = "https://ysx-mm.com/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
# FIXED: Expanded to capture a full 4-hour market session (240 mins) safely
MAX_INTRADAY_POINTS = 300 

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "api.json")
BACKUP_FILE = os.path.join(SCRIPT_DIR, "api_backup.json")

CONSTITUENT_SHARES = {
    "FMI": 27112747, "MTSH": 38929150, "MCB": 10400986, "FPB": 2472053,
    "TMH": 12213224, "EFR": 48740248, "AMATA": 10000000, "MAEX": 24561164
}

INDEX_BASE_DIVISOR = 645241392.0 

BASELINE_PRICES = {
    "FMI": 19000.0, "MTSH": 9800.0, "MCB": 7800.0, "FPB": 1600.0,
    "TMH": 2400.0, "EFR": 1950.0, "AMATA": 4800.0, "MAEX": 1800.0
}

def check_market_hours():
    mmt_now = datetime.now(timezone.utc) + timedelta(hours=6, minutes=30)
    if mmt_now.weekday() >= 5:
        return False, "Market Closed (Weekend)"
    
    market_start = mmt_now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_end = mmt_now.replace(hour=13, minute=30, second=0, microsecond=0)
    
    if market_start <= mmt_now <= market_end:
        return True, "Market Open (Live Trading)"
    return False, "Market Closed (Outside Hours)"

def scrape_ysx():
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(YSX_URL, headers=headers, timeout=12)
        if response.status_code != 200: return None
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", {"class": "table-stock"}) or soup.find("table")
        if not table: return None
        
        prices = {}
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if len(cols) >= 3:
                ticker = cols[0].text.strip().upper()
                if ticker in CONSTITUENT_SHARES:
                    try:
                        prices[ticker] = float(cols[2].text.replace(",", "").strip())
                    except ValueError: continue
        return prices if prices else None
    except Exception:
        return None

def load_existing_state():
    if os.path.exists(OUTPUT_FILE):
        try:
            shutil.copy(OUTPUT_FILE, BACKUP_FILE)
            with open(OUTPUT_FILE, "r") as f:
                state = json.load(f)
                return state.get("intraday_history", []), state.get("daily_candle_history", []), {c["ticker"]: c["price"] for c in state.get("constituents", [])}
        except Exception: pass
    return [], [], {}

def generate_historical_backfill(base_points):
    history = []
    mmt_now = datetime.now(timezone.utc) + timedelta(hours=6, minutes=30)
    current_sim_points = base_points * 0.85 

    for i in range(365, 0, -1):
        date_str = (mmt_now - timedelta(days=i)).strftime("%Y-%m-%d")
        date_obj = mmt_now - timedelta(days=i)
        if date_obj.weekday() >= 5: continue 
        
        change = current_sim_points * random.uniform(-0.015, 0.016)
        open_p = current_sim_points
        close_p = open_p + change
        high_p = max(open_p, close_p) + abs(change * random.uniform(0.1, 0.5))
        low_p = min(open_p, close_p) - abs(change * random.uniform(0.1, 0.5))
        
        history.append({
            "date": date_str,
            "open": round(open_p, 2), "high": round(high_p, 2),
            "low": round(low_p, 2), "close": round(close_p, 2)
        })
        current_sim_points = close_p
    return history

def compile_api():
    is_open, status_message = check_market_hours()

    if not is_open:
        print(f"Engine Sleep Mode Active: {status_message}. api.json remains frozen.")
        return 

    intraday_hist, daily_hist, last_known_prices = load_existing_state()
    scraped_prices = scrape_ysx()
    final_prices = {}
    is_simulated = False

    for ticker in CONSTITUENT_SHARES.keys():
        if scraped_prices and ticker in scraped_prices:
            final_prices[ticker] = scraped_prices[ticker]
        elif ticker in last_known_prices:
            final_prices[ticker] = last_known_prices[ticker]
        else:
            final_prices[ticker] = BASELINE_PRICES[ticker]

    if not scraped_prices:
        is_simulated = True
        for t, p in final_prices.items():
            raw_price = p * (1 + random.uniform(-0.01, 0.01))
            final_prices[t] = float(round(raw_price / 100) * 100)
        data_source = "Cloud Simulation Engine" if last_known_prices else "Baseline Initialization"
    else:
        data_source = "Scraped Live (YSX)"

    total_market_cap = sum(price * CONSTITUENT_SHARES[ticker] for ticker, price in final_prices.items())
    index_points = round(total_market_cap / INDEX_BASE_DIVISOR, 2)
    
    constituents_payload = []
    for ticker, price in final_prices.items():
        weight = round(((price * CONSTITUENT_SHARES[ticker]) / total_market_cap) * 100, 2)
        old_price = last_known_prices.get(ticker, price)
        price_change = price - old_price
        
        constituents_payload.append({
            "ticker": ticker, "price": price, "weight_percent": weight,
            "change": round(price_change, 2)
        })

    mmt_now = datetime.now(timezone.utc) + timedelta(hours=6, minutes=30)
    current_date_str = mmt_now.strftime("%Y-%m-%d")
    current_time_str = mmt_now.strftime("%Y-%m-%d %H:%M")

    # FIXED: Clear out yesterday's intraday data when a new session opens
    if intraday_hist:
        last_tick_date = intraday_hist[-1]["time"].split(" ")[0]
        if last_tick_date != current_date_str:
            intraday_hist = []

    # Intraday Candle Management
    intra_open = intraday_hist[-1]["close"] if intraday_hist else index_points
    new_intra = {
        "time": current_time_str, "open": round(intra_open, 2),
        "high": round(max(intra_open, index_points) + (0.02 if is_simulated else 0), 2),
        "low": round(min(intra_open, index_points) - (0.02 if is_simulated else 0), 2), 
        "close": round(index_points, 2)
    }
    
    if intraday_hist and intraday_hist[-1]["time"] == current_time_str:
        intraday_hist[-1] = new_intra
    else:
        intraday_hist.append(new_intra)
    if len(intraday_hist) > MAX_INTRADAY_POINTS: intraday_hist = intraday_hist[-MAX_INTRADAY_POINTS:]

    if not daily_hist:
        daily_hist = generate_historical_backfill(index_points)

    # Daily Master Candle Management
    if daily_hist and daily_hist[-1]["date"] == current_date_str:
        daily_hist[-1]["high"] = round(max(daily_hist[-1]["high"], index_points), 2)
        daily_hist[-1]["low"] = round(min(daily_hist[-1]["low"], index_points), 2)
        daily_hist[-1]["close"] = round(index_points, 2)
    else:
        daily_open = daily_hist[-1]["close"] if daily_hist else index_points
        daily_hist.append({"date": current_date_str, "open": daily_open, "high": max(daily_open, index_points), "low": min(daily_open, index_points), "close": index_points})

    # Advanced Analytics
    net_change = round(intraday_hist[-1]["close"] - intraday_hist[0]["open"], 2)
    
    if intraday_hist[0]['open'] != 0:
        percent_change = round((net_change / intraday_hist[0]['open']) * 100, 2)
    else:
        percent_change = 0.0
        
    if net_change > 0:
        market_sentiment = "Bullish 📈"
    elif net_change < 0:
        market_sentiment = "Bearish 📉"
    else:
        market_sentiment = "Neutral ⚖️"

    api_payload = {
        "system_metadata": {
            "index_ticker": "MPI 8", 
            "index_name": "Myanmar's Public Index 8",
            "data_source": data_source, 
            "market_status": status_message,
            "market_sentiment": market_sentiment,
            "last_updated_mmt": mmt_now.strftime("%Y-%m-%d %H:%M:%S MMT")
        },
        "index_metrics": {
            "current_points": index_points,
            "net_change": net_change,
            "percentage_change": f"{'+' if percent_change > 0 else ''}{percent_change}%",
            "daily_high": daily_hist[-1]["high"],
            "daily_low": daily_hist[-1]["low"]
        },
        "intraday_history": intraday_hist,
        "daily_candle_history": daily_hist,
        "constituents": constituents_payload
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(api_payload, f, indent=2)

if __name__ == "__main__":
    compile_api()
