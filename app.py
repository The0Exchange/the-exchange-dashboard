import os
import sqlite3
from flask import Flask, render_template, jsonify
import requests

app = Flask(__name__)

# ─── CONFIGURATION ─────────────────────────────────────────────────────────────
PORT         = int(os.environ.get("PORT", 5000))
ACCESS_TOKEN = os.getenv("SQUARE_ACCESS_TOKEN", "")
DB_PATH      = os.path.join(os.path.dirname(__file__), "price_history.db")

# Keys here are the friendly display names; values are Square variation IDs.
DRINKS = {
    "Bud Light":      "3DQO6KCAEQPMPTZIHJ3HA3KP",
    "Budweiser":      "SB723UTQLPRBLIIE27ZBGHZ7",
    "Busch Light":    "SPUC5B5SGD7SXTYW3VSNVVAV",
    "Coors Light":    "NO3AZ4JDPGQJYR23GZVFSAUA",
    "Corona Light":   "J3QW2HGXZ2VFFYWXOHHCMFIK",
    "Guinness":       "BUVRMGQPP347WIFSEVKLTYO6",
    "Heineken":       "AXVZ5AHHXXJNW2MWHEHQKP2S",
    "Michelob Ultra": "KAMYKBVWOHTPHREECKQONYZA",
    "Miller Light":   "KAJM3ISSH2TYK7GGAJ2R4XF3",
    "Modelo":         "ZTFUVEXIA5AF7TRKA322R3U3"
}

# Map display‐names → internal “underscored” keys for SQLite storage
DISPLAY_TO_KEY = {
    "Bud Light":      "bud_light",
    "Budweiser":      "budweiser",
    "Busch Light":    "busch_light",
    "Coors Light":    "coors_light",
    "Corona Light":   "corona_light",
    "Guinness":       "guinness",
    "Heineken":       "heineken",
    "Michelob Ultra": "michelob_ultra",
    "Miller Light":   "miller_light",
    "Modelo":         "modelo"
}

# ─── ENSURE HISTORY TABLE EXISTS ────────────────────────────────────────────────
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
    Returns a dict { "Bud Light": 4.15, … } on success.
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
    live = get_prices_from_square()
    if not live:
        return render_template("offline.html"), 503
    return render_template("index.html")

@app.route("/prices")
def prices_api():
    return jsonify(get_prices_from_square())

@app.route("/history/<drink>")
def history_api(drink):
    """
    Accepts display‐names like "Bud Light" and maps them to the underscore key 
    in the database. If unknown, returns 404 with [].
    """
    if drink not in DISPLAY_TO_KEY:
        return jsonify([]), 404

    key = DISPLAY_TO_KEY[drink]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT timestamp, price FROM history WHERE drink = ? ORDER BY timestamp ASC",
        (key,)
    )
    rows = c.fetchall()
    conn.close()

    history_data = [ {"timestamp": ts, "price": price} for ts, price in rows ]
    return jsonify(history_data)

# ─── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)

