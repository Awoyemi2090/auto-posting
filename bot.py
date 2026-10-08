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
CHAT_IDS = [c.strip() for c in os.environ["CHAT_ID"].split(",") if c.strip()]
# CHAT_ID can hold one or more IDs separated by commas: @channel1,-1001234567890
FEED_URL = os.environ["FEED_URL"]
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))  # seconds
SEEN_FILE = os.getenv("SEEN_FILE", "seen.json")
SUMMARY_LIMIT = int(os.getenv("SUMMARY_LIMIT", "600"))  # characters

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

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


def get_og_image(page_url):
    """Fetch the article page and read its preview image (og:image)."""
    if not page_url:
        return None
    try:
        r = requests.get(page_url, headers={"User-Agent": USER_AGENT}, timeout=20)
    except requests.RequestException as exc:
        logging.warning("Could not open article page: %s", exc)
        return None
    if not r.ok:
        logging.warning("Article page returned HTTP %s", r.status_code)
        return None
    head = r.text[:300000]
    patterns = (
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, head, re.I)
        if match:
            return html.unescape(match.group(1))
    return None


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

    # Nothing in the feed: use the article's own preview image
    og = get_og_image(entry.get("link"))
    return urljoin(entry.get("link", ""), og) if og else None


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


def send_to(chat_id, entry):
    title = html.escape(truncate(clean_text(entry.get("title", "New post")), 200))
    summary = html.escape(get_summary(entry))
    text = f"<b>{title}</b>"
    if summary:
        text += f"\n\n{summary}"

    image = get_image(entry)
    logging.info("Image: %s", image or "none")
    if image:
        ok = telegram(
            "sendPhoto",
            {
                "chat_id": chat_id,
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
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    )


def send(entry):
    # Post to every channel; count as sent if at least one succeeded
    results = []
    for chat_id in CHAT_IDS:
        ok = send_to(chat_id, entry)
        if not ok:
            logging.warning("Failed to post to %s", chat_id)
        results.append(ok)
        time.sleep(1)
    return any(results)


def check_feed(seen):
    resp = requests.get(FEED_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    logging.info(
        "Feed HTTP %s, %d bytes, type %s",
        resp.status_code,
        len(resp.content),
        resp.headers.get("Content-Type"),
    )
    if not resp.ok:
        logging.warning("Feed request failed with status %s", resp.status_code)
        return seen
    feed = feedparser.parse(resp.content)
    logging.info(
        "Parsed as %s, raw entries: %d", feed.get("version") or "unknown", len(feed.entries)
    )
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
