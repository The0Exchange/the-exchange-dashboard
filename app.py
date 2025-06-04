import os
import sqlite3
from flask import Flask, render_template, jsonify
import requests

app = Flask(__name__)

# ─── CONFIGURATION ─────────────────────────────────────────────────────────────
PORT         = int(os.environ.get("PORT", 5000))
ACCESS_TOKEN = os.getenv("SQUARE_ACCESS_TOKEN", "")
DB_PATH      = os.path.join(os.path.dirname(__file__), "price_history.db")

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

# ─── ENSURE HISTORY TABLE EXISTS ────────────────────────────────────────────────
# This block will create the `history` table if it does not already exist.
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    drink TEXT NOT NULL,
    price REAL NOT NULL
)
""")
conn.commit()
conn.close()

# ─── HELPERS ────────────────────────────────────────────────────────────────────
def get_prices_from_square():
    """
    Fetch live prices from Square’s Catalog API.
    Returns a dict { "Busch Light": 4.15, … } on success.
    On error or missing token, returns {}.
    """
    if not ACCESS_TOKEN:
        return {}

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

    result = {}
    for obj in resp.json().get("objects", []):
        if obj.get("type") != "ITEM":
            continue
        for var in obj["item_data"].get("variations", []):
            vid = var["id"]
            for name, target_vid in DRINKS.items():
                if vid == target_vid:
                    cents = var["item_variation_data"]["price_money"]["amount"]
                    result[name] = round(cents / 100.0, 2)
    return result


# ─── ROUTES ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    """
    1) Attempt to fetch live prices from Square.
       • If Square is offline or returns {}, render “offline.html” (503).
    2) Otherwise, render the skeleton index.html. The client-side JS will
       fetch both /prices and /history/<drink> to populate ticker, grid, and chart.
    """
    live = get_prices_from_square()
    if not live:
        return render_template("offline.html"), 503

    return render_template("index.html")


@app.route("/prices")
def prices_api():
    """
    Returns live prices JSON: { "Busch Light": 4.15, … }.
    """
    return jsonify(get_prices_from_square())


@app.route("/history/<drink>")
def history_api(drink):
    """
    Returns the full price history for a given drink from SQLite, in ascending
    timestamp order. JSON format:
      [
        { "timestamp": "2025-06-04T17:01:00Z", "price": 4.23 },
        { "timestamp": "2025-06-04T17:02:00Z", "price": 4.30 },
        …
      ]
    If the drink name is not recognized, returns 404 with an empty list.
    """
    # Only allow known drink names
    if drink not in DRINKS:
        return jsonify([]), 404

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT timestamp, price FROM history WHERE drink = ? ORDER BY timestamp ASC",
        (drink,)
    )
    rows = c.fetchall()
    conn.close()

    # Convert rows into JSON-serializable list of dicts
    history_data = []
    for ts, price in rows:
        history_data.append({"timestamp": ts, "price": price})

    return jsonify(history_data)


# ─── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
