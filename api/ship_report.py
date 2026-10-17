"""Single-ship report: one printable page (browser print -> PDF) and the same content as CSV.

Built from the dict `ship_result` returns, so the report can never disagree with the screen.
"""
import csv
import html
import io
import re
from datetime import datetime, timezone

from ghgcore.nzf import NZF_STATUS
from .report import CSS

LEGAL_REFERENCES = [
    ("EU ETS scope and shares", "Directive 2003/87/EC, Art. 3ga: 100% of emissions on voyages between "
     "EU/EEA ports and at berth, 50% on voyages into or out of the EU/EEA."),
    ("EU ETS phase-in", "Directive 2003/87/EC, Art. 3gb: 40% of 2024 emissions, 70% of 2025, 100% from 2026."),
    ("EU ETS surrender", "Directive 2003/87/EC, Art. 12(3): by 30 September of the following year; "
     "Art. 16(3): EUR 100 per tCO2e excess-emissions penalty, allowances still owed."),
    ("EU ETS gases", "Directive 2003/87/EC, Annex I: methane and nitrous oxide from 1 January 2026; "
     "GWP 28 and 265 (Delegated Regulation (EU) 2020/1044)."),
    ("EU ETS exceptions", "Directive 2003/87/EC, Art. 12(3-b) to (3-e), until 31 December 2030."),
    ("Monitoring formula", "Regulation (EU) 2015/757, Annex I Part A, as amended by Delegated Regulation "
     "(EU) 2023/2776."),
    ("UK ETS", "SI 2026/392, Schedule 2A: paras 5 (ships), 7 (voyages), 15 (surrender: 50% Great Britain "
     "to Northern Ireland, 100% otherwise; 2026 emissions due 30 April 2028)."),
    ("FuelEU targets and defaults", "Regulation (EU) 2023/1805, Art. 4 and Annex I (targets from the "
     "91.16 gCO2e/MJ baseline), Annex II (default fuel values)."),
    ("FuelEU flexibility", "Regulation (EU) 2023/1805, Art. 20 (banking and borrowing), Art. 21 (pooling)."),
    ("FuelEU penalty", "Regulation (EU) 2023/1805, Art. 23 and Annex IV Part B: |CB| / (GHGIE x 41,000) "
     "x EUR 2,400; Art. 23(2): x (1 + (n - 1)/10) for consecutive deficit periods."),
    ("CII", "MARPOL Annex VI, reg. 28; MEPC.352(78) G1, MEPC.353(78) G2, MEPC.338(76) as amended by "
     "MEPC.400(83) G3, MEPC.354(78) G4, MEPC.355(78) G5."),
    ("EEXI", "MARPOL Annex VI, regs. 23 and 25; capacity per MEPC.364(79)."),
    ("Charter split", "BIMCO ETS Allowances Clause for Time Charter Parties 2022; BIMCO FuelEU Maritime "
     "Clause for Time Charter Parties 2024."),
    ("IMO Net-Zero Framework", "Draft MARPOL Annex VI Chapter 5 as approved at MEPC 83. " + NZF_STATUS),
    ("Source data", "EMSA THETIS-MRV public data, published under Art. 21 of Regulation (EU) 2015/757."),
]

SHIP_CSS = CSS + """
.wrap h2{border-bottom:1px solid #e2e8f0;padding-bottom:4px}
table.kv td{text-align:left;white-space:normal}
table.kv td:first-child{color:#475569;width:44%}
ol.refs{font-size:11.5px;color:#334155;line-height:1.55;padding-left:18px}
.btns{margin:16px 36px 0;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.btns button{font:700 14px 'Segoe UI',sans-serif;padding:10px 16px;border-radius:9px;
 border:0;background:#0a5aa0;color:#fff;cursor:pointer}
.btns a{font-size:14px;color:#0a5aa0;font-weight:600}
@media print{.btns{display:none}h2{break-after:avoid}table{break-inside:avoid}}
@media(max-width:600px){.head,.wrap{padding-left:16px;padding-right:16px}.band,.btns{margin-left:16px}}
"""


def _source(name: str) -> str:
    m = re.search(r"(\d{4})_v(\d+)", name or "")
    return f"EMSA THETIS-MRV, {m.group(1)} report, version {m.group(2)}" if m else "EMSA THETIS-MRV"


def _t(x, unit="t") -> str:
    return "—" if x is None else f"{x:,.1f} {unit}"


def _eur(x) -> str:
    return "—" if x is None else f"EUR {x:,.0f}"


def _parts(r: dict):
    full = "scorecard" in r
    sc = r.get("scorecard") or {}
    pick = (lambda k: sc[k]) if full else (lambda k: r[k])
    name = sc.get("vessel_name") if full else r["vessel_name"]
    imo = sc.get("imo_number") if full else r["imo"]
    return full, sc, pick("ets"), pick("ukets"), pick("fueleu"), pick("nzf"), name, imo


def sections(r: dict) -> list[tuple[str, list[tuple[str, str]]]]:
    """(title, [(label, value)]) for every block of the report."""
    full, sc, ets, uk, feu, nzf, name, imo = _parts(r)
    bill, a = r["bill"], r["assumptions"]
    out = [
        ("Ship", [("Name", name), ("IMO number", imo), ("Ship type", r.get("ship_type") or "—"),
                  ("Company (Document of Compliance holder)", r.get("company") or "—"),
                  ("Emissions year", str(bill["year"])),
                  ("Data", _source(r["source"])),
                  ("Status", "ESTIMATE rebuilt from public data"
                   + (" — what-if scenario, not the ship's own position" if r["scenario"] else ""))]),
        ("Carbon bill", [("EU ETS", _eur(bill["ets_eur"])), ("UK ETS", _eur(bill["ukets_eur"])),
                         ("FuelEU, statutory penalty", _eur(bill["fueleu_penalty_eur"])),
                         ("FuelEU, deficit bought from a pool", _eur(bill["fueleu_pooled_eur"])),
                         ("Total, FuelEU at the penalty", _eur(bill["total_penalty_eur"])),
                         ("Total, FuelEU pooled", _eur(bill["total_pooled_eur"]))]),
    ]
    ss = r.get("scope_split")
    if ss:
        out.append(("Where the emissions fall (from the register)",
                    [(row["label"], f"{row['co2_t']:,.1f} t CO2 x {row['share'] * 100:.0f}% = "
                                    f"{row['counted_t']:,.1f} t counted") for row in ss["rows"]]
                    + [("Our rebuild of ETS-scope CO2", _t(ss["rebuilt_t"])),
                       ("Verifier-reported ETS-scope CO2", _t(ss["reported_t"]))]))
    out += [
        ("EU ETS", [("ETS-scope CO2e the bill uses", _t(ets["co2e_in_scope_t"])),
                    ("Basis", "verifier-reported figure" if ets["basis"] == "verifier" else "our rebuild"),
                    ("Share surrendered (phase-in)", f"{ets['surrender_share'] * 100:.0f}%"),
                    ("Allowances due", f"{ets['allowances_due']:,.1f} EUAs"),
                    ("Allowance price assumed", f"EUR {ets['eua_price_used']:,.2f}"),
                    ("Exceptions applied", "; ".join(ets.get("exceptions_applied") or []) or "none"),
                    ("Surrender by", ets.get("surrender_by") or "—")]),
        ("UK ETS", [("CO2e in scope", _t(uk["co2e_in_scope_t"])),
                    ("Cost", f"GBP {uk['cost_gbp']:,.0f} at GBP {uk['uka_price_used']:,.2f}"),
                    ("Visible in this data", "yes" if uk.get("data_observable", True) else
                     "no — the EU register does not contain UK domestic voyages")]),
        ("FuelEU Maritime", [("Applies", "yes" if feu.get("applicable", True) else "no — " + feu["surplus_value_note"]),
                             ("GHG intensity (well-to-wake)", f"{feu['ghg_intensity']} gCO2e/MJ"),
                             ("Target", f"{feu['target']} gCO2e/MJ"),
                             ("Compliance balance", _t(feu["compliance_balance_tco2e"], "tCO2e")),
                             ("Penalty multiplier, Art. 23(2)", f"{feu.get('penalty_multiplier', 1):g}"),
                             ("Statutory penalty per tCO2e", f"EUR {feu.get('penalty_eur_per_tco2e', 0):,.2f}"),
                             ("Statutory penalty", _eur(feu["penalty_eur"])),
                             ("Pool price assumed", "—" if feu.get("pool_price_eur_per_tco2e") is None
                              else f"EUR {feu['pool_price_eur_per_tco2e']:,.2f} per tCO2e"),
                             ("Cost if pooled", _eur(feu.get("pooling_cost_eur")))]),
    ]
    if full:
        c = sc["cii"]
        out.append(("CII rating", [("Rating", c["rating"]),
                                   ("Attained", f"{c['attained']} gCO2 per capacity-nm"),
                                   ("Required", f"{c['required']} (Z = {c['z_factor_pct']}%)"),
                                   ("Ratio attained / required", str(c["ratio"])),
                                   ("Rating boundaries", " · ".join(
                                       f"{k} ≤ {x}" for k, x in (c.get("boundaries") or {}).items()))]))
        x = r.get("eexi")
        if x:
            out.append(("EEXI", [("Verdict", x["verdict"]),
                                 ("Attained", f"{x['attained']} ({x['attained_basis']})"),
                                 ("Required", str(x["required"])),
                                 ("Margin", "—" if x["margin_pct"] is None else f"{x['margin_pct']}%")]))
    out.append(("IMO Net-Zero Framework (scenario)",
                [("Scenario year", str(nzf["year"])), ("Attained GFI", f"{nzf['attained_gfi']} gCO2e/MJ"),
                 ("Remedial units", f"USD {nzf['remedial_cost_usd']:,.0f}"), ("Status", NZF_STATUS)]))
    ch = r.get("charter")
    if ch:
        out.append(("Owner and time-charterer split",
                    [("Charter period", f"{ch['charter_from']} to {ch['charter_to']}"),
                     ("Charterer share", f"{ch['charterer_share'] * 100:.1f}%")]
                    + [(ln["item"], f"charterer EUR {ln['charterer_eur']:,.0f} · owner EUR {ln['owner_eur']:,.0f}")
                       for ln in ch["lines"]]
                    + [("Total", f"charterer EUR {ch['total_charterer_eur']:,.0f} · "
                                 f"owner EUR {ch['total_owner_eur']:,.0f}"),
                       ("Method", " ".join(ch["notes"][1:]))]))
    out.append(("Assumptions", [("EU allowance price", f"EUR {a['eua_price_eur']:,.2f} per tonne"),
                                ("UK allowance price", f"GBP {a['uka_price_gbp']:,.2f} per tonne"),
                                ("Pounds to euros", str(a["eur_per_gbp"])),
                                ("FuelEU pool price", f"EUR {a['pool_price_eur_per_tco2e']:,.2f} per tCO2e"),
                                ("Fuel mix", r.get("fuel_mix") or "Inferred from the register's CO2 ÷ fuel"),
                                ("Distance", "Worked out from the filed CO2 per nautical mile"),
                                ("Market levels last checked", a["checked"])]))
    return out


def ship_report_html(r: dict, csv_href: str) -> str:
    secs = sections(r)
    body = "".join(
        f"<h2>{html.escape(title)}</h2><table class=kv>"
        + "".join(f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>" for k, v in pairs)
        + "</table>" for title, pairs in secs)
    refs = "".join(f"<li><b>{html.escape(k)}.</b> {html.escape(v)}</li>" for k, v in LEGAL_REFERENCES)
    name = secs[0][1][0][1]
    stamp = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    return f"""<!DOCTYPE html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1"><meta name=robots content="noindex, nofollow">
<title>CarbonKeel report — {html.escape(str(name))}</title><style>{SHIP_CSS}</style></head><body>
<div class=head><div class=logo>Carbon<span>Keel</span></div>
<div class=sub>Single-ship carbon position · generated {stamp}</div></div>
<div class=btns><button type=button onclick="window.print()">Print or save as PDF</button>
<a href="{html.escape(csv_href)}">Download as CSV</a><a href="/app">Back to CarbonKeel</a></div>
<span class=band>ESTIMATE: rebuilt from the verified emissions EMSA publishes. Not a verifier's statement.</span>
<div class=wrap>{body}
<h2>Legal references</h2><ol class=refs>{refs}</ol>
<p class=note>CarbonKeel is independent and is not an
accredited MRV or FuelEU verifier: allowances are surrendered, and FuelEU balances settled, on your
verifier's figures. This report is for planning and is not legal, tax or investment advice. Contains
data from EMSA THETIS-MRV; CarbonKeel's calculations are its own and are not endorsed by EMSA or the
European Commission. Full method: carbonkeel.com/app#method.</p>
</div></body></html>"""


def _cell(v) -> str:
    """Stop a spreadsheet reading a ship name (or any text) as a formula."""
    s = str(v)
    if s[:1] in ("=", "+", "@", "\t", "\r") or (s[:1] == "-" and not s[1:2].isdigit()):
        return "'" + s
    return s


def ship_report_csv(r: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["section", "item", "value"])
    for title, pairs in sections(r):
        for k, v in pairs:
            w.writerow([_cell(title), _cell(k), _cell(v)])
    for k, v in LEGAL_REFERENCES:
        w.writerow(["Legal references", k, v])
    return buf.getvalue()
