"""First-party visit statistics: no cookies, no third party, no stored IP addresses.

What is kept per event: time, the kind of event, the page, the visitor's country, the site the
visitor came from (domain only), any utm_ campaign tags, phone or computer, and for ship
lookups the IMO, ship name and company (all public register facts). Unique visitors are counted
with a hash of IP and browser that uses a salt replaced every day and then deleted, so a
visitor cannot be recognised across days or traced back.

Storage is a SQLite file in CARBONKEEL_DATA_DIR (a persistent volume in production). Events
older than RETENTION_DAYS are deleted.
"""
import hashlib
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qs, urlparse

from . import geo

RETENTION_DAYS = 730
CLIENT_KINDS = {"view", "contact_open", "contact_send", "email_click", "cta_latest"}
BOT_MARKERS = ("bot", "crawl", "spider", "slurp", "preview", "monitor", "curl", "wget", "python", "headless",
               "consul", "fly-", "uptime", "pingdom", "lighthouse")

_lock = threading.Lock()
_ready = False


def db_path() -> str:
    base = os.environ.get("CARBONKEEL_DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", "..", "data")
    return os.path.join(base, "analytics.sqlite")


def _conn() -> sqlite3.Connection:
    global _ready
    if not _ready:
        os.makedirs(os.path.dirname(db_path()), exist_ok=True)
    c = sqlite3.connect(db_path(), timeout=5)
    if not _ready:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY, ts REAL, day TEXT, kind TEXT, path TEXT, country TEXT, ref TEXT,
              utm_source TEXT, utm_medium TEXT, utm_campaign TEXT, device TEXT, visitor TEXT,
              imo TEXT, ship TEXT, company TEXT, detail TEXT);
            CREATE INDEX IF NOT EXISTS ev_day ON events(day);
            CREATE TABLE IF NOT EXISTS salts (day TEXT PRIMARY KEY, salt TEXT);""")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
        c.execute("DELETE FROM events WHERE day < ?", (cutoff,))
        c.commit()
        _ready = True
    return c


def is_bot(ua: str) -> bool:
    u = (ua or "").lower()
    return not u or any(m in u for m in BOT_MARKERS)


def _device(ua: str) -> str:
    u = (ua or "").lower()
    return "phone" if any(m in u for m in ("mobile", "iphone", "android")) else (
        "tablet" if "ipad" in u or "tablet" in u else "computer")


def _visitor(c: sqlite3.Connection, day: str, ip: str, ua: str) -> str:
    row = c.execute("SELECT salt FROM salts WHERE day = ?", (day,)).fetchone()
    if row is None:
        salt = secrets.token_hex(16)
        c.execute("DELETE FROM salts WHERE day <> ?", (day,))
        c.execute("INSERT OR IGNORE INTO salts(day, salt) VALUES (?, ?)", (day, salt))
        row = c.execute("SELECT salt FROM salts WHERE day = ?", (day,)).fetchone()
    return hashlib.sha256(f"{row[0]}|{ip}|{ua}".encode()).hexdigest()[:16]


def _domain(url: str, own: str) -> str:
    try:
        host = (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""
    host = host[4:] if host.startswith("www.") else host
    return "" if not host or host == own or host.endswith("." + own) else host[:80]


def record(kind: str, ip: str, ua: str, path: str = "", referrer: str = "", query: str = "",
           own_host: str = "carbonkeel.com", imo: str = "", ship: str = "", company: str = "",
           detail: str = "") -> bool:
    """Store one event. Returns False (and stores nothing) for bots."""
    if is_bot(ua):
        return False
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    qs = parse_qs((query or "").lstrip("?"))
    utm = [(qs.get(k) or [""])[0][:60] for k in ("utm_source", "utm_medium", "utm_campaign")]
    try:
        with _lock:
            c = _conn()
            try:
                c.execute("""INSERT INTO events(ts, day, kind, path, country, ref, utm_source, utm_medium,
                             utm_campaign, device, visitor, imo, ship, company, detail)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (time.time(), day, kind[:30], (path or "")[:80], geo.country(ip),
                           _domain(referrer, own_host), *utm, _device(ua), _visitor(c, day, ip, ua),
                           (imo or "")[:12], (ship or "")[:80], (company or "")[:120], (detail or "")[:120]))
                c.commit()
            finally:
                c.close()
    except sqlite3.Error:
        return False
    return True


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days - 1)).strftime("%Y-%m-%d")


def summary(days: int = 30) -> dict:
    since = _since(days)
    with _lock:
        c = _conn()
        try:
            q = lambda sql, *a: c.execute(sql, (since, *a)).fetchall()
            totals = {k: n for k, n in q("SELECT kind, COUNT(*) FROM events WHERE day >= ? GROUP BY kind")}
            visitors = q("SELECT COUNT(DISTINCT day || visitor) FROM events WHERE day >= ?")[0][0]
            daily = q("""SELECT day, COUNT(DISTINCT visitor), SUM(kind='view'), SUM(kind='lookup')
                         FROM events WHERE day >= ? GROUP BY day ORDER BY day""")
            countries = q("""SELECT country, COUNT(DISTINCT day || visitor) n FROM events WHERE day >= ?
                             GROUP BY country ORDER BY n DESC LIMIT 25""")
            refs = q("""SELECT ref, COUNT(*) n FROM events WHERE day >= ? AND kind='view' AND ref <> ''
                        GROUP BY ref ORDER BY n DESC LIMIT 20""")
            campaigns = q("""SELECT utm_source, utm_medium, utm_campaign, COUNT(*) n FROM events
                             WHERE day >= ? AND kind='view' AND utm_source <> ''
                             GROUP BY 1, 2, 3 ORDER BY n DESC LIMIT 20""")
            pages = q("""SELECT path, COUNT(*) n FROM events WHERE day >= ? AND kind='view'
                         GROUP BY path ORDER BY n DESC LIMIT 10""")
            devices = q("""SELECT device, COUNT(DISTINCT day || visitor) n FROM events WHERE day >= ?
                           GROUP BY device ORDER BY n DESC""")
            leads = q("""SELECT company, COUNT(*) n, COUNT(DISTINCT imo), GROUP_CONCAT(DISTINCT country),
                                MAX(ts), GROUP_CONCAT(DISTINCT ship)
                         FROM events WHERE day >= ? AND company <> '' GROUP BY company
                         ORDER BY n DESC, MAX(ts) DESC LIMIT 100""")
            recent = c.execute("""SELECT ts, kind, country, ship, company, detail, ref FROM events
                                  WHERE kind NOT IN ('view') ORDER BY ts DESC LIMIT 50""").fetchall()
        finally:
            c.close()
    return {"days": days, "since": since, "totals": totals, "visitors": visitors, "daily": daily,
            "countries": countries, "referrers": refs, "campaigns": campaigns, "pages": pages,
            "devices": devices, "leads": leads, "recent": recent}
