# generate_feed.py
import hashlib, os, re, sys, time, requests, feedparser
from datetime import datetime, timezone, timedelta
from dateutil import parser as dtparse
from html import escape
from urllib.parse import urlparse

# ----- Config base (da ENV) -----
MAX_ITEMS   = int(os.getenv("MAX_ITEMS", "100"))
KEYWORDS    = [s.strip().lower() for s in os.getenv("KEYWORDS", "").split(",") if s.strip()]
SINCE_DAYS  = int(os.getenv("SINCE_DAYS", "0"))  # 0 = nessun filtro per data
TITLE       = os.getenv("FEED_TITLE", "Personal Aggregated Feed")
AUTHOR_NAME = os.getenv("FEED_AUTHOR_NAME", "mariofontana")  # feed-level author per Atom
SELF_URL    = os.getenv("REPO_PAGES_URL", "https://example.com/feed.xml")

def normalize_url(url:str)->str:
    if not url: return ""
    url = re.sub(r"[?&](utm_[^&]+|fbclid)=[^&#]+", "", url)
    url = re.sub(r"[?&]$", "", url)
    return url

def fetch(url):
    headers = {"User-Agent": "PersonalFeedMux/1.0 (+github actions)"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.text

def to_dt(value):
    if not value: return None
    try:
        if isinstance(value, time.struct_time):
            return datetime(*value[:6], tzinfo=timezone.utc)
        dt = dtparse.parse(str(value))
        if not
