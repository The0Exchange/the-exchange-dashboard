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

# === PRICING PARAMETERS ===
FLOOR_PRICE    = 2.00
RANDOM_RANGE   = 0.10    # ±10% random walk component

# Mean–reversion to $5 parameters
TARGET_PRICE   = 5.00
PRICE_LOW      = 2.00
PRICE_HIGH     = 10.00
ALPHA_AT_LOW   = 0.25    # α when price <= 2.00
ALPHA_AT_MID   = 0.01    # α when price = 5.00
ALPHA_AT_HIGH  = 0.25    # α when price >= 10.00

# Track consecutive no‐purchase streaks (for potential logging; drift is flat −0.01)
no_purchase_streak = { drink: 0 for drink in DRINKS }

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

    # Record purchase time (for logging; not used in drift)
    now_utc = datetime.now(tz=pytz.utc)
    last_purchase_time = now_utc  # (unused aside from potential logs)

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

    # Record purchase locally so the dashboard can display history
    try:
        conn = sqlite3.connect(DB_PATH)
        c    = conn.cursor()
        now_ts = datetime.now(tz=pytz.utc).isoformat()
        c.execute(
            "INSERT INTO purchases (timestamp, drink, quantity, price) VALUES (?, ?, ?, ?)",
            (now_ts, drink_key, qty, total_cents / 100.0)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  [{drink_key}] ⚠️ Failed to record purchase locally: {e}")

    return {drink_key: qty}


def alpha_to_center(price: float) -> float:
    """
    Compute α for pulling price toward TARGET_PRICE (5.00):
      • α = 0.25 at price <= 2.00
      • α = 0.01 at price = 5.00
      • α = 0.25 at price >= 10.00
    Linearly interpolate for intermediate values.
    """
    if price <= PRICE_LOW:
        return ALPHA_AT_LOW
    elif price >= PRICE_HIGH:
        return ALPHA_AT_HIGH
    elif price < TARGET_PRICE:
        # Map [2.0 → 5.0] → [0.25 → 0.01]
        return ALPHA_AT_LOW - (price - PRICE_LOW) * (ALPHA_AT_LOW - ALPHA_AT_MID) / (TARGET_PRICE - PRICE_LOW)
    else:
        # Map [5.0 → 10.0] → [0.01 → 0.25]
        return ALPHA_AT_MID + (price - TARGET_PRICE) * (ALPHA_AT_HIGH - ALPHA_AT_MID) / (PRICE_HIGH - TARGET_PRICE)


def apply_pricing_logic(drink: str, current_price: float, purchases: dict):
    """
    1) Random walk: ±10%
    2) Purchase drift (+0.01 * qty) or no‐purchase drift (−0.01)
    3) Pull directly toward $5.00 with α defined by alpha_to_center()
    4) Enforce floor at $2.00
    """
    # 1) Random walk component (a uniform fraction in [−0.10, +0.10])
    rand_comp = random.uniform(-RANDOM_RANGE, RANDOM_RANGE)

    # 2) Purchase vs. no‐purchase drift
    if drink in purchases:
        qty = purchases[drink]
        purchase_comp = 0.01 * qty
        no_purchase_streak[drink] = 0
    else:
        purchase_comp = -0.01
        no_purchase_streak[drink] += 1

    # Construct preliminary price
    new_price = current_price * (1 + rand_comp + purchase_comp)

    # 3) Mean‐reversion directly toward $5.00
    alpha = alpha_to_center(new_price)
    new_price += (TARGET_PRICE - new_price) * alpha

    # 4) Enforce floor at $2.00
    if new_price < FLOOR_PRICE:
        new_price = FLOOR_PRICE

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
    last_reset_date = None

    while True:
        now_utc = datetime.now(tz=pytz.utc)
        now_eastern = now_utc.astimezone(EASTERN)
        hour = now_eastern.hour

        if 16 <= hour < 24:
            # Reset history and purchases once at the start of each market day
            if last_reset_date != now_eastern.date():
                try:
                    conn = sqlite3.connect(DB_PATH)
                    c    = conn.cursor()
                    c.execute("DELETE FROM history")
                    c.execute("DELETE FROM purchases")
                    conn.commit()
                    conn.close()
                    last_reset_date = now_eastern.date()
                    print("[Reset] Cleared previous price and purchase history")
                except Exception as e:
                    print(f"[Reset] Failed to clear history/purchases: {e}")

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

