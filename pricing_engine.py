import os
import time
import uuid
import random
import requests

# === CONFIGURATION ===
SQUARE_API_URL = "https://connect.squareupsandbox.com/v2"
ACCESS_TOKEN = os.getenv("SQUARE_ACCESS_TOKEN")

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

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

FLOOR_PRICE = 2.00
CAP_PRICE = 10.00
PRICE_DRIFT = 0.02
PURCHASE_DRIFT = 0.01
ROLLING_WINDOW = 20

price_history = {drink: [] for drink in DRINKS}


def get_square_price(variation_id):
    url = f"{SQUARE_API_URL}/catalog/object/{variation_id}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        cents = data["object"]["item_variation_data"]["price_money"]["amount"]
        return cents / 100.0
    else:
        raise RuntimeError(f"Failed to fetch price: {response.text}")


def update_square_price(drink, variation_id, new_price):
    cents = int(round(new_price * 100))
    
    # Step 1: Fetch full object
    response = requests.get(f"{SQUARE_API_URL}/catalog/object/{variation_id}", headers=HEADERS)
    if response.status_code != 200:
        print(f"[{drink}] Failed to fetch Square object: {response.text}")
        return

    catalog_object = response.json()["object"]
    catalog_object["item_variation_data"]["price_money"]["amount"] = cents

    # Step 2: Batch upsert
    body = {
        "idempotency_key": str(uuid.uuid4()),
        "batches": [
            {
                "objects": [catalog_object]
            }
        ]
    }

    update_response = requests.post(f"{SQUARE_API_URL}/catalog/batch-upsert", headers=HEADERS, json=body)
    if update_response.status_code == 200:
        print(f"[{drink}] ✅ Price updated to ${new_price:.2f}")
    else:
        print(f"[{drink}] ❌ Failed to update price: {update_response.text}")


def simulate_purchases():
    drink = random.choice(list(DRINKS.keys()))
    quantity = random.choices([1, 2, 3], weights=[0.7, 0.2, 0.1])[0]
    print(f"[{drink}] Simulated {quantity} purchase(s)")
    return {drink: quantity}


def apply_pricing_logic(drink, current_price, purchases):
    drift = 1 + random.uniform(-PRICE_DRIFT, PRICE_DRIFT)
    if purchases.get(drink):
        drift += PURCHASE_DRIFT

    new_price = current_price * drift

    history = price_history[drink]
    history.append(current_price)
    if len(history) > ROLLING_WINDOW:
        history.pop(0)
    mean = sum(history) / len(history)

    if new_price > mean:
        new_price -= (new_price - mean) * 0.1
    else:
        new_price += (mean - new_price) * 0.1

    new_price = max(FLOOR_PRICE, min(CAP_PRICE, new_price))
    return round(new_price, 2)


def run_engine():
    print("Starting pricing engine with Square updates and purchase simulation...")

    while True:
        try:
            purchases = simulate_purchases()

            for drink, variation_id in DRINKS.items():
                try:
                    current_price = get_square_price(variation_id)
                except Exception as e:
                    print(f"[{drink}] Error retrieving price: {e}")
                    continue

                new_price = apply_pricing_logic(drink, current_price, purchases)
                update_square_price(drink, variation_id, new_price)

            time.sleep(60)

        except Exception as e:
            print(f"Engine error: {e}")
            time.sleep(10)


if __name__ == "__main__":
    run_engine()


