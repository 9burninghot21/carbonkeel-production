"""Private visit-statistics page for the site owner (behind HTTP Basic auth in api/main.py)."""
import html
from datetime import datetime, timezone

COUNTRY = {"GB": "United Kingdom", "GR": "Greece", "DE": "Germany", "NL": "Netherlands", "NO": "Norway",
           "DK": "Denmark", "SG": "Singapore", "US": "United States", "IN": "India", "CY": "Cyprus",
           "FR": "France", "IT": "Italy", "ES": "Spain", "BE": "Belgium", "SE": "Sweden", "FI": "Finland",
           "CH": "Switzerland", "MT": "Malta", "TR": "Türkiye", "AE": "United Arab Emirates", "JP": "Japan",
           "KR": "South Korea", "CN": "China", "HK": "Hong Kong", "PL": "Poland", "PT": "Portugal",
           "IE": "Ireland", "MC": "Monaco", "CA": "Canada", "AU": "Australia", "": "Unknown"}
KIND = {"view": "Page views", "lookup": "Ships looked up", "lookup_dwt": "CII and EEXI checks (DWT added)",
        "fleet": "Ships in fleet analyses", "report": "Reports opened", "report_csv": "CSV downloads",
        "calculator": "Calculator runs", "contact_open": "Contact box opened", "contact_send": "Contact emails started",
        "email_click": "Email links clicked", "cta_latest": "Asked about this year's analysis",
        "operator_request": "Operator requests (claim, correct, hide)"}

CSS = """
*{box-sizing:border-box}body{font-family:'Segoe UI',system-ui,sans-serif;margin:0;background:#f3f8fd;color:#0b2545}
.wrap{max-width:1100px;margin:0 auto;padding:24px 18px 60px}h1{font-size:24px;margin:0}h2{font-size:16px;margin:28px 0 8px}
.sub{color:#46607e;font-size:13.5px;margin-top:4px}.tabs a{display:inline-block;margin:14px 6px 0 0;padding:7px 12px;border-radius:9px;
background:#fff;border:1px solid #c9d3dd;color:#0a5aa0;text-decoration:none;font-weight:600;font-size:13.5px}.tabs a.on{background:#0a5aa0;color:#fff}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:16px}
.kpi{background:#fff;border-radius:12px;padding:12px 14px;border:1px solid #dbe4ee}.kpi b{display:block;font-size:24px}
.kpi span{font-size:12px;color:#46607e}table{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;font-size:13.5px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid #edf1f6;vertical-align:top}th{background:#0b2545;color:#fff;font-size:12px}
td.n{text-align:right;font-variant-numeric:tabular-nums}.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:760px){.cols{grid-template-columns:1fr}}.note{font-size:12px;color:#586f8c;margin-top:8px}
.btn{display:inline-block;padding:8px 12px;border-radius:9px;background:#fff;border:1px solid #0a5aa0;color:#0a5aa0;font-weight:700;
font-size:13px;cursor:pointer;text-decoration:none;margin:12px 8px 0 0}svg{background:#fff;border-radius:12px;border:1px solid #dbe4ee}
"""


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _table(head, rows) -> str:
    if not rows:
        return "<p class=note>Nothing yet.</p>"
    th = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td class={'n' if isinstance(v, (int, float)) else ''}>{_e(v)}</td>" for v in r) + "</tr>"
                   for r in rows)
    return f"<table><tr>{th}</tr>{body}</table>"


def _chart(daily) -> str:
    if not daily:
        return ""
    W, H, pad = 1000, 170, 26
    mx = max([d[1] or 0 for d in daily] + [1])
    bw = (W - 2 * pad) / len(daily)
    bars = []
    for i, (day, visitors, views, lookups) in enumerate(daily):
        h = (visitors or 0) / mx * (H - 2 * pad)
        x = pad + i * bw
        bars.append(f'<rect x="{x + 1:.1f}" y="{H - pad - h:.1f}" width="{max(1, bw - 2):.1f}" height="{h:.1f}" fill="#0a6fb7">'
                    f'<title>{_e(day)}: {visitors} visitors, {views or 0} page views, {lookups or 0} lookups</title></rect>')
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Visitors per day">{"".join(bars)}'
            f'<text x="{pad}" y="{H - 8}" font-size="11" fill="#46607e">{_e(daily[0][0])}</text>'
            f'<text x="{W - pad}" y="{H - 8}" font-size="11" fill="#46607e" text-anchor="end">{_e(daily[-1][0])}</text>'
            f'<text x="{pad}" y="16" font-size="11" fill="#46607e">most in a day: {mx}</text></svg>')


def dashboard_html(s: dict) -> str:
    t = s["totals"]
    kp = [("Visitors", s["visitors"])] + [(KIND[k], t.get(k, 0)) for k in
                                          ("view", "lookup", "lookup_dwt", "fleet", "report", "calculator", "contact_send", "cta_latest")]
    kpis = "".join(f"<div class=kpi><b>{n:,}</b><span>{_e(label)}</span></div>" for label, n in kp)
    tabs = "".join(f'<a class="{"on" if s["days"] == d else ""}" href="?days={d}">Last {d} days</a>' for d in (7, 30, 90, 365))
    when = lambda ts: datetime.fromtimestamp(ts, timezone.utc).strftime("%d %b %H:%M")
    leads = [(c, n, ships, ", ".join(COUNTRY.get(x, x) for x in (cs or "").split(",") if x is not None), when(last),
              (names or "")[:160]) for c, n, ships, cs, last, names in s["leads"]]
    recent = [(when(ts), KIND.get(k, k), COUNTRY.get(cc, cc), ship or "", company or "", detail or "", ref or "")
              for ts, k, cc, ship, company, detail, ref in s["recent"]]
    countries = [(COUNTRY.get(c, c), n) for c, n in s["countries"]]
    return f"""<!DOCTYPE html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width, initial-scale=1">
<meta name=robots content="noindex, nofollow"><title>CarbonKeel — visit statistics</title><style>{CSS}</style></head><body><div class=wrap>
<h1>Visit statistics</h1><div class=sub>Private to you. Since {_e(s["since"])} (UTC). No cookies; visitor IP addresses are never stored.</div>
<div class=tabs>{tabs}</div>
<div class=kpis>{kpis}</div>
<h2>Visitors per day</h2>{_chart(s["daily"])}
<h2>Companies whose ships were looked up: your outreach list</h2>
{_table(["Company", "Actions", "Ships", "Visitor countries", "Last seen (UTC)", "Ships looked up"], leads)}
<a class=btn href="/admin/analytics/leads.csv?days={s["days"]}">Download this list as CSV</a>
<p class=note>A company appears here when someone looked up, analysed or downloaded a report on one of its ships. It shows interest
in that fleet; it does not tell you who the visitor was. Visitor countries help you judge whether the interest came from the company's own office.</p>
<div class=cols><div><h2>Where visitors are</h2>{_table(["Country", "Visitors"], countries)}</div>
<div><h2>Where they came from</h2>{_table(["Website", "Visits"], s["referrers"])}
<h2>Your campaign links</h2>{_table(["utm_source", "utm_medium", "utm_campaign", "Visits"], s["campaigns"])}
<p class=note>Add tags to links you send, for example carbonkeel.com/?utm_source=linkedin&amp;utm_campaign=oct-outreach, to see which outreach brings visits.</p></div></div>
<div class=cols><div><h2>Pages</h2>{_table(["Page", "Views"], s["pages"])}</div><div><h2>Devices</h2>{_table(["Device", "Visitors"], s["devices"])}</div></div>
<h2>Latest actions</h2>{_table(["When (UTC)", "What", "Country", "Ship", "Company", "Detail", "Came from"], recent)}
<h2>Your own visits</h2><p class=note id=self></p>
<button class=btn type=button onclick="setSelf(true)">Don't count this browser</button>
<button class=btn type=button onclick="setSelf(false)">Count this browser again</button>
<p class=note>Country lookups use IP geolocation by <a href="https://db-ip.com">DB-IP</a> (CC BY 4.0).</p>
<script>
function show(){{var on=false;try{{on=localStorage.getItem('ck_nostats')==='1'}}catch(e){{}}
document.getElementById('self').textContent=on?'This browser is not counted.':'This browser is counted. Click below so your own testing does not show up.';}}
function setSelf(on){{try{{on?localStorage.setItem('ck_nostats','1'):localStorage.removeItem('ck_nostats')}}catch(e){{}}show();}}
show();
</script></div></body></html>"""
