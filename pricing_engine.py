import os
import time
import csv
import random
import smtplib
import pytz
from datetime import datetime
from io import BytesIO
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import pandas as pd

# ---------- CONFIGURATION ----------
DRINKS = [
    "bud_light", "budweiser", "busch_light", "coors_light", "corona_light",
    "guinness", "heineken", "michelob_ultra", "miller_light", "modelo"
]
PRICE_DIR = "data"
PURCHASES_FILE = os.path.join(PRICE_DIR, "simulated_purchases.csv")

EMAIL_SENDER = "caleb_hussain@yahoo.com"
EMAIL_PASSWORD = "oumentqpjhockghh"  # Yahoo app password
EMAIL_RECEIVER = "caleb_hussain@yahoo.com"
SMTP_SERVER = "smtp.mail.yahoo.com"
SMTP_PORT = 587

# ---------- UTILITIES ----------
def get_latest_price(drink):
    path = os.path.join(PRICE_DIR, f"{drink}_history.csv")
    try:
        df = pd.read_csv(path)
        return float(df["price"].iloc[-1])
    except Exception:
        return None

def append_price(drink, price):
    path = os.path.join(PRICE_DIR, f"{drink}_history.csv")
    now = datetime.now().strftime("%H:%M:%S")
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([now, price])

def simulate_purchase():
    drink = random.choice(DRINKS)
    price = get_latest_price(drink)
    if price is None:
        return

    if price < 5:
        qty = random.randint(2, 3)
    elif price < 6.5:
        qty = random.randint(1, 2)
    else:
        qty = random.choice([0, 1])

    if qty == 0:
        return

    now = datetime.now().strftime("%H:%M:%S")
    with open(PURCHASES_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([now, drink, qty, price])

    print(f"Simulated purchase: {qty}x {drink} at ${price}")

def update_price(drink):
    price = get_latest_price(drink)
    if price is None:
        price = 5.00

    new_price = price * random.uniform(0.98, 1.02)

    # Check for purchases
    if os.path.exists(PURCHASES_FILE):
        with open(PURCHASES_FILE, "r") as f:
            rows = list(csv.reader(f))
            if any(row[1] == drink for row in rows):
                new_price *= 1.01  # Boost for purchases

    new_price = round(min(max(new_price, 3.00), 10.00), 2)
    append_price(drink, new_price)
    print(f"Updated {drink} price to ${new_price}")

def archive_and_email():
    print("Archiving and emailing recap...")
    tz = pytz.timezone("US/Eastern")
    today = datetime.now(tz).strftime("%Y-%m-%d")

    with pd.ExcelWriter(f"price_archive_{today}.xlsx", engine="xlsxwriter") as writer:
        summary_lines = []

        total_sales = 0
        total_units = 0

        for drink in DRINKS:
            path = os.path.join(PRICE_DIR, f"{drink}_history.csv")
            if not os.path.exists(path):
                continue

            df = pd.read_csv(path)
            df.to_excel(writer, sheet_name=drink, index=False)

            o = df["price"].iloc[0]
            h = df["price"].max()
            l = df["price"].min()
            c = df["price"].iloc[-1]

            summary_lines.append(
                f"{drink.replace('_', ' ').title()}\n"
                f"• Open: ${o:.2f}\n• High: ${h:.2f}\n• Low: ${l:.2f}\n• Close: ${c:.2f}"
            )

        if os.path.exists(PURCHASES_FILE):
            df_p = pd.read_csv(PURCHASES_FILE, names=["time", "drink", "qty", "price"])
            df_p.to_excel(writer, sheet_name="purchases", index=False)

            grouped = df_p.groupby("drink").agg(
                qty=("qty", "sum"),
                total_sales=("price", lambda x: (x * df_p.loc[x.index, "qty"]).sum())
            )

            for drink, row in grouped.iterrows():
                summary_lines.append(
                    f"{drink.replace('_', ' ').title()}\n"
                    f"• Units Sold: {int(row.qty)}\n• Total Sales: ${row.total_sales:.2f}"
                )
                total_sales += row.total_sales
                total_units += row.qty

            summary_lines.append(f"\nTotal Units Sold: {int(total_units)}")
            summary_lines.append(f"Total Sales: ${total_sales:.2f}")

            os.remove(PURCHASES_FILE)

        # Send email
        body = "\n\n".join(summary_lines)
        msg = MIMEMultipart()
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER
        msg["Subject"] = f"The Exchange Recap – {today}"
        msg.attach(MIMEText(body, "plain"))

        excel_path = f"price_archive_{today}.xlsx"
        with open(excel_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={excel_path}")
            msg.attach(part)

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("Recap email sent.")

        # Clear CSVs
        for drink in DRINKS:
            path = os.path.join(PRICE_DIR, f"{drink}_history.csv")
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["time", "price"])

# ---------- MAIN LOOP ----------
print("Starting pricing engine...")
sent_today = False

while True:
    now = datetime.now(pytz.timezone("US/Eastern"))

    if 16 <= now.hour <= 23:
        for drink in DRINKS:
            update_price(drink)
        simulate_purchase()
        sent_today = False

    elif now.hour == 0 and not sent_today:
        archive_and_email()
        sent_today = True

    time.sleep(60)
