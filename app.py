from flask import Flask, render_template, jsonify
import requests
import os
import csv
from datetime import datetime
from pytz import timezone

app = Flask(__name__)

ACCESS_TOKEN = "EAAAl2jsnhSRCJrDUumNtCxHXYpTtF82iUx8t-p185KlTHoyaiYjH_GXw-CWGpcy"
DRINKS = {
    "Busch Light": "SPUC5B5SGD7SXTYW3VSNVVAV",
    "Coors Light": "NO3AZ4JDPGQJYR23GZVFSAUA",
    "Michelob Ultra": "KAMYKBVWOHTPHREECKQONYZA",
    "Modelo": "ZTFUVEXIA5AF7TRKA322R3U3",
    "Bud Light": "3DQO6KCAEQPMPTZIHJ3HA3KP",
    "Miller Light": "KAJM3ISSH2TYK7GGAJ2R4XF3",
    "Corona Light": "J3QW2HGXZ2VFFYWXOHHCMFIK",
    "Budweiser": "SB723UTQLPRBLIIE27ZBGHZ7",
    "Guinness": "BUVRMGQPP347WIFSEVKLTYO6",
    "Heineken": "AXVZ5AHHXXJNW2MWHEHQKP2S"
}
DATA_DIR = "Data"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/prices")
def get_prices():
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    response = requests.get("https://connect.squareupsandbox.com/v2/catalog/list", headers=headers)
    prices = {}
    if response.status_code == 200:
        for obj in response.json().get("objects", []):
            if obj["type"] == "ITEM":
                for var in obj["item_data"].get("variations", []):
                    for name, vid in DRINKS.items():
                        if var["id"] == vid:
                            amount = var["item_variation_data"]["price_money"]["amount"]
                            prices[name] = round(amount / 100.0, 2)
    return jsonify(prices)

@app.route("/history/<drink>")
def get_history(drink):
    file_path = os.path.join(DATA_DIR, f"{drink.lower().replace(' ', '_')}_history.csv")
    history = []
    if os.path.exists(file_path):
        with open(file_path, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    timestamp = datetime.fromisoformat(row["timestamp"]).astimezone(timezone("US/Eastern"))
                    price = float(row["price"])
                    history.append({"time": timestamp.strftime("%H:%M"), "price": price})
                except:
                    continue
    return jsonify(history)

if __name__ == "__main__":
    app.run(debug=True)
