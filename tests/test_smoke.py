#!/usr/bin/env python3
"""Smoke test — catches the class of bug the engine tests cannot see.

On 3 Oct 2026 a stray apostrophe in `operator's` closed a JavaScript string
early, the whole app script failed to parse, and every button in the browser
stopped working. The 144 engine tests still passed, because the engines were
fine. The API still answered, because FastAPI was fine. Only the page was
dead — and nothing in the suite was looking at the page.

So this file checks the things that live outside the engines:
  1. both HTML pages parse as JavaScript (no syntax errors)
  2. the critical endpoints answer with the right status
  3. the calculator is open by default and locks when CARBONKEEL_REQUIRE_KEY is set
  4. nothing customer-facing leaks a raw API path or a price

Run:  python tests/test_smoke.py          (starts its own server)
"""
import io
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

PASS, FAIL = [], []


def ok(name):
    PASS.append(name)
    print(f"  [ok]   {name}")


def bad(name, detail=""):
    FAIL.append(name)
    print(f"  [FAIL] {name}{(' - ' + str(detail)) if detail else ''}")


# ----------------------------------------------------------------- 1. JS --
def scripts_in(path):
    html = open(path, encoding="utf-8").read()
    return re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html,
                      re.S | re.I)


def check_js_parses(path, label):
    """Parse every inline <script> with Node if present; otherwise fall back
    to a quote-balance check that would have caught the real bug."""
    blocks = scripts_in(path)
    if not blocks:
        bad(f"{label}: no inline script found")
        return
    import shutil
    import subprocess
    node = shutil.which("node")
    if node:
        for i, src in enumerate(blocks, 1):
            r = subprocess.run([node, "--check", "-"], input=src, text=True,
                               capture_output=True, encoding="utf-8",
                               errors="replace")
            if r.returncode != 0:
                first = (r.stderr.strip().splitlines() or ["?"])[0]
                bad(f"{label}: script {i} has a syntax error", first)
                return
        ok(f"{label}: {len(blocks)} inline script(s) parse (node --check)")
        return
    # No node: approximate. Strip comments and template/regex-free lines, then
    # require balanced ' and " on each statement line. Crude, but it is exactly
    # the failure mode that bit us.
    problems = 0
    for src in blocks:
        for n, line in enumerate(src.split("\n"), 1):
            s = line.strip()
            if not s or s.startswith("//") or s.startswith("*") or s.startswith("/*"):
                continue
            body = re.sub(r"\\.", "", s)          # drop escaped chars
            if body.count("'") % 2 or body.count('"') % 2:
                # a line may legitimately continue a template literal
                if "`" in body or body.endswith("+") or body.endswith(","):
                    continue
                problems += 1
                if problems == 1:
                    bad(f"{label}: unbalanced quotes near line {n}", s[:70])
    if not problems:
        ok(f"{label}: quote balance clean (install node for a real parse)")


# -------------------------------------------------------------- 2. HTTP --
BASE = "http://127.0.0.1:8111"


def http(path, method="GET", body=None, timeout=90):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                    # noqa: BLE001
        return 0, str(e)


def serve():
    import uvicorn
    from api.main import app
    cfg = uvicorn.Config(app, host="127.0.0.1", port=8111, log_level="error")
    uvicorn.Server(cfg).run()


def check_endpoints():
    cases = [
        ("/", 200, "landing page at the root"),
        ("/app", 200, "app shell"),
        ("/home", 200, "app serves the landing page (one server shows the whole journey)"),
        ("/privacy", 200, "privacy notice"),
        ("/sitemap.xml", 200, "sitemap"),
        ("/api/access/status", 200, "access status"),
        ("/api/lookup/9464663?dwt=93000&eua_price=90&pool_price=120&deficit_years=2"
         "&charter_from=2025-01-01&charter_to=2025-06-30&fueleu_basis=pool", 200, "lookup with every input"),
        ("/api/lookup/9464663?eua_price=0", 422, "lookup rejects a zero allowance price"),
        ("/api/lookup/9464663?charter_from=2025-01-01", 422, "lookup needs both charter dates"),
        ("/report/ship/9464663?dwt=93000", 200, "single-ship report"),
        ("/report/ship/9464663.csv?dwt=93000", 200, "single-ship CSV"),
        ("/healthz", 200, "healthz"),
        ("/robots.txt", 200, "robots.txt"),
        ("/privacy.html", 200, "app serves the privacy notice (relative links work)"),
        ("/api/search?q=OLDENDORFF", 200, "search"),
        ("/api/search?q=a", 422, "search rejects short query"),
        ("/api/lookup/9464663", 200, "lookup"),
        ("/api/lookup/0000000", 404, "lookup 404s unknown IMO"),
        ("/api/eexi/9464663?dwt=93000", 200, "eexi"),
        ("/api/fleet?imos=9464663,9463633", 200, "fleet"),
        ("/api/calendar?year=2026", 200, "calendar"),
        ("/api/audit/9464663?dwt=93000", 200, "audit worksheet"),
    ]
    for path, want, label in cases:
        got, _ = http(path)
        ok(label) if got == want else bad(label, f"got {got}, want {want}")

    # the calculator is open by default; the gate is one environment setting away
    payload = {"ship_type": "bulk_carrier", "dwt": 50000, "year": 2026,
               "fuel_tonnes": {"hfo": 3000}, "distance_nm": 50000}
    got, _ = http("/api/cii/compute", "POST", payload)
    ok("CII calculator open by default") if got == 200 else bad("CII calculator open by default", got)
    got, _ = http("/api/calc", "POST", dict(payload, scope={"intra_eea": 50, "extra_eea": 30}))
    ok("your-data bill") if got == 200 else bad("your-data bill", got)
    got, _ = http("/api/calc", "POST", dict(payload, scope={"intra_eea": 80, "extra_eea": 30}))
    ok("voyage shares over 100% rejected") if got == 422 else bad("voyage shares over 100% rejected", got)
    os.environ["CARBONKEEL_REQUIRE_KEY"] = "1"
    try:
        got, _ = http("/api/cii/compute", "POST", payload)
        ok("gate on: needs a key") if got == 401 else bad("gate on: needs a key", got)
        got, _ = http("/api/cii/compute?key=ck-definitely-wrong", "POST", payload)
        ok("gate on: rejects a bad key") if got == 401 else bad("gate on: rejects a bad key", got)
    finally:
        os.environ.pop("CARBONKEEL_REQUIRE_KEY", None)

    # abuse limits on unauthenticated routes
    got, _ = http("/api/claim", "POST", {"kind": "suppress", "imos": [str(9100000 + i) for i in range(21)],
                                          "contact_email": "a@b.co"})
    ok("claim form refuses 21 IMOs") if got == 422 else bad("claim form refuses 21 IMOs", got)
    got, _ = http("/api/score", "POST", {"imo": "1", "name": "x", "ship_type": "bulk_carrier", "dwt": 1e308,
                                          "year": 2026, "legs": [{"scope": "intra_eea", "distance_nm": 0, "fuel": {"hfo": 1}}]})
    ok("absurd numbers get a 422, not a 500") if got == 422 else bad("absurd numbers get a 422, not a 500", got)
    many9 = ",".join(str(1111111 + i) for i in range(9))
    got, _ = http(f"/api/pool-agreement?imos={many9}")
    ok("pool agreement capped like the fleet view") if got == 403 else bad("pool agreement capped like the fleet view", got)
    req = urllib.request.Request(BASE + "/app")
    with urllib.request.urlopen(req, timeout=30) as r:
        csp, hsts = r.headers.get("Content-Security-Policy", ""), r.headers.get("Strict-Transport-Security", "")
    ok("content security policy set") if "frame-ancestors 'none'" in csp and "default-src 'self'" in csp \
        else bad("content security policy set", csp)
    ok("HSTS set") if "max-age=" in hsts else bad("HSTS set", hsts)

    # anonymous fleet cap
    many = ",".join(str(1111111 + i) for i in range(12))
    got, _ = http(f"/api/fleet?imos={many}")
    ok("anonymous fleet cap") if got == 403 else bad("anonymous fleet cap", got)


# ------------------------------------------------------------ 3. content --
def check_customer_copy():
    for path, label in [(os.path.join(ROOT, "site", "index.html"), "landing"),
                        (os.path.join(ROOT, "api", "static", "index.html"), "app")]:
        html = open(path, encoding="utf-8").read()
        visible = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "", html, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", visible)
        if re.search(r"/api/\w+/\{", text):
            bad(f"{label}: raw API path template in customer copy")
        else:
            ok(f"{label}: no raw API paths in copy")
        # allowance and pool prices are the subject; our own pricing must not appear
        money = re.search(r"(subscription|per month|per vessel/month|our fees?\b|our pric(e|es|ing)\b|\bpricing\b)",
                          text, re.I)
        bad(f"{label}: service pricing language", money.group(0)) if money \
            else ok(f"{label}: no service-pricing language")
        for must in ["ESTIMATE", "Article 21"]:
            ok(f"{label}: states '{must}'") if must.lower() in text.lower() \
                else bad(f"{label}: missing '{must}'")


# ------------------------------------------------------- 4. hosting ------
def check_hosting_readiness():
    """Behaviours that are invisible on a laptop and break on a real host."""
    import tempfile

    # (a) behind a proxy every visitor shares the socket address; the real
    #     client must come from the RIGHT of X-Forwarded-For.
    from api import main as m

    class _Req:                                   # minimal stand-in
        def __init__(self, xff, peer="10.0.0.1"):
            self.headers = {"x-forwarded-for": xff} if xff else {}
            self.client = type("C", (), {"host": peer})()

    old = os.environ.get("CARBONKEEL_PROXY_HOPS")
    try:
        os.environ["CARBONKEEL_PROXY_HOPS"] = "0"
        ok("no proxy: socket address used") if m._client_key(_Req("1.1.1.1")) == "10.0.0.1"             else bad("no proxy: socket address used")
        os.environ["CARBONKEEL_PROXY_HOPS"] = "1"
        got = m._client_key(_Req("6.6.6.6, 203.0.113.9"))
        ok("1 proxy hop: rightmost X-Forwarded-For entry (cannot be forged)")             if got == "203.0.113.9" else bad("1 proxy hop uses rightmost entry", got)
        os.environ["CARBONKEEL_PROXY_HOPS"] = "2"
        got = m._client_key(_Req("203.0.113.9, 172.70.1.1"))
        ok("2 proxy hops: client is second from the right")             if got == "203.0.113.9" else bad("2 proxy hops", got)
        os.environ["CARBONKEEL_PROXY_HOPS"] = "1"
        got = m._client_key(_Req("", peer="10.0.0.1"))
        ok("missing header falls back safely") if got == "10.0.0.1"             else bad("missing header falls back safely", got)
    finally:
        if old is None:
            os.environ.pop("CARBONKEEL_PROXY_HOPS", None)
        else:
            os.environ["CARBONKEEL_PROXY_HOPS"] = old

    # (b) access keys and suppression must be supplyable by environment,
    #     because a free host wipes local files on every restart.
    from ghgcore import access, privacy
    os.environ["CARBONKEEL_ACCESS_KEYS"] = "ck-envtest1:Env partner, ck-envtest2"
    try:
        ok("env access key accepted") if access.is_valid("ck-envtest1")             else bad("env access key accepted")
        ok("env access key label kept") if access.label_for("ck-envtest1") == "Env partner"             else bad("env access key label kept")
        ok("unknown key still rejected") if not access.is_valid("ck-nope")             else bad("unknown key still rejected")
    finally:
        os.environ.pop("CARBONKEEL_ACCESS_KEYS", None)
    os.environ["CARBONKEEL_SUPPRESSED_IMOS"] = "9999991, 9999992 abc"
    try:
        ok("env suppression applies") if privacy.is_suppressed("9999991")             and privacy.is_suppressed("9999992") else bad("env suppression applies")
        ok("env suppression ignores junk") if not privacy.is_suppressed("abc")             else bad("env suppression ignores junk")
    finally:
        os.environ.pop("CARBONKEEL_SUPPRESSED_IMOS", None)
    ok("env suppression gone when unset") if not privacy.is_suppressed("9999991")         else bad("env suppression gone when unset")

    # (c) the register cache must survive a changed mtime (git clone/deploy).
    import glob
    from ghgcore.thetis import load_thetis_cached
    from ghgcore.exports import latest as _latest_export
    xlsx = _latest_export(os.path.join(ROOT, "fixtures"))
    load_thetis_cached(xlsx)                       # make sure a cache exists
    os.utime(xlsx, None)                           # what a fresh checkout does
    t0 = time.time()
    load_thetis_cached(xlsx)
    took = time.time() - t0
    ok(f"cache survives a touched file ({took:.2f}s)") if took < 4         else bad("cache survives a touched file", f"{took:.1f}s - reparsed")

    # (d) security headers on every response
    code, _ = http("/")
    import urllib.request
    with urllib.request.urlopen(BASE + "/healthz", timeout=30) as r:
        hdr = {k.lower(): v for k, v in r.headers.items()}
    for h, want in [("x-content-type-options", "nosniff"),
                    ("x-frame-options", "DENY"),
                    ("referrer-policy", None)]:
        if h in hdr and (want is None or hdr[h] == want):
            ok(f"header {h}")
        else:
            bad(f"header {h}", hdr.get(h))


# ---------------------------------------------------- 5. privacy notice ---
def check_privacy_notice():
    path = os.path.join(ROOT, "site", "privacy.html")
    if not os.path.exists(path):
        bad("site/privacy.html exists")
        return
    ok("site/privacy.html exists")
    page = open(path, encoding="utf-8").read()
    for needle, label in [("controller", "names the controller"),
                          ("hello@carbonkeel.com", "gives a contact address"),
                          ("right to", "states rights / complaint route"),
                          ("cookies", "states the cookie position")]:
        ok(f"notice {label}") if needle.lower() in page.lower()             else bad(f"notice {label}")
    for f, label in [("site/index.html", "landing"), ("api/static/index.html", "app")]:
        html = open(os.path.join(ROOT, f), encoding="utf-8").read()
        ok(f"{label} links the privacy notice") if ("privacy.html" in html or 'href="/privacy"' in html)             else bad(f"{label} links the privacy notice")
    # documents the Method / Your-data pages render must not leak API paths
    for doc in ["CALCULATION_NOTES.md", "DATA_AND_PRIVACY.md"]:
        txt = open(os.path.join(ROOT, "docs", doc), encoding="utf-8").read()
        ok(f"{doc}: no raw API paths") if "/api/" not in txt             else bad(f"{doc}: no raw API paths")


# ------------------------------------------------- 6. landing page ------
def check_landing_page():
    """The landing page quotes numbers from the register. They must come from
    data/market_stats.json (scripts/market_data.py), never be typed by hand,
    and the page must not call out to any third party."""
    import json
    html = open(os.path.join(ROOT, "site", "index.html"), encoding="utf-8").read()
    stats_path = os.path.join(ROOT, "data", "market_stats.json")
    if not os.path.exists(stats_path):
        bad("data/market_stats.json exists (run scripts/market_data.py)")
        return
    st = json.load(open(stats_path, encoding="utf-8"))
    want = {
        "ships": st["ships"],
        "companies": st["companies"],
        "ETS-scope CO2 (Mt)": st["ets_scope_co2_mt"],
        "annual cost at assumed allowance (bn EUR)": round(st["implied_ets_cost_eur_bn"][str(st["assumed_eua_eur"])], 1),
        "average cost per ship (k EUR)": round(st["avg_cost_per_ship_eur"] / 1000),
    }
    found = [float(x) for x in re.findall(r'data-count="([0-9.]+)"', html)]
    for label, val in want.items():
        ok(f"landing number matches register data: {label}") if float(val) in found             else bad(f"landing number matches register data: {label}", f"want {val}, page has {found}")
    ok(f"landing states the assumed allowance level (EUR {st['assumed_eua_eur']})")         if f"€{st['assumed_eua_eur']}" in html else bad("landing states the assumed allowance level")

    # privacy: nothing loads from anywhere else
    ext = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    ext = [u for u in ext if not u.startswith(("https://carbonkeel.com/", "https://app.carbonkeel.com"))]
    ok("landing makes no third-party requests") if not ext         else bad("landing makes no third-party requests", ext[:3])
    ok("landing loads no external CSS or fonts") if "url(http" not in html and "@import" not in html         else bad("landing loads no external CSS or fonts")

    # structure the nav and motion depend on
    for sid in ["hero", "how", "services", "best", "cost", "talk", "finale"]:
        ok(f"landing section #{sid} exists") if f'id="{sid}"' in html else bad(f"landing section #{sid} exists")
    for needle, why in [('id="seaHero"', "hero sea canvas"), ('id="seaNight"', "night sea canvas"),
                        ("window.__ckSea", "sea engine test seam"), ("IntersectionObserver", "sea pauses when off screen"),
                        ("document.hidden", "sea pauses in a hidden tab")]:
        ok(f"landing has the {why}") if needle in html else bad(f"landing has the {why}")
    ok("landing respects reduced-motion") if "prefers-reduced-motion" in html         else bad("landing respects reduced-motion")
    ok("landing motion has a safe fallback") if "motion disabled" in html         else bad("landing motion has a safe fallback")


def main():
    print("JavaScript parses")
    check_js_parses(os.path.join(ROOT, "site", "index.html"), "landing")
    check_js_parses(os.path.join(ROOT, "api", "static", "index.html"), "app")

    print("\nCustomer-facing copy")
    check_customer_copy()

    print("\nPrivacy notice")
    check_privacy_notice()

    print("\nLanding page")
    check_landing_page()

    print("\nHTTP endpoints")
    threading.Thread(target=serve, daemon=True).start()
    for _ in range(60):
        if http("/healthz")[0] == 200:
            break
        time.sleep(1)
    else:
        bad("server did not start on :8111")
    check_endpoints()

    print("\nHosting readiness")
    check_hosting_readiness()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + "; ".join(FAIL))
        sys.exit(1)
    print("Smoke test green.")


if __name__ == "__main__":
    main()
