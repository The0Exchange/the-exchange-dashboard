import os
import sys
import time
import uuid
import random
import requests
import sqlite3
from datetime import datetime, timedelta
import pytz

# === CONFIGURATION ===
SQUARE_API_URL = "https://connect.squareupsandbox.com/v2"
ACCESS_TOKEN   = os.getenv("SQUARE_ACCESS_TOKEN")
LOCATION_ID    = os.getenv("SQUARE_LOCATION_ID")

# === EARLY TOKEN & LOCATION CHECK ===
if not ACCESS_TOKEN:
    print("[DEBUG] SQUARE_ACCESS_TOKEN is empty! Exiting.")
    sys.exit(1)

if not LOCATION_ID:
    print("⚠️ SQUARE_LOCATION_ID is empty! (Set this in your Render environment.)")
    sys.exit(1)

# === DATABASE SETUP (SQLite) ===
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "price_history.db")

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
RANDOM_RANGE   = 0.10   # ±10% random walk
ROLLING_WINDOW = 20

# Track last‐purchase times (unused for drift; we track no_purchase_streak instead)
last_purchase_time = { drink: None for drink in DRINKS }

# Track consecutive no‐purchase streaks per drink
no_purchase_streak = { drink: 0 for drink in DRINKS }

# In-memory price history for mean reversion (rolling window)
price_history = { drink: [] for drink in DRINKS }

# US/Eastern timezone for active‐hours logic
EASTERN = pytz.timezone("US/Eastern")


def get_square_price(variation_id, drink):
    url = f"{SQUARE_API_URL}/catalog/object/{variation_id}"
    resp = requests.get(url, headers=HEADERS)
    print(f"[{drink}] GET {url} → HTTP {resp.status_code}")
    print(f"[{drink}]   Response: {resp.text}")

    if resp.status_code == 200:
        data = resp.json()
        cents = data["object"]["item_variation_data"]["price_money"]["amount"]
        return cents / 100.0
    else:
        raise RuntimeError(f"[{drink}] Failed to fetch price: HTTP {resp.status_code}")


def update_square_price(drink, variation_id, new_price):
    cents = int(round(new_price * 100))

    # Fetch the full catalog object for upsert
    url_get = f"{SQUARE_API_URL}/catalog/object/{variation_id}"
    resp = requests.get(url_get, headers=HEADERS)
    print(f"[{drink}] GET for upsert ({url_get}) → HTTP {resp.status_code}")
    print(f"[{drink}]   Pre-upsert: {resp.text}")

    if resp.status_code != 200:
        print(f"[{drink}] ❌ Failed to fetch object before upsert (HTTP {resp.status_code})")
        return

    catalog_object = resp.json()["object"]
    catalog_object["item_variation_data"]["price_money"]["amount"] = cents

    body = {
        "idempotency_key": str(uuid.uuid4()),
        "batches": [
            {"objects": [catalog_object]}
        ]
    }
    url_post = f"{SQUARE_API_URL}/catalog/batch-upsert"
    upsert_resp = requests.post(url_post, headers=HEADERS, json=body)
    print(f"[{drink}] POST {url_post} → HTTP {upsert_resp.status_code}")
    print(f"[{drink}]   Upsert: {upsert_resp.text}")

    if upsert_resp.status_code == 200:
        print(f"[{drink}] ✅ Price updated to ${new_price:.2f}")
    else:
        print(f"[{drink}] ❌ Failed to update price: HTTP {upsert_resp.status_code}")


def simulate_real_square_purchase():
    """
    Simulate purchases:
      - 50% → no purchase (qty=0)
      - 30% → qty=1
      - 10% → qty=2
      - 10% → qty=3
    If qty>0, randomly pick one drink to purchase.
    Returns { drink_key: quantity } or {} if none.
    """
    qty = random.choices([0, 1, 2, 3], weights=[0.5, 0.3, 0.1, 0.1])[0]
    if qty == 0:
        print("[none] No purchase this cycle")
        return {}

    drink_key = random.choice(list(DRINKS.keys()))
    variation_id = DRINKS[drink_key]
    print(f"[{drink_key}] Simulating {qty} purchase(s)…")

    # Record purchase time for eventual use (not used for no_purchase_streak)
    now_utc = datetime.now(tz=pytz.utc)
    last_purchase_time[drink_key] = now_utc

    # Create Order
    order_url = f"{SQUARE_API_URL}/orders"
    order_body = {
        "order": {
            "location_id": LOCATION_ID,
            "line_items": [
                {
                    "catalog_object_id": variation_id,
                    "quantity": str(qty)
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

    order_data = order_resp.json().get("order", {})
    order_id   = order_data.get("id")
    total_cents = order_data.get("total_money", {}).get("amount", 0)
    if not order_id or total_cents is None:
        print(f"  [{drink_key}] ❌ Invalid order_id or total_money.")
        return {}

    # Create Payment
    payment_url = f"{SQUARE_API_URL}/payments"
    payment_body = {
        "source_id": "cnon:card-nonce-ok",
        "idempotency_key": str(uuid.uuid4()),
        "amount_money": {
            "amount": total_cents,
            "currency": "USD"
        },
        "order_id": order_id,
        "location_id": LOCATION_ID
    }
    pay_resp = requests.post(payment_url, headers=HEADERS, json=payment_body)
    print(f"  [Payment] POST {payment_url} → HTTP {pay_resp.status_code}")
    print(f"  [Payment]   Body: {pay_resp.text}")

    if pay_resp.status_code not in (200, 201):
        print(f"  [{drink_key}] ❌ Unable to pay order.")
        return {drink_key: qty}

    print(f"[{drink_key}] ✔️ Order {order_id} paid for ${total_cents/100:.2f}")
    return {drink_key: qty}


def alpha_dynamic(price: float) -> float:
    """
    Return a dynamic mean-reversion factor α based on price:
    - α = 0.01 when price = 5.0
    - α ramps to 0.25 at price = 10.0 and also to 0.25 at price = 2.0
    Linear interpolation between these anchor points.
    """
    if price >= 5.0:
        # Linear from (5.0, 0.01) to (10.0, 0.25)
        return 0.01 + (price - 5.0) * (0.25 - 0.01) / (10.0 - 5.0)
    else:
        # price < 5.0 → linear from (2.0, 0.25) to (5.0, 0.01)
        return 0.25 - (5.0 - price) * (0.25 - 0.01) / (5.0 - 2.0)


def apply_pricing_logic(drink: str, current_price: float, purchases: dict):
    """
    Compute the new_price using:
      - ±10% random walk
      - Scaled purchase/no-purchase drift:
          • If qty>0, purchase_drift = 0.01 * qty
          • If no purchase, no_purchase_streak += 1, then no_purchase_drift = -min(0.01*streak, 0.03)
      - Dynamic mean reversion α(t) based on new_price
      - Floor at $2.00 (no cap)
    """
    # 1) Random walk component (±10%)
    rand_comp = random.uniform(-RANDOM_RANGE, RANDOM_RANGE)

    # 2) Purchase/no-purchase drift
    if drink in purchases:
        qty = purchases[drink]
        purchase_comp = 0.01 * qty
        no_purchase_streak[drink] = 0
    else:
        no_purchase_streak[drink] += 1
        purchase_comp = max(-0.01 * no_purchase_streak[drink], -0.03)

    # 3) Preliminary new price
    new_price = current_price * (1 + rand_comp + purchase_comp)

    # 4) Rolling mean of last ROLLING_WINDOW points
    history = price_history[drink]
    history.append(current_price)
    if len(history) > ROLLING_WINDOW:
        history.pop(0)
    mean_price = sum(history) / len(history)

    # 5) Dynamic mean reversion
    alpha = alpha_dynamic(new_price)
    new_price += (mean_price - new_price) * alpha

    # 6) Enforce floor only (no upper cap)
    new_price = max(FLOOR_PRICE, new_price)
    return round(new_price, 2)


def seconds_until_next_4pm_eastern():
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
    return max((next_start_utc - now_utc).total_seconds(), 0)


def run_engine():
    print("Starting pricing engine (active 4 PM–12 AM Eastern)…")

    while True:
        now_utc = datetime.now(tz=pytz.utc)
        now_eastern = now_utc.astimezone(EASTERN)
        hour = now_eastern.hour

        if 16 <= hour < 24:
            # 1) Simulate purchases
            purchases = simulate_real_square_purchase()

            # 2) For each drink, fetch current price and compute new_price
            for drink, variation_id in DRINKS.items():
                try:
                    current_price = get_square_price(variation_id, drink)
                except Exception as e:
                    print(f"[{drink}] Error retrieving price: {e}")
                    continue

                new_price = apply_pricing_logic(drink, current_price, purchases)
                update_square_price(drink, variation_id, new_price)

                # 3) Insert into SQLite history
                conn = sqlite3.connect(DB_PATH)
                c    = conn.cursor()
                now_ts = datetime.now(tz=pytz.utc).isoformat()
                c.execute(
                    "INSERT INTO history (timestamp, drink, price) VALUES (?, ?, ?)",
                    (now_ts, drink, new_price)
                )
                conn.commit()
                conn.close()

            time.sleep(60)

        else:
            secs = seconds_until_next_4pm_eastern()
            hrs  = int(secs // 3600)
            mins = int((secs % 3600) // 60)
            secs_rem = int(secs % 60)
            print(f"[{now_eastern.strftime('%Y-%m-%d %H:%M:%S')} ET] "
                  f"Outside active hours. Sleeping {hrs}h{mins}m{secs_rem}s.")
            time.sleep(secs)


if __name__ == "__main__":
    run_engine()

