"""Wording, style and data-source guards.

The engine tests prove the numbers and the smoke tests prove the pages work.
This suite protects what a reader actually sees, and the things that went
wrong on 5 Oct 2026: a placeholder ("year-Y") shown to users, an invalid font
declaration that shrank every button, an absolute accuracy claim, a wrong
Article 21 paragraph, and file ordering that would pick the wrong data version.

Run:  python tests/test_style.py        (starts its own server on :8113)
"""
import html as htmllib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

PASS, FAIL = [], []
PORT = 8113


def ok(name):
    PASS.append(name)
    print(f"  [ok]   {name}")


def bad(name, detail=""):
    FAIL.append(name)
    print(f"  [FAIL] {name}{(' - ' + str(detail)[:160]) if detail else ''}")


def check(cond, name, detail=""):
    ok(name) if cond else bad(name, detail)


def read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read().replace("\r\n", "\n")


# ---- text extraction ------------------------------------------------------
def visible_markup_text(src):
    s = re.sub(r"<script\b.*?</script>|<style\b.*?</style>|<!--.*?-->", " ", src, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return htmllib.unescape(s)


def script_prose(src):
    """Sentences the scripts build into the page."""
    out = []
    for sc in re.findall(r"<script>(.*?)</script>", src, re.S):
        for m in re.finditer(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"|`((?:[^`\\]|\\.)*)`", sc):
            t = m.group(1) or m.group(2) or m.group(3) or ""
            t = re.sub(r"\$\{[^}]*\}", " ", t)
            t = htmllib.unescape(re.sub(r"<[^>]+>", " ", t))
            if t.count(" ") >= 3 and not re.search(r"[;{}]|=>|\bconst\b|\bfunction\b|\blet\b", t):
                out.append(t)
    return "\n".join(out)


PAGES = [("site/index.html", "landing"), ("api/static/index.html", "app"), ("site/privacy.html", "privacy")]


def check_pages():
    for rel, label in PAGES:
        src = read(rel)
        # 1. invalid shorthand: 'inherit' is not allowed as a family inside font:, so the
        #    browser drops the whole declaration and the text falls back to 13px
        bad_font = re.findall(r"font:\s*\d{3}\s+[\d.]+px\s*/\s*[\d.]+\s+inherit|font:\s*[\d.]+px\s*/\s*[\d.]+\s+inherit", src)
        check(not bad_font, f"{label}: no invalid font shorthand", bad_font[:1])

        # numbers must not follow the visitor's own locale: an Indian-locale browser showed
        # "$3,66,599" next to "€510,798". Every toLocaleString call names a locale.
        bare = re.findall(r"toLocaleString\(\s*\)", src)
        check(not bare, f"{label}: numbers are formatted in one locale, not the visitor's", len(bare))

        text = visible_markup_text(src)
        prose = script_prose(src)
        both = text + "\n" + prose
        rules = [
            (r"\bregistry\b", "says 'registry' (it is a register, or the public record)"),
            (r"\bArt\. ?21", "writes 'Art. 21' (write Article 21)"),
            (r"EU-MRV", "writes 'EU-MRV' (write EU MRV)"),
            (r"→ ?PDF|\U0001F4A1", "uses an arrow or emoji where words are better"),
            (r"\s~\s?[€$\d]", "uses '~' for 'about'"),
            (r"replies same day", "missing 'the' in 'the same day'"),
            (r"Request failed:", "shows a raw error to the user"),
            (r"\bvs\.? ", "uses 'vs' in a sentence (write 'against')"),
        ]
        for pat, why in rules:
            m = re.search(pat, both)
            check(not m, f"{label}: no {why}", m.group(0) if m else "")

        # house style: 'ship', not 'vessel', in text a person reads
        m = re.search(r"\bvessels?\b", text, re.I)
        check(not m, f"{label}: markup says 'ship', not 'vessel'", text[max(0, m.start() - 30):m.end() + 20] if m else "")
        # typographic apostrophes in visible markup text
        m = re.search(r"[A-Za-z]'[A-Za-z]", text)
        check(not m, f"{label}: visible text uses typographic apostrophes", text[max(0, m.start() - 20):m.end() + 15] if m else "")

    # accuracy of what the headline numbers claim
    app = read("api/static/index.html")
    check("Carbon bill for ${year} emissions" in app and "This year" not in app.split("<script>")[1][:200000].replace("This year&rsquo;s", "THIS"),
          "app: the bill names the year of the emissions it covers")
    check("before the cost of the biofuel itself" in app and "before fuel costs" in app,
          "app: lever savings say they exclude the cost of the biofuel")
    # copy that quotes the verifier match must agree with the measured figures
    vm = json.load(open(os.path.join(ROOT, "data", "verifier_match.json"), encoding="utf-8"))
    check(0.62 <= vm["share_exact"] <= 0.72, "'about two ships in three' still describes the measured exact match", vm["share_exact"])
    check(0.70 <= vm["share_within_2pct"] <= 0.80, "'about three in four' still describes the measured match within 2%", vm["share_within_2pct"])
    for rel in ("site/index.html", "api/report.py"):
        t = re.sub(r"\s+", " ", read(rel))
        check("two ships in three" in t or "two in three" in t, f"{rel}: quotes the exact-match rate")
        check("three in four" in t, f"{rel}: quotes the within-2% rate")
        check("400-ship" not in t and "On 400 ships" not in t and "four in five" not in t, f"{rel}: no stale sample figures")
    for needle, why in [("From problem to action", "insight chain"), ("Observation", "observation step"), ("Expected value", "expected-value step"),
                        ("modelled, not measured", "before/after says it is modelled"), ("Top opportunities", "fleet opportunities")]:
        check(needle in app, f"app shows the {why}")
    check("could be saved with standard levers" not in app, "app: lever value is not presented as a net saving")

    # attribution that EMSA's copyright notice and CC BY-style reuse call for
    for rel, label in [("site/index.html", "landing"), ("api/static/index.html", "app")]:
        t = re.sub(r"\s+", " ", visible_markup_text(read(rel)))
        check("EMSA" in t and "not endorsed" in t, f"{label}: acknowledges EMSA and says it is not endorsed")


# ---- the server's own wording --------------------------------------------
def serve():
    import uvicorn
    from api.main import app
    uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")).run()


def http(path, want_json=True):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=120) as r:
            body = r.read().decode("utf-8")
            return r.status, (json.loads(body) if want_json else body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, body


def check_server_text():
    code, d = http("/api/lookup/0000000")
    msg = d.get("detail", "")
    check(code == 404 and "was not found in the public EU MRV register" in msg, "unknown IMO: plain message", msg)

    code, d = http("/api/search?q=VIKING%20R&limit=20")
    imo = next((x["imo"] for x in d.get("results", []) if not x["supported"]), None)
    if imo:
        code, d = http(f"/api/lookup/{imo}")
        msg = d.get("detail", "")
        check(code == 422 and "not yet supported" in msg and "'" not in msg and "Ship type “" in msg,
              "unsupported ship type: readable message, no Python quoting", msg)
    else:
        bad("found an unsupported ship type to test")

    year = 2026
    code, d = http(f"/api/calendar?year={year}")
    items = d["deadlines"]
    check(not any("year-Y" in x["what"] or "year Y" in x["what"] for x in items),
          "calendar: no 'year Y' placeholder reaches the user")
    check(not any("(compliance year" in x["what"] for x in items), "calendar: no repeated '(compliance year)' suffix")
    check(all(str(year) in x["what"] for x in items), "calendar: every item names its year")
    check(all("Art." not in x["basis"] and "Reg. (" not in x["basis"] for x in items),
          "calendar: legal bases are written out (Article, Regulation)")

    code, d = http("/api/lookup/9464663?dwt=50000")
    sc = d["scorecard"]
    prose = " ".join(sc["actions"] + [sc["future_readiness"]] + sc["fueleu"]["notes"] + [sc["fueleu"]["surplus_value_note"]]
                     + sc["ets"]["notes"] + sc["nzf"]["notes"] + sc["ukets"]["notes"])
    for pat, why in [(r"bank-borrow", "'bank-borrow'"), (r"\bSoC\b", "undefined 'SoC'"), (r"hedge", "trading advice ('hedge')"),
                     (r"~", "'~' for about"), (r"\bvessel", "'vessel'"), (r"uk_share", "an internal field name"),
                     (r"prototype", "'prototype'"), (r"\bT1\b|\bT2\b", "unexplained T1/T2")]:
        m = re.search(pat, prose)
        check(not m, f"engine text: no {why}", m.group(0) if m else "")
    check(any("Three years in a row at D" in a or "A rating of E requires" in a for a in sc["actions"]),
          "CII action states the rule once, without contradicting itself")

    # the landing page's worked example must be the engines' own numbers for IMO 9464663.
    # After a data refresh these change: this test then says which figures to update.
    code, base = http("/api/lookup/9464663")
    code, lev = http("/api/lookup/9464663?biofuel_pct=20&speed_pct=-10")
    ets0, feu0, ets1, feu1 = base["ets"], base["fueleu"], lev["ets"], lev["fueleu"]
    total0, total1 = ets0["cost_eur"] + feu0["penalty_eur"], ets1["cost_eur"] + feu1["penalty_eur"]
    fwd = total0 - ets0["cost_eur"] + ets0["cost_eur"] / ets0["surrender_share"]
    k = lambda v: f"€{round(v / 1000):,}k"
    land = re.sub(r"\s+", " ", visible_markup_text(read("site/index.html")))
    want = {"bill": k(total0), "ETS part": k(ets0["cost_eur"]), "FuelEU part": k(feu0["penalty_eur"]),
            "2026-rules bill": k(fwd), "after levers": k(total1), "value of levers": k(total0 - total1),
            "ETS share": f"{round(ets0['cost_eur'] / total0 * 100)}%", "reduction": f"−{round((total0 - total1) / total0 * 100)}%",
            "CO2e cut": f"{round((1 - ets1['co2e_in_scope_t'] / ets0['co2e_in_scope_t']) * 100)}%",
            "intensity": str(feu0["ghg_intensity"]), "target": str(feu0["target"])}
    for label, text in want.items():
        check(text in land, f"landing worked example matches the engines: {label} ({text})", "update site/index.html")

    code, m = http("/api/method", want_json=False)
    check("(225 checks)" in m and "220 checks" not in m, "method page quotes the real test count")
    vm = json.load(open(os.path.join(ROOT, "data", "verifier_match.json"), encoding="utf-8"))
    check("exactly on spot" not in m and f"{vm['share_exact'] * 100:.1f}%" in m,
          "method page states the measured match rate (data/verifier_match.json), not an absolute")
    check("400 ships" not in m and "400-ship" not in m, "method page no longer quotes the old sample")
    check("Art. 21(6)" not in m, "method page: no wrong Article 21(6)")
    code, pv = http("/api/privacy", want_json=False)
    check("21(6)" not in pv and "21(3)" in pv, "data page cites Article 21(3), not 21(6)")
    check("EEA port" not in pv, "data page does not misstate the scope as 'EEA port'")

    # --- EU ETS and UK ETS rules, through the API -----------------------------------------
    code, d = http("/api/lookup/9464663")
    e = d["ets"]
    check(e["basis"] == "verifier" and abs(e["co2e_in_scope_t"] - d["verified"]["ets_scope_co2_reported"]) < 0.06,
          "bill uses the verifier-reported ETS-scope CO2")
    check(d["verified"]["ets_scope_co2_rebuilt"] is not None, "our own rebuild is returned as a cross-check")
    check(e["surrender_by"] == "30 September 2026", "2025 emissions are surrendered by 30 September 2026", e["surrender_by"])
    code, x = http("/api/lookup/9464663?ice_class=true&derogation_pct=30")
    want = d["ets"]["allowances_due"] * 0.95 * 0.70
    check(abs(x["ets"]["allowances_due"] - want) < 0.5, "exceptions lower the allowances (ice class, 30% derogation)",
          f"{x['ets']['allowances_due']} vs {want}")
    check(len(x["ets"]["exceptions_applied"]) == 2, "the exceptions applied are listed")
    # a ship that reported no ETS-scope emissions is not charged
    code, sr = http("/api/search?q=a&limit=1")
    from ghgcore.exports import latest as _latest
    from ghgcore.thetis import load_thetis_cached as _load
    recs = _load(_latest(os.path.join(ROOT, "fixtures")))
    zero = next(r for r in recs.values() if r.co2_ets_reported_t == 0 and r.ship_type is not None
                and (r.co2_intra_t or 0) + (r.co2_departed_t or 0) > 0)
    code, z = http(f"/api/lookup/{zero.imo}")
    check(z["ets"]["cost_eur"] == 0 and any("below 5,000 GT" in n for n in z["ets"]["notes"]),
          "a ship that reported zero ETS-scope CO2 is not charged, and is told why")
    code, cal = http("/api/calendar?year=2026")
    uk = [x for x in cal["deadlines"] if x["regime"] == "UK ETS" and x["what"].startswith("Surrender")]
    check(len(uk) == 1 and uk[0]["due"] == "2028-04-30", "UK ETS surrender for 2026 is 30 April 2028", uk)
    code, cal25 = http("/api/calendar?year=2025")
    check(not any(x["regime"] == "UK ETS" for x in cal25["deadlines"]), "no UK ETS dates for 2025 (scheme starts 2026)")

    code, rep = http("/report?imos=9464663", want_json=False)
    check(code == 200 and "generated for outreach" not in rep, "printable report: no internal 'outreach' wording")
    check("spot-checks reproduce" not in rep and "two ships in three" in rep, "printable report: measured accuracy, not an absolute")
    check("not endorsed by EMSA" in rep and "Article 21" in rep, "printable report: attributes EMSA and disclaims endorsement")


# ---- data source tooling ---------------------------------------------------
def check_data_tools():
    from ghgcore.exports import latest, ordered
    d = tempfile.mkdtemp()
    for n in ["thetis_mrv_2025_v6.xlsx", "thetis_mrv_2025_v60.xlsx", "thetis_mrv_2025_v100.xlsx",
              "thetis_mrv_2024_v246.xlsx", "thetis_mrv_2025_v6.xlsx.pkl", "notes.xlsx"]:
        open(os.path.join(d, n), "w").close()
    names = [os.path.basename(p) for p in ordered(d)]
    check(os.path.basename(latest(d)) == "thetis_mrv_2025_v100.xlsx", "newest export is chosen by (year, version), not by text", names)
    check(sorted(os.listdir(d))[-1] != "thetis_mrv_2025_v100.xlsx", "(control) plain text sorting would have chosen wrongly")

    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "fetch_thetis.py"), "--download", "2025"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    check(r.returncode == 1 and "--yes" in r.stdout, "fetch tool refuses to download without --yes")

    ds = read("docs/DATA_SOURCES.md")
    check("21(3)" in ds and "mrv.emsa.europa.eu" in ds and "not endorsed" in ds,
          "DATA_SOURCES.md records the legal basis, the source and the attribution line")
    for rel in ["docs/DATA_AND_PRIVACY.md", "docs/LEGAL_REVIEW.md"]:
        t = read(rel)
        check("Article 21(6) alternative" not in t and "Art. 21(6)" not in t, f"{rel}: no wrong Article 21(6) citation")


def main():
    print("Pages: fonts, wording, attribution")
    check_pages()
    print("\nData tooling and sources")
    check_data_tools()
    print("\nServer wording")
    threading.Thread(target=serve, daemon=True).start()
    for _ in range(90):
        try:
            if http("/healthz")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        bad("server did not start on :%d" % PORT)
    check_server_text()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + "; ".join(FAIL))
        sys.exit(1)
    print("Style suite green.")


if __name__ == "__main__":
    main()
