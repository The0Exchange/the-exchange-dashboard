import os
import json
from datetime import datetime
from flask import Flask, render_template, jsonify
import requests
import plotly.graph_objs as go

app = Flask(__name__)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT = int(os.environ.get("PORT", 5000))
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data_json")  # your JSON‐history folder
ACCESS_TOKEN = "EAAAl2jsnhSRCJrDUumNtCxHXYpTtF82iUx8t-p185KlTHoyaiYj_H_GXw-CWGpcy"

DRINKS = {
    "Busch Light":    "SPUC5B5SGD7SXTYW3VSNVVAV",
    "Coors Light":    "NO3AZ4JDPGQJYR23GZVFSAUA",
    "Michelob Ultra": "KAMYKBVWOHTPHREECKQONYZA",
    "Modelo":         "ZTFUVEXIA5AF7TRKA322R3U3",
    "Bud Light":      "3DQO6KCAEQPMPTZIHJ3HA3KP",
    "Miller Light":   "KAJM3ISSH2TYK7GGAJ2R4XF3",
    "Corona Light":   "J3QW2HGXZ2VFFYWXOHHCMFIK",
    "Budweiser":      "SB723UTQLPRBLIIE27ZBGHZ7",
    "Guinness":       "BUVRMGQPP347WIFSEVKLTYO6",
    "Heineken":       "AXVZ5AHHXXJNW2MWHEHQKP2S"
}


# ─── HELPERS ──────────────────────────────────────────────────────────────────
def get_prices_from_square():
    """
    Try a one‐shot fetch from Square’s Catalog API.
    Returns a dict { "Busch Light": 4.15, … } on success.
    On any error or non‐200, returns {}.
    """
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    try:
        resp = requests.get(
            "https://connect.squareupsandbox.com/v2/catalog/list",
            headers=headers,
            timeout=5
        )
    except Exception:
        return {}

    if resp.status_code != 200:
        return {}

    payload = resp.json().get("objects", [])
    result = {}
    for obj in payload:
        if obj.get("type") != "ITEM":
            continue
        for var in obj["item_data"].get("variations", []):
            vid = var["id"]
            for drink_name, target_vid in DRINKS.items():
                if vid == target_vid:
                    cents = var["item_variation_data"]["price_money"]["amount"]
                    result[drink_name] = round(cents / 100.0, 2)
    return result


def load_price_history_from_json(drink_name):
    """
    Read data_json/<drink_name>.json, expecting a list of:
      [{ "timestamp": "2025-06-03T14:00:00", "price": 4.10 }, …]
    Return a sorted list of (datetime, float).
    """
    path = os.path.join(DATA_DIR, f"{drink_name}.json")
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        raw = json.load(f)

    parsed = []
    for entry in raw:
        ts = entry.get("timestamp")
        p = entry.get("price", None)
        try:
            price_float = float(p)
            dt = datetime.fromisoformat(ts)
        except Exception:
            continue
        parsed.append((dt, price_float))
    parsed.sort(key=lambda pair: pair[0])
    return parsed


def get_latest_prices_from_json():
    """
    Scan data_json/*.json and return { "Busch Light": 4.12, … } for each file’s last price.
    If a file is missing or empty, its price is None.
    """
    latest = {}
    for fname in os.listdir(DATA_DIR):
        if not fname.lower().endswith(".json"):
            continue
        drink = os.path.splitext(fname)[0]
        history = load_price_history_from_json(drink)
        latest[drink] = history[-1][1] if history else None
    return latest


# ─── ROUTES ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    """
    1) Attempt to fetch live prices from Square.  
       • If the result is empty or there was an error, immediately render “offline.html.”  
    2) Otherwise:
       • Build a historical Plotly line chart for the first drink in data_json/ (using JSON history).  
       • Build ticker items (name/price/direction) from live Square prices.  
       • Build a bottom grid from live Square prices.  
       • Render index.html with those three pieces of data.
    """
    # ── STEP 1: Try Square ──────────────────────────────────────────────────────
    live_prices = get_prices_from_square()
    if not live_prices:
        # If Square is offline / returned {}, show the “Market Offline” page:
        return render_template("offline.html"), 503

    # ── STEP 2: Build historical line chart (JSON‐based) ─────────────────────────
    #   We assume you have a folder data_json/ with files named exactly
    #   "Busch Light.json", "Coors Light.json", etc.  Even though the chart
    #   is “historical,” we only render it when Square is online.
    all_files = [f for f in os.listdir(DATA_DIR) if f.lower().endswith(".json")]
    drinks = sorted([os.path.splitext(f)[0] for f in all_files])
    if not drinks:
        # If data_json/ is empty, we can still show live_grid + live_ticker if desired.
        # For now, just say “No JSON history found”:
        return "No drink-history JSON files found.", 500

    selected = drinks[0]
    hist = load_price_history_from_json(selected)
    times = [dt for dt, price in hist]
    prices = [price for dt, price in hist]

    trace = go.Scatter(
        x=times,
        y=prices,
        mode="lines+markers",
        name=selected,
        line=dict(width=2),
        marker=dict(size=6)
    )
    layout = go.Layout(
        title=dict(text=selected, font=dict(size=24, family="Arial Black")),
        xaxis=dict(visible=False),
        yaxis=dict(autorange=True, title="Price (USD)"),
        margin=dict(l=40, r=20, t=50, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig = go.Figure(data=[trace], layout=layout)
    graphJSON = fig.to_json()

    # ── STEP 3: Build Ticker Items from live_prices ─────────────────────────────
    ticker_items = []
    for drink_name, current_price in live_prices.items():
        # Compare to JSON’s second-to-last price, if it exists, to get an “up/down/flat” arrow:
        history = load_price_history_from_json(drink_name)
        if len(history) >= 2:
            prev = history[-2][1]
            if current_price > prev:
                direction = "up"
            elif current_price < prev:
                direction = "down"
            else:
                direction = "flat"
        else:
            direction = "flat"

        ticker_items.append({
            "name": drink_name,
            "price": f"{current_price:.2f}",
            "direction": direction
        })

    # ── STEP 4: Bottom Price Grid (live_prices) ─────────────────────────────────
    price_grid = {
        drink: live_prices.get(drink) for drink in live_prices
    }

    # ── STEP 5: Render index.html ───────────────────────────────────────────────
    return render_template(
        "index.html",
        plot_json=graphJSON,
        ticker_items=ticker_items,
        price_grid=price_grid
    )


@app.route("/prices")
def prices_api():
    """
    If anyone hits /prices, we still serve the same JSON:
     • First try Square
     • If Square fails, return {} (or you could fallback to JSON, but per request, we only
       want to show Square data—in which case the client sees {} and can display offline).
    """
    live = get_prices_from_square()
    return jsonify(live)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
