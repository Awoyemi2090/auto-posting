import html
import json
import logging
import os
import re
import time
from urllib.parse import urljoin

import feedparser
import requests

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]  # @channelname or numeric ID like -100123...
FEED_URL = os.environ["FEED_URL"]
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))  # seconds
SEEN_FILE = os.getenv("SEEN_FILE", "seen.json")
SUMMARY_LIMIT = int(os.getenv("SUMMARY_LIMIT", "600"))  # characters

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return None  # None = first run


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f)


def entry_id(entry):
    return entry.get("id") or entry.get("link") or entry.get("title")


def clean_text(raw):
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def truncate(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(".,;:!?") + "…"


def get_summary(entry):
    raw = entry.get("summary")
    if not raw and entry.get("content"):
        raw = entry["content"][0].get("value", "")
    return truncate(clean_text(raw), SUMMARY_LIMIT)


def get_image(entry):
    candidates = []

    for m in entry.get("media_content", []):
        url = m.get("url", "")
        if (
            m.get("medium") == "image"
            or m.get("type", "").startswith("image")
            or url.lower().split("?")[0].endswith(IMAGE_EXTS)
        ):
            candidates.append(url)

    for m in entry.get("media_thumbnail", []):
        candidates.append(m.get("url", ""))

    for link in entry.get("links", []):
        if link.get("rel") == "enclosure" and link.get("type", "").startswith("image"):
            candidates.append(link.get("href", ""))

    # Fall back to the first <img> inside the post content
    html_parts = [entry.get("summary", "")]
    if entry.get("content"):
        html_parts.append(entry["content"][0].get("value", ""))
    for part in html_parts:
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', part or "", re.I)
        if match:
            candidates.append(match.group(1))

    for url in candidates:
        if url:
            return urljoin(entry.get("link", ""), url)
    return None


def telegram(method, payload):
    for _ in range(3):
        r = requests.post(f"{API_BASE}/{method}", json=payload, timeout=30)
        if r.status_code == 429:  # rate limited
            wait = r.json().get("parameters", {}).get("retry_after", 5)
            time.sleep(wait + 1)
            continue
        if not r.ok:
            logging.error("Telegram %s error: %s", method, r.text)
            return False
        return True
    return False


def send(entry):
    title = html.escape(truncate(clean_text(entry.get("title", "New post")), 200))
    summary = html.escape(get_summary(entry))
    text = f"<b>{title}</b>"
    if summary:
        text += f"\n\n{summary}"

    image = get_image(entry)
    if image:
        ok = telegram(
            "sendPhoto",
            {
                "chat_id": CHAT_ID,
                "photo": image,
                "caption": text,
                "parse_mode": "HTML",
            },
        )
        if ok:
            return True
        logging.info("Photo failed, sending text only")

    return telegram(
        "sendMessage",
        {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    )


def check_feed(seen):
    feed = feedparser.parse(FEED_URL)
    if feed.bozo and not feed.entries:
        logging.warning("Could not read feed: %s", feed.get("bozo_exception"))
        return seen

    entries = [e for e in feed.entries if entry_id(e)]
    logging.info("Feed returned %d entries", len(entries))
    if not entries:
        logging.warning("No entries found in feed, nothing to do")
        return seen

    # First run (or empty seen file): remember what's already there
    if not seen:
        seen = {entry_id(e) for e in entries}
        save_seen(seen)
        logging.info("First run: marked %d existing items as seen", len(seen))
        return seen

    new_entries = [e for e in entries if entry_id(e) not in seen]
    for entry in reversed(new_entries):  # oldest first
        if send(entry):
            seen.add(entry_id(entry))
            save_seen(seen)
            logging.info("Posted: %s", entry.get("title"))
        time.sleep(3)  # stay under Telegram's rate limits
    return seen


def main():
    seen = load_seen()
    if os.getenv("RUN_ONCE") == "1":  # for GitHub Actions: check once and exit
        check_feed(seen)
        return
    while True:
        try:
            seen = check_feed(seen)
        except Exception:
            logging.exception("Error while checking feed")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
import html
import json
import logging
import os
import re
import time
from urllib.parse import urljoin

import feedparser
import requests

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]  # @channelname or numeric ID like -100123...
FEED_URL = os.environ["FEED_URL"]
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))  # seconds
SEEN_FILE = os.getenv("SEEN_FILE", "seen.json")
SUMMARY_LIMIT = int(os.getenv("SUMMARY_LIMIT", "600"))  # characters

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return None  # None = first run


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f)


def entry_id(entry):
    return entry.get("id") or entry.get("link") or entry.get("title")


def clean_text(raw):
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def truncate(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(".,;:!?") + "…"


def get_summary(entry):
    raw = entry.get("summary")
    if not raw and entry.get("content"):
        raw = entry["content"][0].get("value", "")
    return truncate(clean_text(raw), SUMMARY_LIMIT)


def get_image(entry):
    candidates = []

    for m in entry.get("media_content", []):
        url = m.get("url", "")
        if (
            m.get("medium") == "image"
            or m.get("type", "").startswith("image")
            or url.lower().split("?")[0].endswith(IMAGE_EXTS)
        ):
            candidates.append(url)

    for m in entry.get("media_thumbnail", []):
        candidates.append(m.get("url", ""))

    for link in entry.get("links", []):
        if link.get("rel") == "enclosure" and link.get("type", "").startswith("image"):
            candidates.append(link.get("href", ""))

    # Fall back to the first <img> inside the post content
    html_parts = [entry.get("summary", "")]
    if entry.get("content"):
        html_parts.append(entry["content"][0].get("value", ""))
    for part in html_parts:
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', part or "", re.I)
        if match:
            candidates.append(match.group(1))

    for url in candidates:
        if url:
            return urljoin(entry.get("link", ""), url)
    return None


def telegram(method, payload):
    for _ in range(3):
        r = requests.post(f"{API_BASE}/{method}", json=payload, timeout=30)
        if r.status_code == 429:  # rate limited
            wait = r.json().get("parameters", {}).get("retry_after", 5)
            time.sleep(wait + 1)
            continue
        if not r.ok:
            logging.error("Telegram %s error: %s", method, r.text)
            return False
        return True
    return False


def send(entry):
    title = html.escape(truncate(clean_text(entry.get("title", "New post")), 200))
    summary = html.escape(get_summary(entry))
    text = f"<b>{title}</b>"
    if summary:
        text += f"\n\n{summary}"

    image = get_image(entry)
    if image:
        ok = telegram(
            "sendPhoto",
            {
                "chat_id": CHAT_ID,
                "photo": image,
                "caption": text,
                "parse_mode": "HTML",
            },
        )
        if ok:
            return True
        logging.info("Photo failed, sending text only")

    return telegram(
        "sendMessage",
        {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    )


def check_feed(seen):
    feed = feedparser.parse(FEED_URL)
    if feed.bozo and not feed.entries:
        logging.warning("Could not read feed: %s", feed.get("bozo_exception"))
        return seen

    entries = [e for e in feed.entries if entry_id(e)]
    logging.info("Feed returned %d entries", len(entries))
    if not entries:
        logging.warning("No entries found in feed, nothing to do")
        return seen

    # First run (or empty seen file): remember what's already there
    if not seen:
        seen = {entry_id(e) for e in entries}
        save_seen(seen)
        logging.info("First run: marked %d existing items as seen", len(seen))
        return seen

    new_entries = [e for e in entries if entry_id(e) not in seen]
    for entry in reversed(new_entries):  # oldest first
        if send(entry):
            seen.add(entry_id(entry))
            save_seen(seen)
            logging.info("Posted: %s", entry.get("title"))
        time.sleep(3)  # stay under Telegram's rate limits
    return seen


def main():
    seen = load_seen()
    if os.getenv("RUN_ONCE") == "1":  # for GitHub Actions: check once and exit
        check_feed(seen)
        return
    while True:
        try:
            seen = check_feed(seen)
        except Exception:
            logging.exception("Error while checking feed")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
    
