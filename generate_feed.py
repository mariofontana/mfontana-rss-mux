import hashlib, os, re, sys, time, requests, feedparser
from datetime import datetime, timezone
from dateutil import parser as dtparse
from html import escape

# Config base
MAX_ITEMS = int(os.getenv("MAX_ITEMS", "100"))
KEYWORDS = [s.strip().lower() for s in os.getenv("KEYWORDS", "").split(",") if s.strip()]
SINCE_DAYS = int(os.getenv("SINCE_DAYS", "0"))  # 0 = nessun filtro per data
TITLE = os.getenv("FEED_TITLE", "Personal Aggregated Feed")

def normalize_url(url:str)->str:
    if not url: return ""
    # togli tracking semplice
    url = re.sub(r"[?&](utm_[^&]+|fbclid)=[^&#]+", "", url)
    url = re.sub(r"[?&]$", "", url)
    return url

def fetch(url):
    # rispetta rate limit basilare
    headers = {"User-Agent": "PersonalFeedMux/1.0 (+github actions)"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.text

def to_dt(value):
    if not value: return None
    # feedparser può dare struct_time; altrimenti stringa ISO/RFC
    try:
        if isinstance(value, time.struct_time):
            return datetime(*value[:6], tzinfo=timezone.utc)
        return dtparse.parse(str(value))
    except Exception:
        return None

def load_feeds(feed_urls):
    entries = []
    for u in feed_urls:
        try:
            xml = fetch(u)
            fp = feedparser.parse(xml)
            for e in fp.entries:
                title = (e.get("title") or "").strip()
                link = normalize_url(e.get("link") or e.get("id") or "")
                guid = (e.get("id") or e.get("guid") or link or title).strip()
                # preferisci updated/published
                updated = to_dt(e.get("updated_parsed") or e.get("published_parsed") or e.get("updated") or e.get("published"))
                if not updated:
                    updated = datetime.now(timezone.utc)
                summary = (e.get("summary") or e.get("description") or "").strip()
                entries.append({
                    "title": title,
                    "link": link,
                    "guid": guid,
                    "updated": updated,
                    "summary": summary
                })
        except Exception as ex:
            print(f"[warn] feed error {u}: {ex}", file=sys.stderr)
    return entries

def dedup_sort_filter(entries):
    # de-dup su guid/link normalizzato
    seen = set(); out = []
    for it in entries:
        key = (it["guid"] or it["link"] or it["title"]).lower()
        if key in seen: continue
        seen.add(key)
        out.append(it)

    # filtra per keywords
    if KEYWORDS:
        out = [
            it for it in out
            if any(kw in (it["title"] + " " + it["summary"]).lower() for kw in KEYWORDS)
        ]

    # filtra per data
    if SINCE_DAYS > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=SINCE_DAYS)
        out = [it for it in out if it["updated"] and it["updated"] >= cutoff]

    # sort desc per updated
    out.sort(key=lambda x: x["updated"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return out[:MAX_ITEMS]

def atom(entries, self_url):
    now = datetime.now(timezone.utc).isoformat()
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f'  <title>{escape(TITLE)}</title>',
        f'  <updated>{now}</updated>',
        f'  <id>{escape(self_url)}</id>',
        f'  <link rel="self" href="{escape(self_url)}"/>'
    ]
    for it in entries:
        uid = it["guid"] or it["link"] or hashlib.md5((it["title"] + it["link"]).encode("utf-8")).hexdigest()
        upd = (it["updated"] or datetime.now(timezone.utc)).isoformat()
        parts += [
            "  <entry>",
            f'    <title>{escape(it["title"] or "")}</title>',
            f'    <link href="{escape(it["link"] or "")}"/>',
            f'    <id>{escape(uid)}</id>',
            f'    <updated>{upd}</updated>',
            '    <summary type="html"><![CDATA[' + (it["summary"] or "") + ']]></summary>',
            "  </entry>"
        ]
    parts.append("</feed>")
    return "\n".join(parts)

if __name__ == "__main__":
    repo_url = os.getenv("REPO_PAGES_URL", "https://example.com/feed.xml")
    # leggi feed list
    with open("feeds.txt", "r", encoding="utf-8") as f:
        feed_urls = [l.strip() for l in f.readlines() if l.strip() and not l.strip().startswith("#")]
    entries = load_feeds(feed_urls)
    final_items = dedup_sort_filter(entries)
    xml = atom(final_items, repo_url)
    os.makedirs("public", exist_ok=True)
    with open("public/feed.xml", "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"Generated {len(final_items)} items → public/feed.xml")
