"""
Think2 new-item watcher -> Telegram notifications.
Runs once per call; GitHub Actions runs it on a schedule.
Token and chat ID come from GitHub secrets (never put them in this file).
"""

import json
import os
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

# Newest women's items first, 36 per page
WATCH_URL = "https://think2.eu/en/women?order=product.date_add.desc&resultsPerPage=36"
SEEN_FILE = Path(__file__).with_name("seen_items.json")

HEADERS = {"User-Agent": "Mozilla/5.0 (personal new-item notifier)"}
PRODUCT_CODE = re.compile(r"-(at\d+)/?$", re.IGNORECASE)


def fetch_items():
    """Return a dict {code: {name, url, price}} of products on the listing page."""
    resp = requests.get(WATCH_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = {}
    # Product titles are links inside headings
    for link in soup.select("h1 a, h2 a, h3 a, h4 a"):
        url = link.get("href", "")
        match = PRODUCT_CODE.search(url)
        if not match:
            continue
        code = match.group(1).upper()
        items[code] = {"name": link.get_text(strip=True), "url": url, "price": ""}

    # Prices are separate links to the same product URL, containing "€"
    for link in soup.find_all("a", href=True):
        text = link.get_text(strip=True)
        match = PRODUCT_CODE.search(link["href"])
        if match and "€" in text:
            code = match.group(1).upper()
            if code in items and not items[code]["price"]:
                items[code]["price"] = text

    return items


def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=30)
    r.raise_for_status()


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return None  # first run


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen)))


def check_once():
    items = fetch_items()
    if not items:
        print("Warning: found no products. The page layout may have changed.")
        return

    seen = load_seen()
    if seen is None:
        # First run: remember what's there now, don't spam you with 36 messages
        save_seen(set(items))
        send_telegram(f"👋 Watcher started. Tracking {len(items)} current items; "
                      "you'll get a message for anything new.")
        print(f"First run: saved {len(items)} items.")
        return

    new_codes = [c for c in items if c not in seen]
    for code in new_codes:
        item = items[code]
        send_telegram(f"🆕 {item['name']}\n{item['price']}\n{item['url']}")
        time.sleep(1)  # avoid Telegram rate limits

    save_seen(seen | set(items))
    print(f"Checked: {len(new_codes)} new item(s).")


if __name__ == "__main__":
    check_once()
