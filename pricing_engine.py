import os
import sys
import time
import uuid
import random
import requests
from datetime import datetime, timedelta
import pytz

# === CONFIGURATION ===
SQUARE_API_URL   = "https://connect.squareupsandbox.com/v2"
ACCESS_TOKEN     = os.getenv("SQUARE_ACCESS_TOKEN")
LOCATION_ID      = os.getenv("SQUARE_LOCATION_ID")  # Your sandbox location ID

# === EARLY TOKEN & LOCATION CHECK ===
if ACCESS_TOKEN:
    print(f"[DEBUG] Raw token is: {ACCESS_TOKEN[:8]}…")
else:
    print("[DEBUG] SQUARE_ACCESS_TOKEN is empty!")
    print("⚠️ SQUARE_ACCESS_TOKEN is empty! Exiting.")
    sys.exit(1)

if not LOCATION_ID:
    print("⚠️ SQUARE_LOCATION_ID is empty! (Set this in your Render environment.)")
    sys.exit(1)

# === HEADERS (with pinned API version) ===
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

FLOOR_PRICE    = 2.00
CAP_PRICE      = 10.00
PRICE_DRIFT    = 0.02     # ±2% random drift
TIME_DRIFT     = 0.005    # 0.5% negative drift if no purchase in last 5 min
ROLLING_WINDOW = 20

# Keep track of the last time each drink was actually purchased
last_purchase_time = { drink: None for drink in DRINKS }

price_history = { drink: [] for drink in DRINKS }

# We'll use US/Eastern for determining our 4 PM–12 AM window
EASTERN = pytz.timezone("US/Eastern")


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

    # Step 1: Fetch the full catalog object for upsert
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


def simulate_real_square_purchase():
    """
    1) Decide whether to simulate no purchase (50%) or a positive quantity (30%→1, 10%→2, 10%→3).
    2) If quantity > 0, randomly choose a drink & create a Sandbox order + payment.
    3) Update last_purchase_time for that drink when quantity > 0.
    4) Return { drink_key: quantity } or {} if no purchase this cycle.
    """
    # Decide quantity with weighted probabilities
    quantity = random.choices([0, 1, 2, 3], weights=[0.5, 0.3, 0.1, 0.1])[0]
    if quantity == 0:
        print("[none] No purchase simulated this cycle")
        return {}

    # Otherwise, pick a random drink to credit
    drink_key    = random.choice(list(DRINKS.keys()))
    variation_id = DRINKS[drink_key]
    print(f"[{drink_key}] Simulating {quantity} purchase(s)…")

    # Record the time of this purchase
    now_utc = datetime.now(tz=pytz.utc)
    last_purchase_time[drink_key] = now_utc

    # --- 1) CREATE THE ORDER ---
    order_url = f"{SQUARE_API_URL}/orders"
    order_body = {
        "order": {
            "location_id": LOCATION_ID,
            "line_items": [
                {
                    "catalog_object_id": variation_id,
                    "quantity": str(quantity)
                    # Omitting "base_price_money" so Square uses current catalog price
                }
            ]
        },
        "idempotency_key": str(uuid.uuid4())
    }

    order_resp = requests.post(order_url, headers=HEADERS, json=order_body)
    print(f"  [Order] POST {order_url} → HTTP {order_resp.status_code}")
    print(f"  [Order]   Body: {order_resp.text}")

    if order_resp.status_code not in (200, 201):
        print(f"  [{drink_key}] ❌ Unable to create Square order (HTTP {order_resp.status_code})")
        return {}

    order_data  = order_resp.json().get("order", {})
    order_id    = order_data.get("id")
    total_money = order_data.get("total_money", {}).get("amount", 0)
    if not order_id or total_money is None:
        print(f"  [{drink_key}] ❌ Square did not return a valid order_id or total_money.")
        return {}

    # --- 2) CREATE THE PAYMENT (Quick Sale) ---
    payment_url = f"{SQUARE_API_URL}/payments"
    payment_body = {
        "source_id": "cnon:card-nonce-ok",   # Sandbox test nonce that always works
        "idempotency_key": str(uuid.uuid4()),
        "amount_money": {
            "amount": total_money,  # in cents
            "currency": "USD"
        },
        "order_id": order_id,
        "location_id": LOCATION_ID
    }

    payment_resp = requests.post(payment_url, headers=HEADERS, json=payment_body)
    print(f"  [Payment] POST {payment_url} → HTTP {payment_resp.status_code}")
    print(f"  [Payment]   Body: {payment_resp.text}")

    if payment_resp.status_code not in (200, 201):
        print(f"  [{drink_key}] ❌ Unable to pay Square order (HTTP {payment_resp.status_code})")
        return { drink_key: quantity }

    print(f"[{drink_key}] ✔️ Order {order_id} paid for ${total_money/100:.2f}")
    return { drink_key: quantity }


def apply_pricing_logic(drink, current_price, purchases):
    """
    Apply the random-walk + purchase & time-based drift + mean reversion to compute new_price.
    
    - Random drift: ±PRICE_DRIFT (2%)
    - Purchase drift: 0.5%/1%/1.5% depending on quantity (1→0.5%, 2→1%, 3→1.5%)
    - Time drift: –TIME_DRIFT (0.5%) if no purchase in last 5 minutes
    - Mean reversion: adjust 10% toward the rolling mean (over last ROLLING_WINDOW)
    - Enforce floor CAP_PRICE boundaries
    """
    now_utc = datetime.now(tz=pytz.utc)

    # 1) Random walk drift (±2%)
    drift = 1 + random.uniform(-PRICE_DRIFT, PRICE_DRIFT)

    # 2) Purchase‐based drift
    qty = purchases.get(drink, 0)
    if qty == 1:
        drift += 0.005   # +0.5%
    elif qty == 2:
        drift += 0.01    # +1%
    elif qty >= 3:
        drift += 0.015   # +1.5%

    # 3) Time‐based negative drift if last purchase > 5 minutes ago
    last_time = last_purchase_time.get(drink)
    if last_time:
        if (now_utc - last_time) > timedelta(minutes=5):
            drift -= TIME_DRIFT  # –0.5%
    else:
        # If never purchased yet, consider it as "older than 5 minutes"
        drift -= TIME_DRIFT

    new_price = current_price * drift

    # 4) Mean reversion: 
    history = price_history[drink]
    history.append(current_price)
    if len(history) > ROLLING_WINDOW:
        history.pop(0)
    mean = sum(history) / len(history)

    if new_price > mean:
        new_price -= (new_price - mean) * 0.1
    else:
        new_price += (mean - new_price) * 0.1

    # 5) Enforce floor and cap, then round
    new_price = max(FLOOR_PRICE, min(CAP_PRICE, new_price))
    return round(new_price, 2)


def seconds_until_next_4pm_eastern():
    """
    Calculate how many seconds remain until the next 4:00 PM US/Eastern.
    If the current Eastern time is before 16:00, return delta until today at 16:00.
    Otherwise, return delta until tomorrow at 16:00.
    """
    now_utc = datetime.now(tz=pytz.utc)
    now_eastern = now_utc.astimezone(EASTERN)

    today_4pm = EASTERN.localize(datetime(
        now_eastern.year, now_eastern.month, now_eastern.day, 16, 0, 0
    ))
    if now_eastern < today_4pm:
        next_start = today_4pm
    else:
        tomorrow = now_eastern.date() + timedelta(days=1)
        next_start = EASTERN.localize(datetime(
            tomorrow.year, tomorrow.month, tomorrow.day, 16, 0, 0
        ))

    next_start_utc = next_start.astimezone(pytz.utc)
    delta = (next_start_utc - now_utc).total_seconds()
    return max(delta, 0)


def run_engine():
    print("Starting pricing engine (active 4 PM–12 AM Eastern)…")

    while True:
        # 1) Check current time in US/Eastern
        now_utc = datetime.now(tz=pytz.utc)
        now_eastern = now_utc.astimezone(EASTERN)
        hour = now_eastern.hour

        # 2) If between 16:00 and 23:59 ET, run one cycle
        if 16 <= hour < 24:
            # Simulate a real Square purchase & get {drink: quantity} (or {} if none)
            purchases = simulate_real_square_purchase()

            # For each drink, fetch current price and update accordingly
            for drink, variation_id in DRINKS.items():
                try:
                    current_price = get_square_price(variation_id, drink)
                except Exception as e:
                    print(f"[{drink}] Error retrieving price: {e}")
                    continue

                new_price = apply_pricing_logic(drink, current_price, purchases)
                update_square_price(drink, variation_id, new_price)

            # Sleep 60 seconds before repeating
            time.sleep(60)

        else:
            # Outside active window: sleep until next 4 PM ET
            secs = seconds_until_next_4pm_eastern()
            hrs = int(secs // 3600)
            mins = int((secs % 3600) // 60)
            secs_rem = int(secs % 60)
            print(f"[{now_eastern.strftime('%Y-%m-%d %H:%M:%S')} ET] Outside active hours. "
                  f"Sleeping {hrs}h{mins}m{secs_rem}s until next 4 PM ET.")
            time.sleep(secs)


if __name__ == "__main__":
    run_engine()

