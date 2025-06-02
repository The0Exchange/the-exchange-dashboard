import os
import sys
import time
import uuid
import random
import requests

# === CONFIGURATION ===
SQUARE_API_URL = "https://connect.squareupsandbox.com/v2"
ACCESS_TOKEN = os.getenv("SQUARE_ACCESS_TOKEN")

# === EARLY TOKEN CHECK ===
# Print the first few characters of the token, or exit if it's missing.
print(f"[DEBUG] Raw token is: {ACCESS_TOKEN[:8]}…" if ACCESS_TOKEN else "[DEBUG] SQUARE_ACCESS_TOKEN is empty!")
if not ACCESS_TOKEN:
    print("⚠️ SQUARE_ACCESS_TOKEN is empty! Exiting.")
    sys.exit(1)

# Add the Square-Version header so our requests use the 2025-05-21 API schema
HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Square-Version": "2025-05-21",
    "Content-Type": "application/json"
}

DRINKS = {
    "bud_light":        "3DQO6KCAEQPMPTZIHJ3HA3KP",
    "budweiser":        "SB723UTQLPRBLIIE27ZBGHZ7",
    "busch_light":      "SPUC5B5SGD7SXTYW3VSNVVAV",
    "coors_light":      "NO3AZ4JDPGQJYR23GZVFSAUA",
    "corona_light":     "J3QW2HGXZ2VFFYWXOHHCMFIK",
    "guinness":         "BUVRMGQPP347WIFSEVKLTYO6",
    "heineken":         "AXVZ5AHHXXJNW2MWHEHQKP2S",
    "michelob_ultra":   "KAMYKBVWOHTPHREECKQONYZA",
    "miller_light":     "KAJM3ISSH2TYK7GGAJ2R4XF3",
    "modelo":           "ZTFUVEXIA5AF7TRKA322R3U3"
}

FLOOR_PRICE = 2.00
CAP_PRICE = 10.00
PRICE_DRIFT = 0.02
PURCHASE_DRIFT = 0.01
ROLLING_WINDOW = 20

price_history = {drink: [] for drink in DRINKS}


def get_square_price(variation_id, drink):
    """
    Fetch the current price (in dollars) for a given item variation.
    Prints HTTP status and response body for debugging.
    """
    url = f"{SQUARE_API_URL}/catalog/object/{variation_id}"
    response = requests.get(url, headers=HEADERS)
    print(f"[{drink}] GET {url} → HTTP {response.status_code}")
    print(f"[{drink}]   Response body: {response.text}")

    if response.status_code == 200:
        data = response.json()
        cents = data["object"]["item_variation_data"]["price_money"]["amount"]
        return cents / 100.0
    else:
        raise RuntimeError(f"[{drink}] Failed to fetch price: HTTP {response.status_code}")


def update_square_price(drink, variation_id, new_price):
    """
    Update the price of a given item variation to `new_price` (in dollars).
    Prints both the GET (pre-upsert) and the POST (batch-upsert) debugging info.
    """
    cents = int(round(new_price * 100))

    # Step 1: Fetch the full catalog object
    url_get = f"{SQUARE_API_URL}/catalog/object/{variation_id}"
    response = requests.get(url_get, headers=HEADERS)
    print(f"[{drink}] GET for upsert ({url_get}) → HTTP {response.status_code}")
    print(f"[{drink}]   Response body (pre-upsert): {response.text}")

    if response.status_code != 200:
        print(f"[{drink}] ❌ Failed to fetch Square object before upsert (HTTP {response.status_code})")
        return

    catalog_object = response.json()["object"]
    catalog_object["item_variation_data"]["price_money"]["amount"] = cents

    # Step 2: Batch upsert with the modified price
    body = {
        "idempotency_key": str(uuid.uuid4()),
        "batches": [
            {
                "objects": [catalog_object]
            }
        ]
    }

    url_post = f"{SQUARE_API_URL}/catalog/batch-upsert"
    update_response = requests.post(url_post, headers=HEADERS, json=body)
    print(f"[{drink}] POST {url_post} → HTTP {update_response.status_code}")
    print(f"[{drink}]   Response body (upsert): {update_response.text}")

    if update_response.status_code == 200:
        print(f"[{drink}] ✅ Price updated to ${new_price:.2f}")
    else:
        print(f"[{drink}] ❌ Failed to update price: HTTP {update_response.status_code}")


def simulate_purchases():
    """
    Simulate a random purchase for one drink. 
    Returns a dict mapping {drink_name: quantity_sold}.
    """
    drink = random.choice(list(DRINKS.keys()))
    quantity = random.choices([1, 2, 3], weights=[0.7, 0.2, 0.1])[0]
    print(f"[{drink}] Simulated {quantity} purchase(s)")
    return {drink: quantity}


def apply_pricing_logic(drink, current_price, purchases):
    """
    Apply the random-walk + mean reversion + purchase drift logic to compute new_price.
    """
    # ±2% random drift
    drift = 1 + random.uniform(-PRICE_DRIFT, PRICE_DRIFT)
    # +1% additional drift if a purchase happened for this drink
    if purchases.get(drink):
        drift += PURCHASE_DRIFT

    new_price = current_price * drift

    # Mean reversion: rolling mean over last ROLLING_WINDOW prices
    history = price_history[drink]
    history.append(current_price)
    if len(history) > ROLLING_WINDOW:
        history.pop(0)
    mean = sum(history) / len(history)

    if new_price > mean:
        new_price -= (new_price - mean) * 0.1
    else:
        new_price += (mean - new_price) * 0.1

    # Enforce floor and cap, then round to the nearest cent
    new_price = max(FLOOR_PRICE, min(CAP_PRICE, new_price))
    return round(new_price, 2)


def run_engine():
    print("Starting pricing engine with Square updates and purchase simulation...")

    while True:
        try:
            purchases = simulate_purchases()

            for drink, variation_id in DRINKS.items():
                try:
                    current_price = get_square_price(variation_id, drink)
                except Exception as e:
                    print(f"[{drink}] Error retrieving price: {e}")
                    continue

                new_price = apply_pricing_logic(drink, current_price, purchases)
                update_square_price(drink, variation_id, new_price)

            # Wait 60 seconds before the next cycle
            time.sleep(60)

        except Exception as e:
            print(f"Engine error: {e}")
            time.sleep(10)


if __name__ == "__main__":
    run_engine()


