"""
Fertilizer (Urea) Stock Monitor - Cloud version
--------------------------------
Checks the Telangana Fertilizer Booking app's dealer stock API and sends
an email notification whenever a dealer's available bag count goes
from 0 to something greater than 0.

This version reads credentials from environment variables (set as GitHub
Actions secrets), so no sensitive info is stored directly in this file.

It keeps track of previous stock levels in dealer_state.json (committed
back to the repo each run) so it only notifies on NEW availability,
not every single run.
"""

import requests
import json
import os
import sys
import smtplib
from email.mime.text import MIMEText

# ====== CONFIGURATION - pulled from environment variables (GitHub secrets) ======
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_TO_EMAIL = os.environ["NOTIFY_TO_EMAIL"]

# District / Mandal IDs as seen in the captured request URL.
# Change these if you want to monitor a different mandal.
DISTRICT_ID = 28
MANDAL_ID = 547

# ====== Internal config (captured from the app's own traffic) ======
LOGIN_URL = "https://telanganaureasales.com/login"
DEALERS_URL = f"https://telanganaureasales.com/api/GetDealerDetailsMandalWise/{DISTRICT_ID}/{MANDAL_ID}"

# This is the app's own built-in service login (not your personal OTP login).
LOGIN_PAYLOAD = {
    "password": "f2ad06i5-bqa4-4eb8-87b9-908763ea79me",
    "username": "onesoft.markets.authuser",
}

HEADERS_BASE = {
    "User-Agent": "okhttp, Urea-Android/1.0.8",
    "X-App-Version": "1.0.8",
    "X-Platform": "android",
    "Content-Type": "application/json; charset=UTF-8",
}

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dealer_state.json")


def get_token():
    """Log in with the app's built-in service credentials and return a fresh JWT."""
    resp = requests.post(LOGIN_URL, json=LOGIN_PAYLOAD, headers=HEADERS_BASE, timeout=15)
    resp.raise_for_status()
    return resp.json()["token"]


def get_dealers(token):
    """Fetch the current dealer list with stock levels."""
    headers = dict(HEADERS_BASE)
    headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(DEALERS_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def load_previous_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = NOTIFY_TO_EMAIL

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)


def main():
    token = get_token()
    dealers = get_dealers(token)

    previous_state = load_previous_state()
    new_state = {}
    newly_available = []

    for dealer in dealers:
        dealer_id = str(dealer.get("IFMSId"))
        stock = dealer.get("Stock_Available_For_Booking", 0)
        new_state[dealer_id] = stock

        previous_stock = previous_state.get(dealer_id, 0)
        if stock > 0 and previous_stock == 0:
            newly_available.append(dealer)

    if newly_available:
        lines = ["Urea stock now available:"]
        for d in newly_available:
            lines.append(
                f"- {d.get('DealerName')} ({d.get('VillName')}): "
                f"{d.get('Stock_Available_For_Booking')} bags"
            )
        message = "\n".join(lines)
        send_email("Urea Stock Available!", message)
        print(message)
    else:
        print(f"No new stock. Checked {len(dealers)} dealers, all still at 0 (or unchanged).")

    save_state(new_state)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        sys.exit(1)
