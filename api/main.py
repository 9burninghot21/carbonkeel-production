"""CarbonKeel API — free-lookup funnel + owner-data scoring.

Run:  python -m uvicorn api.main:app --reload   (from repo root)
Then open http://127.0.0.1:8000  (landing page; the app is at /app)

Endpoints:
  GET  /api/search?q=NAME        find ships in the public THETIS-MRV export
  GET  /api/lookup/{imo}?dwt=N   ESTIMATE scorecard from public data
  POST /api/calc                 owner-data CII + carbon bill from the operator's own figures
  POST /api/score                full scorecard from owner-supplied activity
  GET  /report/ship/{imo}        printable single-ship report (save as PDF); .csv for a spreadsheet
"""
import os
import sys
import threading
from dataclasses import asdict
from datetime import date
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ghgcore import (Vessel, AnnualActivity, VoyageLeg, FuelConsumption,
                     FuelType, ShipType, VoyageScope, build_scorecard)
from ghgcore.thetis import load_thetis_cached, record_to_activity
from ghgcore.exports import ordered as _ordered_exports
from ghgcore.fueleu import compute_fueleu
from ghgcore.euets import compute_ets
from ghgcore.ukets import compute_ukets
from ghgcore.nzf import compute_nzf
from ghgcore.whatif import apply_whatif
from ghgcore.assumptions import (DEFAULT_EUA_PRICE_EUR, DEFAULT_UKA_PRICE_GBP, DEFAULT_EUR_PER_GBP,
                                 DEFAULT_POOL_PRICE_EUR_PER_TCO2E, assumptions_block)
from ghgcore import privacy

app = FastAPI(title="CarbonKeel", version="0.3.0")

SITE_DIR = os.path.join(os.path.dirname(__file__), "..", "site")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _client_key(request: Optional[Request]) -> str:
    """Who is this visitor, for rate limiting?

    Behind a hosting proxy (Render, Cloudflare) the socket peer is the proxy,
    so keying on it would put EVERY visitor in one bucket and lock the whole
    site out after ~120 lookups. CARBONKEEL_PROXY_HOPS says how many trusted
    proxies sit in front of us; the real client is then that many entries from
    the RIGHT of X-Forwarded-For (the right-hand entries are the ones our own
    proxies appended — anything further left can be forged by the visitor).
    Unset/0 means "no proxy": use the socket address, correct for local use.
    """
    if request is None or request.client is None:
        return "unknown"
    try:
        hops = int(os.environ.get("CARBONKEEL_PROXY_HOPS", "0") or 0)
    except ValueError:
        hops = 0
    if hops > 0:
        parts = [p.strip() for p in
                 request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host


def _guard(request: Optional[Request], cost: int = 1) -> None:
    """Anonymous rate limit. Harvesting the register is the behaviour that
    would harm the operators we sell to — a single honest lookup is not."""
    key = _client_key(request)
    for _ in range(max(1, cost)):
        if not privacy.rate_limit_ok(key):
            raise HTTPException(429, "You have reached the hourly limit for anonymous "
                                     "lookups. If you operate these ships, claim them "
                                     "under “Your data” for full access.")


def _suppressed_payload(rec) -> dict:
    """Public EMSA facts only, for a vessel whose operator opted out of our
    derived figures. We never hide the Art. 21 data itself — it is public by
    law and one click away at the source."""
    return {
        "suppressed": True,
        "note": privacy.SUPPRESSION_NOTE,
        "imo": rec.imo, "vessel_name": rec.name,
        "ship_type": rec.ship_type_raw,
        "source": _EXPORT_NAME,
        "verified": {"co2_tonnes": rec.co2_tonnes,
                     "fuel_tonnes": rec.fuel_tonnes,
                     "tech_efficiency": rec.tech_efficiency},
    }

_RECORDS: Optional[dict] = None
_EXPORT_NAME = ""


_LOAD_LOCK = threading.Lock()


def records() -> dict:
    """Load the newest THETIS export once per process (thread-safe)."""
    global _RECORDS, _EXPORT_NAME
    if _RECORDS is None:
        with _LOAD_LOCK:
            if _RECORDS is None:
                fx = os.path.join(os.path.dirname(__file__), "..", "fixtures")
                files = _ordered_exports(fx)
                if not files:
                    raise HTTPException(503, "The ship register is not available right now. "
                                             "Please try again shortly.")
                _EXPORT_NAME = os.path.basename(files[-1])
                _RECORDS = load_thetis_cached(files[-1])
    return _RECORDS


def _warm() -> None:
    """Load the register in the background at startup so the first visitor
    does not pay for it. /healthz answers immediately either way."""
    try:
        records()
    except Exception:                                     # noqa: BLE001
        pass


threading.Thread(target=_warm, daemon=True, name="warm-register").start()


# Nothing loads from another site; pages may not be framed; forms post only to us.
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
       "base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


@app.middleware("http")
async def _security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Permissions-Policy",
                            "camera=(), microphone=(), geolocation=()")
    resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    resp.headers.setdefault("Content-Security-Policy", CSP)
    return resp


def _unsupported(raw):
    """Message for a ship type we do not cover yet. The page looks for the
    phrase 'not yet supported' to offer the custom EEXI check instead."""
    return (f"Ship type “{raw}” is not yet supported. We cover 12 ship types, "
            "including container ships, bulk carriers, tankers, LNG carriers, "
            "ro-ro, ro-pax and cruise ships.")


@app.get("/")
def index():
    return FileResponse(os.path.join(SITE_DIR, "index.html"),
                        headers={"Cache-Control": "no-cache"})


@app.get("/app")
def app_page():
    # no-store: a cached app shell silently hides new features and breaks calls.
    return FileResponse(os.path.join(STATIC_DIR, "index.html"),
                        headers={"Cache-Control": "no-store, must-revalidate"})


@app.get("/privacy")
def privacy_page():
    return FileResponse(os.path.join(SITE_DIR, "privacy.html"),
                        headers={"Cache-Control": "no-cache"})


@app.get("/api/search")
def search(request: Request, q: str = Query(min_length=3, max_length=100), limit: int = 20):
    # Search fires on every keystroke (debounced), so it needs a far larger
    # budget than a lookup — but not an unlimited one, or it becomes the way
    # around the harvesting cap: ~20 names per call, 16,673 ships.
    if not privacy.rate_limit_ok(_client_key(request) + ":search", limit=900):
        raise HTTPException(429, "Too many searches this hour. Please try again later.")
    limit = max(1, min(limit, 20))
    recs = records()
    ql = q.upper()
    hits = [r for r in recs.values() if ql in r.name.upper() or q == r.imo]
    return {"source": _EXPORT_NAME, "count": len(hits),
            "results": [{"imo": r.imo, "name": r.name, "ship_type": r.ship_type_raw,
                         "co2_tonnes": r.co2_tonnes,
                         "supported": r.ship_type is not None}
                        for r in hits[:limit]]}


def _parse_day(s: Optional[str], what: str) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s.strip())
    except ValueError:
        raise HTTPException(422, f"The {what} date must look like 2026-03-31.")


def _scope_rows(rec) -> Optional[dict]:
    """The register's own scope split, with the share each scope counts for in the EU ETS
    and FuelEU (Directive Art. 3ga): this is why the bill is not simply total CO2 x price."""
    if rec.co2_intra_t is None:
        return None
    intra, dep = rec.co2_intra_t or 0.0, rec.co2_departed_t or 0.0
    arr, berth = rec.co2_arrived_t or 0.0, rec.co2_berth_t or 0.0
    outside = max(0.0, (rec.co2_tonnes or 0.0) - intra - dep - arr - berth)
    rows = [("Voyages between EU/EEA ports", intra, 1.0),
            ("Voyages leaving an EU/EEA port", dep, 0.5),
            ("Voyages arriving at an EU/EEA port", arr, 0.5),
            ("At berth in EU/EEA ports", berth, 1.0),
            ("Outside EU/EEA scope", outside, 0.0)]
    from ghgcore.thetis import rebuilt_ets_co2
    return {"rows": [{"label": l, "co2_t": round(t, 1), "share": s, "counted_t": round(t * s, 1)}
                     for l, t, s in rows],
            "rebuilt_t": round(rebuilt_ets_co2(rec) or 0.0, 1),
            "reported_t": rec.co2_ets_reported_t}


def ship_result(rec, *, dwt=None, year=None, biofuel_pct=0.0, speed_pct=0.0, speed_exp=3.0,
                aux_pct=0.0, ice_class=False, derogation_pct=0.0,
                eua=DEFAULT_EUA_PRICE_EUR, uka=DEFAULT_UKA_PRICE_GBP, fx=DEFAULT_EUR_PER_GBP,
                pool=DEFAULT_POOL_PRICE_EUR_PER_TCO2E, deficit_years=1,
                charter_from=None, charter_to=None, charter_pct=None,
                fueleu_basis="penalty") -> dict:
    """Everything the lookup, the printable report and the CSV show for one ship."""
    from ghgcore.ets_rules import ETSExceptions
    from ghgcore.thetis import rebuilt_ets_co2
    from ghgcore.ets_combined import compute_ets_combined
    y = year or rec.reporting_period or 2025
    eu_exc = ETSExceptions(ice_class, derogation_pct / 100.0)
    verified = {"co2_tonnes": rec.co2_tonnes, "fuel_tonnes": rec.fuel_tonnes,
                "ets_scope_co2_reported": rec.co2_ets_reported_t,
                "ets_scope_co2_rebuilt": rebuilt_ets_co2(rec),
                "est_distance_nm": rec.est_distance_nm,
                "tech_efficiency": rec.tech_efficiency}
    scenario = bool(biofuel_pct or speed_pct)

    def transform(act):
        return apply_whatif(act, biofuel_pct, speed_pct, speed_exp, aux_pct) if scenario else act

    out = {"estimate": True, "scenario": scenario, "source": _EXPORT_NAME, "verified": verified,
           "scope_split": _scope_rows(rec), "assumptions": assumptions_block(eua, uka, fx, pool),
           "company": rec.company, "ship_type": rec.ship_type_raw}
    if dwt:
        sc = build_scorecard(transform(record_to_activity(rec, year=y, dwt=dwt)), eua_price=eua,
                             uka_price_gbp=uka, eur_per_gbp=fx, eu_exceptions=eu_exc,
                             pool_price=pool, consecutive_deficit_years=deficit_years)
        ets, ukets, feu = sc.ets, sc.ukets, sc.fueleu
        out["scorecard"] = asdict(sc)
        from ghgcore.eexi import compute_eexi
        out["eexi"] = asdict(compute_eexi(rec.ship_type, dwt, dwt, rec.tech_efficiency))
    else:
        act = transform(record_to_activity(rec, year=y, dwt=1.0))
        both = compute_ets_combined(act, eua, uka, fx, eu_exc)
        ets, ukets = both.eu, both.uk
        feu = compute_fueleu(act, consecutive_deficit_years=deficit_years, pool_price_eur_per_tco2e=pool)
        nzf = compute_nzf(act)
        out.update({"partial": True, "vessel_name": rec.name, "imo": rec.imo, "year": y,
                    "ets": asdict(ets), "ukets": asdict(ukets), "fueleu": asdict(feu),
                    "nzf": asdict(nzf)})
    uk_eur = ukets.cost_gbp * fx
    feu_pool = feu.pooling_cost_eur if feu.pooling_cost_eur is not None else feu.penalty_eur
    feu_used = feu_pool if fueleu_basis == "pool" else feu.penalty_eur
    out["bill"] = {"year": y, "ets_eur": ets.cost_eur, "ukets_eur": round(uk_eur, 0),
                   "fueleu_penalty_eur": feu.penalty_eur, "fueleu_pooled_eur": feu_pool,
                   "fueleu_basis": fueleu_basis, "fueleu_eur": feu_used,
                   "total_eur": round(ets.cost_eur + uk_eur + feu_used, 0),
                   "total_penalty_eur": round(ets.cost_eur + uk_eur + feu.penalty_eur, 0),
                   "total_pooled_eur": round(ets.cost_eur + uk_eur + feu_pool, 0)}
    start, end = _parse_day(charter_from, "charter start"), _parse_day(charter_to, "charter end")
    if start and end:
        from ghgcore.charter import split
        items = {"EU ETS allowances": ets.cost_eur}
        if uk_eur > 0:
            items["UK ETS allowances"] = uk_eur
        if feu_used > 0:
            items["FuelEU deficit (" + ("pooled" if fueleu_basis == "pool" else "statutory penalty") + ")"] = feu_used
        try:
            cs = split(y, start, end, items, None if charter_pct is None else charter_pct / 100.0)
        except ValueError as e:
            raise HTTPException(422, str(e))
        out["charter"] = asdict(cs)
    elif start or end:
        raise HTTPException(422, "Give both the charter start and end dates.")
    return out


@app.get("/api/lookup/{imo}")
def lookup(imo: str, request: Request = None,
           dwt: Optional[float] = Query(None, gt=0),
           year: Optional[int] = Query(None, ge=2018, le=2035),
           biofuel_pct: float = Query(0, ge=0, le=100),
           speed_pct: float = Query(0, ge=-30, le=20),
           speed_exp: float = Query(3.0, ge=2.0, le=4.5),
           aux_pct: float = Query(0, ge=0, le=100),
           ice_class: bool = False,
           derogation_pct: float = Query(0, ge=0, le=100),
           eua_price: float = Query(DEFAULT_EUA_PRICE_EUR, gt=0, le=500),
           uka_price: float = Query(DEFAULT_UKA_PRICE_GBP, gt=0, le=500),
           eur_per_gbp: float = Query(DEFAULT_EUR_PER_GBP, gt=0.5, le=2.0),
           pool_price: float = Query(DEFAULT_POOL_PRICE_EUR_PER_TCO2E, ge=0, le=2000),
           deficit_years: int = Query(1, ge=1, le=20),
           charter_from: Optional[str] = None, charter_to: Optional[str] = None,
           charter_pct: Optional[float] = Query(None, ge=0, le=100),
           fueleu_basis: str = Query("penalty", pattern="^(penalty|pool)$")):
    """ESTIMATE scorecard. DWT is optional: without it the cost engines
    (ETS/UK ETS/FuelEU/NZF) still run — only CII needs capacity — so the
    first answer costs the visitor a single input. biofuel_pct/speed_pct
    apply the what-if transform before scoring."""
    _guard(request)
    rec = records().get(imo)
    if rec is None:
        raise HTTPException(404, f"IMO {imo} was not found in the public EU MRV register.")
    if privacy.is_suppressed(imo):
        return _suppressed_payload(rec)
    if rec.ship_type is None:
        raise HTTPException(422, _unsupported(rec.ship_type_raw))
    return ship_result(rec, dwt=dwt, year=year, biofuel_pct=biofuel_pct, speed_pct=speed_pct,
                       speed_exp=speed_exp, aux_pct=aux_pct, ice_class=ice_class,
                       derogation_pct=derogation_pct, eua=eua_price, uka=uka_price, fx=eur_per_gbp,
                       pool=pool_price, deficit_years=deficit_years, charter_from=charter_from,
                       charter_to=charter_to, charter_pct=charter_pct, fueleu_basis=fueleu_basis)


@app.get("/api/fleet")
def fleet(imos: str = Query(min_length=7, max_length=2000), request: Request = None,
          eua_price: float = Query(DEFAULT_EUA_PRICE_EUR, gt=0, le=500),
          pool_price: float = Query(DEFAULT_POOL_PRICE_EUR_PER_TCO2E, ge=0, le=2000)):
    """Comma/space/newline-separated IMOs -> per-vessel cost summary +
    intra-fleet FuelEU pooling suggestion (Art. 21)."""
    from ghgcore.pooling import PoolCandidate, suggest_pool
    wanted = _parse_imos(imos)
    if len(wanted) > privacy.ANON_FLEET_MAX_VESSELS:
        raise HTTPException(403,
            f"Anonymous fleet analysis is limited to "
            f"{privacy.ANON_FLEET_MAX_VESSELS} ships (you sent {len(wanted)}). "
            "The limit stops bulk copying of other operators’ data. If these are "
            "your ships, claim them under “Your data” to analyse the full list.")
    _guard(request, cost=len(wanted))
    recs = records()
    out, cands, hidden = [], [], []
    for imo in wanted:
        rec = recs.get(imo)
        if rec is None or rec.ship_type is None:
            out.append({"imo": imo, "name": rec.name if rec else None,
                        "supported": False})
            continue
        if privacy.is_suppressed(imo):
            hidden.append(imo)
            out.append({"imo": imo, "name": rec.name, "supported": False,
                        "suppressed": True})
            continue
        act = record_to_activity(rec, year=rec.reporting_period or 2025, dwt=1.0)
        feu = compute_fueleu(act, pool_price_eur_per_tco2e=pool_price)
        ets, ukets = compute_ets(act, eua_price), compute_ukets(act)
        # carbon cost the standard lever package would remove (modelled)
        lev = apply_whatif(act, 20.0, -10.0)
        lever_saving = max(0.0, (ets.cost_eur + feu.penalty_eur)
                           - (compute_ets(lev, eua_price).cost_eur + compute_fueleu(lev).penalty_eur))
        cpd = (rec.co2_tonnes * 1000.0 / rec.est_distance_nm
               if rec.est_distance_nm else None)
        out.append({"imo": imo, "name": rec.name, "ship_type": rec.ship_type_raw,
                    "co2_tonnes": rec.co2_tonnes, "euas": ets.allowances_due,
                    "ets_cost_eur": ets.cost_eur, "ukets_cost_gbp": ukets.cost_gbp,
                    "fueleu_cb_t": feu.compliance_balance_tco2e,
                    "fueleu_penalty_eur": feu.penalty_eur,
                    "fueleu_pooled_eur": (feu.pooling_cost_eur if feu.pooling_cost_eur is not None
                                          else feu.penalty_eur),
                    "fueleu_applicable": feu.applicable,
                    "lever_saving_eur": round(lever_saving),
                    "co2_per_nm_kg": round(cpd, 1) if cpd else None,
                    "supported": True})
        cands.append(PoolCandidate(imo, rec.name, feu.compliance_balance_tco2e,
                                   feu.ghg_intensity))
    pool = suggest_pool(cands) if cands else None
    return {"source": _EXPORT_NAME, "vessels": out,
            "assumptions": assumptions_block(eua_price, DEFAULT_UKA_PRICE_GBP, DEFAULT_EUR_PER_GBP,
                                             pool_price),
            "suppressed_imos": hidden,
            "pooling": None if pool is None else {
                "avoided_penalty_eur": pool.avoided_penalty_eur,
                "pool_cb_tco2e": pool.pool_cb_tco2e,
                "member_imos": [m.imo for m in pool.members],
                "uncovered_imos": [u.imo for u in pool.uncovered],
                "uncovered_penalty_eur": pool.uncovered_penalty_eur,
                "notes": pool.notes}}


@app.get("/api/eexi/{imo}")
def eexi(imo: str, dwt: float = Query(gt=0), gt: Optional[float] = Query(None, gt=0),
         request: Request = None):
    """FREE EEXI check: required (Reg. 25) vs the attained value the ship
    already reported to THETIS-MRV. For cruise ships pass gt."""
    from ghgcore.eexi import compute_eexi
    _guard(request)
    rec = records().get(imo)
    if rec is None:
        raise HTTPException(404, f"IMO {imo} was not found in the public EU MRV register.")
    if privacy.is_suppressed(imo):
        return _suppressed_payload(rec)
    if rec.ship_type is None:
        raise HTTPException(422, _unsupported(rec.ship_type_raw))
    r = compute_eexi(rec.ship_type, dwt, gt or dwt, rec.tech_efficiency)
    return {"imo": rec.imo, "name": rec.name, "ship_type": rec.ship_type_raw,
            "reported_raw": rec.tech_efficiency, "source": _EXPORT_NAME,
            "result": asdict(r)}


@app.get("/api/siblings/{imo}")
def siblings(imo: str, limit: int = Query(60, ge=1, le=60), request: Request = None):
    """The selected ship's company fleet ('related ships') with the
    verified carbon-intensity-per-mile of each — chart fodder. CO2/nm is
    the honest cross-ship axis: a true CII per sibling would need each
    ship's DWT, which the public export lacks."""
    # public EMSA facts only, shown with every ship: its own, larger allowance
    if not privacy.rate_limit_ok(_client_key(request) + ":siblings", limit=600):
        raise HTTPException(429, "Too many requests this hour. Please try again later.")
    recs = records()
    rec = recs.get(imo)
    if rec is None:
        raise HTTPException(404, f"IMO {imo} was not found in the public EU MRV register.")
    if not rec.company or privacy.is_suppressed(imo):
        return {"imo": imo, "company": None, "siblings": []}
    fleet = [r for r in recs.values() if r.company == rec.company
             and not privacy.is_suppressed(r.imo)]
    fleet.sort(key=lambda r: (r.ship_type_raw, r.name))
    out = []
    for r in fleet[:limit]:
        cpd = (r.co2_tonnes * 1000.0 / r.est_distance_nm) if r.est_distance_nm else None
        out.append({"imo": r.imo, "name": r.name, "ship_type": r.ship_type_raw,
                    "co2_tonnes": r.co2_tonnes,
                    "co2_per_nm_kg": round(cpd, 1) if cpd else None,
                    "same_type": r.ship_type_raw == rec.ship_type_raw,
                    "selected": r.imo == imo,
                    "tech_efficiency": r.tech_efficiency})
    return {"imo": imo, "company": rec.company, "fleet_size": len(fleet),
            "siblings": out}


@app.get("/api/eexi-custom")
def eexi_custom(ship_type: ShipType, dwt: float = Query(gt=0),
                gt: Optional[float] = Query(None, gt=0),
                attained: Optional[float] = Query(None, gt=0),
                mcr_kw: Optional[float] = Query(None, gt=0),
                vref_kn: Optional[float] = Query(None, gt=0),
                main_fuel: FuelType = FuelType.HFO,
                sfoc_me: float = Query(175.0, gt=0, le=400),
                sfoc_ae: float = Query(215.0, gt=0, le=400),
                request: Request = None):
    """FREE custom-vessel EEXI: any ship, no registry needed. Either supply
    the attained EEXI, or MCR + service speed to estimate it (simplified
    EEDI formula, assumptions returned in notes)."""
    from ghgcore.eexi import compute_eexi_custom
    _guard(request)
    try:
        r = compute_eexi_custom(ship_type, dwt, gt or dwt, attained=attained,
                                mcr_kw=mcr_kw, vref_kn=vref_kn,
                                main_fuel=main_fuel,
                                sfoc_me=sfoc_me, sfoc_ae=sfoc_ae)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ship_type": ship_type.value, "dwt": dwt, "gt": gt,
            "result": asdict(r)}


@app.get("/api/audit/{imo}")
def audit(imo: str, dwt: float = Query(gt=0), year: Optional[int] = None,
          eua_price: float = Query(DEFAULT_EUA_PRICE_EUR, gt=0, le=500), request: Request = None):
    """Verifier-ready calculation worksheet: inputs, every parameter used
    (with source citation), intermediates, results."""
    from ghgcore.audit import build_audit
    _guard(request)
    rec = records().get(imo)
    if rec is None:
        raise HTTPException(404, f"IMO {imo} was not found in the public EU MRV register.")
    if privacy.is_suppressed(imo):
        raise HTTPException(403, privacy.SUPPRESSION_NOTE)
    if rec.ship_type is None:
        raise HTTPException(422, _unsupported(rec.ship_type_raw))
    y = year or rec.reporting_period or 2025
    return build_audit(record_to_activity(rec, year=y, dwt=dwt), eua_price=eua_price, estimate=True)


@app.get("/api/method")
def method():
    """The Method/trust page content: calculation notes markdown."""
    p = os.path.join(os.path.dirname(__file__), "..", "docs", "CALCULATION_NOTES.md")
    with open(p, encoding="utf-8") as f:
        return PlainTextResponse(f.read(), media_type="text/markdown")


def _require_key(key: Optional[str]) -> str:
    """The calculator is open unless CARBONKEEL_REQUIRE_KEY is set (see ghgcore/access.py)."""
    from ghgcore import access
    if not access.required():
        return ""
    if not access.is_valid(key):
        raise HTTPException(401, "This tool needs an access key at the moment. Enter yours, "
                                 "or email enquiry@carbonkeel.com for one.")
    return access.label_for(key)


@app.get("/api/access/status")
def access_status():
    from ghgcore import access
    return {"required": access.required()}


@app.get("/api/access/check")
def access_check(key: str = Query(...)):
    """Validate an access key (used by the UI unlock screen)."""
    from ghgcore import access
    if not access.is_valid(key):
        raise HTTPException(401, "That access key is not recognised. Check it, or email "
                                 "enquiry@carbonkeel.com.")
    return {"ok": True, "issued_to": access.label_for(key)}


# Bounds on owner-supplied figures: far above any real ship, low enough that nothing overflows.
MAX_CAPACITY = 1_000_000          # DWT or GT
MAX_FUEL_T = 5_000_000            # tonnes of one fuel in a year
MAX_DISTANCE_NM = 2_000_000


def _check_fuel(*maps: dict) -> None:
    for mp in maps:
        if len(mp) > 10 or any(not (0 <= v <= MAX_FUEL_T) for v in mp.values()):
            raise HTTPException(422, f"Fuel quantities must be between 0 and {MAX_FUEL_T:,} tonnes.")


class SpeedIn(BaseModel):
    ref_cons_t_per_day: float = Field(ge=0, le=2000)
    ref_speed_kn: float = Field(ge=0, le=60)
    actual_speed_kn: float = Field(ge=0, le=60)
    sea_days: float = Field(ge=0, le=366)
    aux_t_per_day_at_sea: float = Field(0.0, ge=0, le=500)
    port_days: float = Field(0.0, ge=0, le=366)
    aux_t_per_day_in_port: float = Field(0.0, ge=0, le=500)
    main_fuel: FuelType = FuelType.HFO
    aux_fuel: FuelType = FuelType.MDO_MGO
    speed_exponent: float = Field(3.0, ge=2.0, le=4.5)


class G5DeductionIn(BaseModel):
    kind: str
    fuel: FuelType
    tonnes: float = Field(0.0, ge=0, le=MAX_FUEL_T)
    distance_nm: float = Field(0.0, ge=0, le=MAX_DISTANCE_NM)
    basis: str = Field("", max_length=300)


class G5In(BaseModel):
    deductions: list[G5DeductionIn] = Field([], max_length=20)
    shuttle_tanker: bool = False
    ice_class: str = Field("", max_length=40)
    fi: float = Field(1.0, gt=0, le=3)
    fm: float = Field(1.0, gt=0, le=3)
    fc: float = Field(1.0, gt=0, le=3)
    fivse: float = Field(1.0, gt=0, le=3)
    self_unloading: bool = False


class CIIIn(BaseModel):
    ship_type: ShipType
    dwt: float = Field(0.0, ge=0, le=MAX_CAPACITY)
    gt: float = Field(0.0, ge=0, le=MAX_CAPACITY)
    year: int = Field(2026, ge=2023, le=2035)
    fuel_tonnes: dict[FuelType, float] = {}
    distance_nm: float = Field(0.0, ge=0, le=MAX_DISTANCE_NM)
    speed: Optional[SpeedIn] = None
    # G5 (documented operator values only): summary totals, or itemised in `g5`
    excluded_co2_t: float = Field(0.0, ge=0, le=MAX_FUEL_T * 4)
    excluded_distance_nm: float = Field(0.0, ge=0, le=MAX_DISTANCE_NM)
    capacity_correction: float = Field(1.0, gt=0, le=3)
    corrections_basis: str = Field("", max_length=300)
    g5: Optional[G5In] = None
    vessel_name: str = Field("", max_length=120)
    imo_number: str = Field("", max_length=20)


def _cii_from(inp: CIIIn):
    from ghgcore.cii_calc import CIIInput, SpeedProfile, compute_cii_full
    from ghgcore.cii import CIICorrections
    from ghgcore.g5 import G5Deduction, G5Input
    _check_fuel(inp.fuel_tonnes)
    sp = SpeedProfile(**inp.speed.model_dump()) if inp.speed is not None else None
    corr = None
    if (inp.excluded_co2_t or inp.excluded_distance_nm
            or inp.capacity_correction != 1.0):
        corr = CIICorrections(inp.excluded_co2_t, inp.excluded_distance_nm,
                              inp.capacity_correction, inp.corrections_basis)
    g5 = None
    if inp.g5 is not None:
        g = inp.g5
        g5 = G5Input([G5Deduction(d.kind, d.fuel, d.tonnes, d.distance_nm, d.basis)
                      for d in g.deductions], g.shuttle_tanker, g.ice_class,
                     g.fi, g.fm, g.fc, g.fivse, g.self_unloading)
        if not g5.deductions and not g5.shuttle_tanker and (g.fi, g.fm, g.fc, g.fivse) == (1, 1, 1, 1):
            g5 = None
    try:
        return compute_cii_full(CIIInput(
            ship_type=inp.ship_type, dwt=inp.dwt, gt=inp.gt, year=inp.year,
            fuel_tonnes={k: v for k, v in inp.fuel_tonnes.items() if v > 0},
            distance_nm=inp.distance_nm, speed_profile=sp, corrections=corr,
            vessel_name=inp.vessel_name, imo_number=inp.imo_number, g5=g5))
    except (ValueError, KeyError) as e:
        raise HTTPException(422, str(e))


@app.post("/api/cii/compute")
def cii_compute(inp: CIIIn, key: Optional[str] = Query(None),
                request: Request = None):
    """Owner-data CII calculation (G1–G5) with forward trajectory."""
    _require_key(key)
    _guard(request)
    return asdict(_cii_from(inp))


class ScopeIn(BaseModel):
    intra_eea: float = Field(0.0, ge=0, le=100)
    extra_eea: float = Field(0.0, ge=0, le=100)
    berth_eea: float = Field(0.0, ge=0, le=100)
    uk_domestic: float = Field(0.0, ge=0, le=100)
    uk_gb_ni: float = Field(0.0, ge=0, le=100)


class CalcIn(CIIIn):
    scope: ScopeIn = ScopeIn()
    engine_type: str = "otto_medium_speed"
    eua_price: float = Field(DEFAULT_EUA_PRICE_EUR, gt=0, le=500)
    uka_price: float = Field(DEFAULT_UKA_PRICE_GBP, gt=0, le=500)
    eur_per_gbp: float = Field(DEFAULT_EUR_PER_GBP, gt=0.5, le=2.0)
    pool_price: float = Field(DEFAULT_POOL_PRICE_EUR_PER_TCO2E, ge=0, le=2000)
    deficit_years: int = Field(1, ge=1, le=20)
    ice_class_ia: bool = False
    derogation_pct: float = Field(0.0, ge=0, le=100)
    charter_from: Optional[str] = None
    charter_to: Optional[str] = None
    charter_pct: Optional[float] = Field(None, ge=0, le=100)
    fueleu_basis: str = Field("penalty", pattern="^(penalty|pool)$")


@app.post("/api/calc")
def calc(inp: CalcIn, key: Optional[str] = Query(None), request: Request = None):
    """Owner data in, the whole position out: CII (G1-G5) plus the EU ETS, UK ETS, FuelEU
    and NZF bill from the operator's own fuel, split by voyage scope. Nothing is stored."""
    _require_key(key)
    _guard(request)
    from ghgcore.ownerbill import ScopeSplit, build_activity
    from ghgcore.ets_combined import compute_ets_combined
    from ghgcore.ets_rules import ETSExceptions
    from ghgcore.schema import EngineType
    cii = _cii_from(inp)
    fuels = {FuelType(k): v for k, v in cii.fuel_tonnes.items()}
    try:
        engine = EngineType(inp.engine_type)
        act, rows = build_activity(inp.vessel_name, inp.imo_number, inp.ship_type, inp.dwt, inp.gt,
                                   inp.year, fuels, ScopeSplit(**inp.scope.model_dump()), engine)
    except ValueError as e:
        raise HTTPException(422, str(e))
    both = compute_ets_combined(act, inp.eua_price, inp.uka_price, inp.eur_per_gbp,
                                ETSExceptions(inp.ice_class_ia, inp.derogation_pct / 100.0))
    feu = compute_fueleu(act, consecutive_deficit_years=inp.deficit_years,
                         pool_price_eur_per_tco2e=inp.pool_price)
    nzf = compute_nzf(act)
    uk_eur = both.uk.cost_gbp * inp.eur_per_gbp
    feu_pool = feu.pooling_cost_eur if feu.pooling_cost_eur is not None else feu.penalty_eur
    feu_used = feu_pool if inp.fueleu_basis == "pool" else feu.penalty_eur
    out = {"estimate": cii.estimated_inputs, "cii": asdict(cii), "scope_rows": rows,
           "ets": asdict(both.eu), "ukets": asdict(both.uk), "fueleu": asdict(feu), "nzf": asdict(nzf),
           "assumptions": assumptions_block(inp.eua_price, inp.uka_price, inp.eur_per_gbp, inp.pool_price),
           "bill": {"year": inp.year, "ets_eur": both.eu.cost_eur, "ukets_eur": round(uk_eur, 0),
                    "fueleu_penalty_eur": feu.penalty_eur, "fueleu_pooled_eur": feu_pool,
                    "fueleu_basis": inp.fueleu_basis, "fueleu_eur": feu_used,
                    "total_eur": round(both.eu.cost_eur + uk_eur + feu_used, 0),
                    "total_penalty_eur": round(both.eu.cost_eur + uk_eur + feu.penalty_eur, 0),
                    "total_pooled_eur": round(both.eu.cost_eur + uk_eur + feu_pool, 0)}}
    start = _parse_day(inp.charter_from, "charter start")
    end = _parse_day(inp.charter_to, "charter end")
    if start and end:
        from ghgcore.charter import split
        items = {"EU ETS allowances": both.eu.cost_eur}
        if uk_eur > 0:
            items["UK ETS allowances"] = uk_eur
        if feu_used > 0:
            items["FuelEU deficit (" + ("pooled" if inp.fueleu_basis == "pool" else "statutory penalty") + ")"] = feu_used
        try:
            out["charter"] = asdict(split(inp.year, start, end, items,
                                          None if inp.charter_pct is None else inp.charter_pct / 100.0))
        except ValueError as e:
            raise HTTPException(422, str(e))
    elif start or end:
        raise HTTPException(422, "Give both the charter start and end dates.")
    return out


@app.get("/api/privacy")
def privacy_doc():
    """Data provenance & operator-control policy (rendered as a page)."""
    p = os.path.join(os.path.dirname(__file__), "..", "docs", "DATA_AND_PRIVACY.md")
    with open(p, encoding="utf-8") as f:
        return PlainTextResponse(f.read(), media_type="text/markdown")


@app.get("/healthz")
def healthz():
    """Liveness probe + keep-warm target. Reports whether the register is
    loaded so a cold start is visible rather than silent."""
    return {"ok": True, "export": _EXPORT_NAME or "not loaded",
            "ships": len(_RECORDS) if _RECORDS else 0}


@app.get("/home")
def landing_page():
    """The public landing page, served by the app as well as by Cloudflare
    Pages. One server and one address then show the whole journey locally
    (the opening page and the app), and a bare onrender.com stage works too."""
    return FileResponse(
        os.path.join(os.path.dirname(__file__), "..", "site", "index.html"),
        headers={"Cache-Control": "no-store, must-revalidate"})


@app.get("/privacy.html")
def privacy_notice():
    """The privacy notice, served by the app too, so a relative link to it
    works on whatever host the app is on (a bare *.onrender.com address
    during a staged rollout, app.carbonkeel.com later)."""
    return FileResponse(
        os.path.join(os.path.dirname(__file__), "..", "site", "privacy.html"),
        headers={"Cache-Control": "no-cache"})


@app.get("/robots.txt")
def robots():
    """The landing page and privacy notice are indexable. Per-vessel derived figures are
    not: searching an operator's ship name should never surface our estimate of its bill."""
    return PlainTextResponse(
        "User-agent: *\n"
        "Allow: /$\n"
        "Allow: /privacy\n"
        "Disallow: /api/\n"
        "Disallow: /report\n"
        "Disallow: /app\n"
        "Sitemap: https://carbonkeel.com/sitemap.xml\n")


@app.get("/sitemap.xml")
def sitemap():
    from fastapi.responses import Response
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '  <url><loc>https://carbonkeel.com/</loc><changefreq>weekly</changefreq></url>\n'
            '  <url><loc>https://carbonkeel.com/privacy</loc><changefreq>yearly</changefreq></url>\n'
            '</urlset>\n')
    return Response(body, media_type="application/xml")


class ShipReportQ:
    def __init__(self, dwt: Optional[float] = Query(None, gt=0),
                 year: Optional[int] = Query(None, ge=2018, le=2035),
                 eua_price: float = Query(DEFAULT_EUA_PRICE_EUR, gt=0, le=500),
                 uka_price: float = Query(DEFAULT_UKA_PRICE_GBP, gt=0, le=500),
                 eur_per_gbp: float = Query(DEFAULT_EUR_PER_GBP, gt=0.5, le=2.0),
                 pool_price: float = Query(DEFAULT_POOL_PRICE_EUR_PER_TCO2E, ge=0, le=2000),
                 deficit_years: int = Query(1, ge=1, le=20),
                 ice_class: bool = False,
                 derogation_pct: float = Query(0, ge=0, le=100),
                 charter_from: Optional[str] = None, charter_to: Optional[str] = None,
                 charter_pct: Optional[float] = Query(None, ge=0, le=100),
                 fueleu_basis: str = Query("penalty", pattern="^(penalty|pool)$")):
        self.kw = dict(dwt=dwt, year=year, eua=eua_price, uka=uka_price, fx=eur_per_gbp,
                       pool=pool_price, deficit_years=deficit_years, ice_class=ice_class,
                       derogation_pct=derogation_pct, charter_from=charter_from,
                       charter_to=charter_to, charter_pct=charter_pct, fueleu_basis=fueleu_basis)


def _report_result(imo: str, q: ShipReportQ, request: Optional[Request]) -> dict:
    _guard(request)
    rec = records().get(imo)
    if rec is None:
        raise HTTPException(404, f"IMO {imo} was not found in the public EU MRV register.")
    if privacy.is_suppressed(imo):
        raise HTTPException(403, privacy.SUPPRESSION_NOTE)
    if rec.ship_type is None:
        raise HTTPException(422, _unsupported(rec.ship_type_raw))
    return ship_result(rec, **q.kw)


@app.get("/report/ship/{imo}.csv")
def ship_report_csv_route(imo: str, request: Request, q: ShipReportQ = Depends()):
    from fastapi.responses import Response
    from .ship_report import ship_report_csv
    r = _report_result(imo, q, request)
    return Response(ship_report_csv(r), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="carbonkeel-{imo}.csv"'})


@app.get("/report/ship/{imo}")
def ship_report_route(imo: str, request: Request, q: ShipReportQ = Depends()):
    from fastapi.responses import HTMLResponse
    from .ship_report import ship_report_html
    r = _report_result(imo, q, request)
    qs = request.url.query
    return HTMLResponse(ship_report_html(r, f"/report/ship/{imo}.csv" + (f"?{qs}" if qs else "")))


class ClaimIn(BaseModel):
    kind: str = Field(pattern="^(claim|correct|suppress)$")
    imos: list[str] = Field(max_length=20)
    company: str = Field("", max_length=200)
    contact_email: str = Field(max_length=254)
    message: str = Field("", max_length=2000)


@app.post("/api/claim")
def claim(inp: ClaimIn, request: Request = None):
    """Operator control: claim vessels, correct our figures, or suppress our
    derived estimates. Suppression is applied straight away — we do not make an
    operator wait for a human to action a 'stop showing my data' request. It is
    then made permanent by the operator of the service (see
    CARBONKEEL_SUPPRESSED_IMOS), because a free host can lose local files."""
    _guard(request)
    if not privacy.rate_limit_ok(_client_key(request) + ":claim", limit=10):
        raise HTTPException(429, "Too many requests from here this hour. Email enquiry@carbonkeel.com instead.")
    try:
        req = privacy.log_request(inp.kind, inp.imos, inp.company,
                                  inp.contact_email, inp.message)
    except ValueError as e:
        raise HTTPException(422, str(e))
    msg = {
        "suppress": "Done — our derived estimates for those IMOs are hidden "
                    "from third parties straight away, and we will confirm by "
                    "email once it is permanent. The EMSA-published figures "
                    "stay visible because Article 21 requires their publication.",
        "claim": "Claim received. We will check it against your company domain or "
                 "Document of Compliance and come back to you.",
        "correct": "Correction received. Send the underlying data (noon reports "
                   "or bunker delivery notes) and we will replace the estimate and "
                   "label it as owner-verified.",
    }[inp.kind]
    if inp.kind == "suppress" and not req.applied:
        msg = ("Received. We have had an unusual number of requests today, so we will check this "
               "one and hide the figures by hand, usually within one working day. The EMSA-published "
               "figures stay visible because Article 21 requires their publication.")
    return {"ok": True, "kind": req.kind, "imos": req.imos, "applied": req.applied, "message": msg}


@app.get("/api/calendar")
def calendar(year: int = Query(2026, ge=2024, le=2035)):
    """All dated obligations arising from compliance year `year`."""
    from ghgcore.deadlines import deadlines_for
    return {"compliance_year": year,
            "deadlines": [{"due": d.due.isoformat(), "regime": d.regime,
                           "what": d.what, "basis": d.basis}
                          for d in deadlines_for(year)]}


@app.get("/api/calendar.ics")
def calendar_ics(year: int = Query(2026, ge=2024, le=2035),
                 fleet: str = "Fleet"):
    """Same calendar as an importable .ics file (14-day alarms included)."""
    from fastapi.responses import Response
    from ghgcore.deadlines import deadlines_for, to_ics
    return Response(to_ics(deadlines_for(year), fleet),
                    media_type="text/calendar",
                    headers={"Content-Disposition":
                             f'attachment; filename="carbonkeel-{year}.ics"'})


@app.get("/api/pool-agreement")
def pool_agreement(imos: str = Query(min_length=7, max_length=2000),
                   year: int = Query(2026, ge=2025, le=2035),
                   organiser: str = Query("[ORGANISER LEGAL NAME]", max_length=200),
                   request: Request = None):
    """Draft Art. 21 pooling agreement (markdown) for the given fleet."""
    from fastapi.responses import PlainTextResponse
    from ghgcore.pooling import PoolCandidate, suggest_pool
    from ghgcore.pool_agreement import draft_agreement
    wanted = [i for i in _parse_imos(imos) if not privacy.is_suppressed(i)]
    if len(wanted) > privacy.ANON_FLEET_MAX_VESSELS:
        raise HTTPException(403, f"Draft agreements are limited to {privacy.ANON_FLEET_MAX_VESSELS} "
                                 "ships. If these are your ships, claim them under “Your data”.")
    _guard(request, cost=max(1, len(wanted)))
    recs = records()
    cands = []
    for imo in wanted:
        rec = recs.get(imo)
        if rec is None or rec.ship_type is None:
            continue
        act = record_to_activity(rec, year=rec.reporting_period or year, dwt=1.0)
        feu = compute_fueleu(act)
        cands.append(PoolCandidate(imo, rec.name, feu.compliance_balance_tco2e,
                                   feu.ghg_intensity))
    if not cands:
        raise HTTPException(422, "None of those ships can be scored yet.")
    return PlainTextResponse(draft_agreement(suggest_pool(cands), year, organiser),
                             media_type="text/markdown")


@app.get("/report")
def report(imos: str = Query(min_length=7, max_length=2000), year: Optional[int] = Query(None, ge=2018, le=2035),
           request: Request = None,
           eua_price: float = Query(DEFAULT_EUA_PRICE_EUR, gt=0, le=500)):
    """Branded fleet health-check page (print to PDF) — the lead magnet."""
    from fastapi.responses import HTMLResponse
    from .report import fleet_report_html
    wanted = [i for i in _parse_imos(imos) if not privacy.is_suppressed(i)]
    if not wanted:
        raise HTTPException(403, privacy.SUPPRESSION_NOTE)
    if len(wanted) > privacy.ANON_FLEET_MAX_VESSELS:
        raise HTTPException(403,
            f"Anonymous reports are limited to {privacy.ANON_FLEET_MAX_VESSELS} "
            "ships. If these are your ships, claim them under “Your data” "
            "for the full report.")
    _guard(request, cost=len(wanted))
    return HTMLResponse(fleet_report_html(records(), wanted, year, eua_price=eua_price))


def _parse_imos(raw: str) -> list[str]:
    import re
    seen, out = set(), []
    for m in re.findall(r"\d{7}", raw):
        if m not in seen:
            seen.add(m)
            out.append(m)
    if not out:
        raise HTTPException(422, "No 7-digit IMO numbers found in the text you pasted.")
    return out


class LegIn(BaseModel):
    scope: VoyageScope
    distance_nm: float = Field(ge=0, le=MAX_DISTANCE_NM)
    fuel: dict[FuelType, float]        # tonnes by fuel type
    uk_share: Optional[float] = Field(None, ge=0, le=1)


class ScoreIn(BaseModel):
    imo: str = Field(max_length=20)
    name: str = Field(max_length=120)
    ship_type: ShipType
    dwt: float = Field(gt=0, le=MAX_CAPACITY)
    gt: float = Field(0.0, ge=0, le=MAX_CAPACITY)
    year: int = Field(ge=2018, le=2035)
    legs: list[LegIn] = Field(min_length=1, max_length=500)
    eua_price: float = DEFAULT_EUA_PRICE_EUR
    nzf_year: int = 2028


@app.post("/api/score")
def score(inp: ScoreIn, request: Request = None):
    _guard(request)
    _check_fuel(*(l.fuel for l in inp.legs))
    vessel = Vessel(inp.imo, inp.name, inp.ship_type, dwt=inp.dwt, gt=inp.gt)
    legs = [VoyageLeg(l.scope, l.distance_nm,
                      [FuelConsumption(f, t) for f, t in l.fuel.items() if t > 0],
                      "API input", uk_share=l.uk_share)
            for l in inp.legs]
    sc = build_scorecard(AnnualActivity(vessel, inp.year, legs),
                         eua_price=inp.eua_price, nzf_year=inp.nzf_year)
    return {"estimate": False, "scorecard": asdict(sc)}
