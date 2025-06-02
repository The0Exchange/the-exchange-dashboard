import time
import random
from datetime import datetime
import pytz
import requests
import uuid
import os

# ---------- CONFIGURATION ----------
SQUARE_ACCESS_TOKEN = os.getenv("SQUARE_ACCESS_TOKEN")
if not SQUARE_ACCESS_TOKEN:
    raise EnvironmentError("Missing SQUARE_ACCESS_TOKEN. Make sure it's set in your Render environment.")

SQUARE_API_URL = "https://connect.squareupsandbox.com/v2"
SQUARE_LOCATION_ID = "LTRVY3BZBFJE8"

HEADERS = {
    "Authorization": f"Bearer {SQUARE_ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

DRINKS = {
    "bud_light": "3DQO6KCAEQPMPTZIHJ3HA3KP",
    "budweiser": "SB723UTQLPRBLIIE27ZBGHZ7",
    "busch_light": "SPUC5B5SGD7SXTYW3VSNVVAV",
    "coors_light": "NO3AZ4JDPGQJYR23GZVFSAUA",
    "corona_light": "J3QW2HGXZ2VFFYWXOHHCMFIK",
    "guinness": "BUVRMGQPP347WIFSEVKLTYO6",
    "heineken": "AXVZ5AHHXXJNW2MWHEHQKP2S",
    "michelob_ultra": "KAMYKBVWOHTPHREECKQONYZA",
    "miller_light": "KAJM3ISSH2TYK7GGAJ2R4XF3",
    "modelo": "ZTFUVEXIA5AF7TRKA322R3U3"
}

# ---------- HELPERS ----------
def get_current_price(variation_id):
    response = requests.get(f"{SQUARE_API_URL}/catalog/object/{variation_id}", headers=HEADERS)
    if response.status_code == 200:
        return response.json()["object"]["item_variation_data"]["price_money"]["amount"] / 100.0
    else:
        print(f"Failed to get price for {variation_id}: {response.text}")
        return None

def update_square_price(drink, variation_id, new_price):
    cents = int(round(new_price * 100))
    response = requests.get(f"{SQUARE_API_URL}/catalog/object/{variation_id}", headers=HEADERS)
    if response.status_code != 200:
        print(f"[{drink}] Failed to fetch Square object: {response.text}")
        return

    obj = response.json()["object"]
    obj["item_variation_data"]["price_money"]["amount"] = cents

    update_response = requests.put(f"{SQUARE_API_URL}/catalog/object/{variation_id}", headers=HEADERS, json={"object": obj})
    if update_response.status_code == 200:
        print(f"[{drink}] Price updated to ${new_price:.2f}")
    else:
        print(f"[{drink}] Failed to update price: {update_response.text}")

def simulate_purchase():
    drink, variation_id = random.choice(list(DRINKS.items()))
    quantity = random.randint(1, 3)

    body = {
        "idempotency_key": str(uuid.uuid4()),
        "order": {
            "location_id": SQUARE_LOCATION_ID,
            "line_items": [
                {
                    "catalog_object_id": variation_id,
                    "quantity": str(quantity)
                }
            ]
        }
    }

    response = requests.post(f"{SQUARE_API_URL}/orders", headers=HEADERS, json=body)
    if response.status_code == 200:
        print(f"[{drink}] Simulated {quantity} purchase(s)")
    else:
        print(f"[{drink}] Failed to simulate purchase: {response.text}")

# ---------- MAIN LOOP ----------
print("Starting pricing engine with Square updates and purchase simulation...")

while True:
    now = datetime.now(pytz.timezone("US/Eastern"))
    if 16 <= now.hour <= 23:
        for drink, variation_id in DRINKS.items():
            current_price = get_current_price(variation_id)
            if current_price is None:
                continue

            new_price = current_price * random.uniform(0.98, 1.02)
            new_price = round(min(max(new_price, 3.00), 10.00), 2)
            update_square_price(drink, variation_id, new_price)

        simulate_purchase()

    time.sleep(60)


