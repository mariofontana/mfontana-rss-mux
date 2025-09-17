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
AUTHOR_NAME = os.getenv("FEED_AUTHOR_NAME", "Mario Fontana")  # feed-level author per Atom
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
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def source_name(fp, url):
    name = (getattr(fp, "feed", {}) or {}).get("title")
    if name: return name
    try:
        host = urlparse(url).hostname or ""
        return host.replace("www.", "") if host else url
    except Exception:
        return url

def sanitize_html(html: str) -> str:
    if not html:
        return ""
    # rimuovi attributi style (il validator li segnala come "potentially dangerous")
    html = re.sub(r'\sstyle=("|\').*?\1', "", html, flags=re.IGNORECASE)
    # opzion. elimina <script>…</script>
    html = re.sub(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", "", html, flags=re.IGNORECASE|re.DOTALL)
    return html

def load_feeds(feed_urls):
    entries = []
    for u in feed_urls:
        try:
            xml = fetch(u)
            fp = feedparser.parse(xml)
            src = source_name(fp, u)
            for e in fp.entries:
                title = (e.get("title") or "").strip()
                link = normalize_url(e.get("link") or e.get("id") or "")
                guid = (e.get("id") or e.get("guid") or link or title).strip()

                updated = to_dt(
                    e.get("updated_parsed") or e.get("published_parsed") or
                    e.get("updated") or e.get("published")
                )
                summary = sanitize_html((e.get("summary") or e.get("description") or "").strip())

                entries.append({
                    "title": title,
                    "link": link,
                    "guid": guid,
                    "updated": updated,
                    "summary": summary,
                    "author": src,   # useremo la sorgente come autore item
                })
        except Exception as ex:
            print(f"[warn] feed error {u}: {ex}", file=sys.stderr)
    return entries

def dedup_sort_filter(entries):
    # de-dup su guid/link normalizzato
    seen = set(); out = []
    for it in entries:
        key = (it["guid"] or it["link"] or it["title"]).lower()
        if key in seen: 
            continue
        seen.add(key)
        out.append(it)

    # filtra per keywords
    if KEYWORDS:
        out = [it for it in out if any(kw in (it["title"] + " " + it["summary"]).lower() for kw in KEYWORDS)]

    # filtra per data
    if SINCE_DAYS > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=SINCE_DAYS)
        out = [it for it in out if it["updated"] and it["updated"] >= cutoff]

    # sort desc
    out.sort(key=lambda x: x["updated"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    out = out[:MAX_ITEMS]

    # Evita stessa timestamp per troppi item: se mancante, assegna fallback unico
    now = datetime.now(timezone.utc)
    fallback_idx = 0
    for it in out:
        if not it["updated"]:
            # assegna timestamp univoci scalando di secondi
            it["updated"] = now - timedelta(seconds=fallback_idx)
            fallback_idx += 1
    return out

def atom(entries, self_url):
    now = datetime.now(timezone.utc).isoformat()
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f'  <title>{escape(TITLE)}</title>',
        f'  <updated>{now}</updated>',
        f'  <id>{escape(self_url)}</id>',
        f'  <link rel="self" href="{escape(self_url)}"/>',
        f'  <author><name>{escape(AUTHOR_NAME)}</name></author>',
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
            f'    <author><name>{escape(it.get("author") or AUTHOR_NAME)}</name></author>',
            '    <summary type="html"><![CDATA[' + (it["summary"] or "") + ']]></summary>',
            "  </entry>"
        ]
    parts.append("</feed>")
    return "\n".join(parts)

if __name__ == "__main__":
    with open("feeds.txt", "r", encoding="utf-8") as f:
        feed_urls = [l.strip() for l in f.readlines() if l.strip() and not l.strip().startswith("#")]
    entries = load_feeds(feed_urls)
    final_items = dedup_sort_filter(entries)
    xml = atom(final_items, SELF_URL)
    os.makedirs("public", exist_ok=True)
    with open("public/feed.xml", "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"Generated {len(final_items)} items → public/feed.xml")
