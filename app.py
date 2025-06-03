import os
from flask import Flask, render_template, jsonify
import requests

app = Flask(__name__)

PORT = int(os.environ.get("PORT", 5000))
ACCESS_TOKEN = os.getenv("SQUARE_ACCESS_TOKEN", "")

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

def get_prices_from_square():
    if not ACCESS_TOKEN:
        return {}
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    try:
        resp = requests.get(
            "https://connect.squareupsandbox.com/v2/catalog/list",
            headers=headers, timeout=5
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

@app.route("/")
def index():
    live = get_prices_from_square()
    if not live:
        return render_template("offline.html"), 503
    return render_template("index.html")

@app.route("/prices")
def prices_api():
    return jsonify(get_prices_from_square())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)

