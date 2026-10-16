"""CarbonKeel API — free-lookup funnel + owner-data scoring.

Run:  python -m uvicorn api.main:app --reload   (from repo root)
Then open http://127.0.0.1:8000

Endpoints:
  GET  /api/search?q=NAME        find ships in the public THETIS-MRV export
  GET  /api/lookup/{imo}?dwt=N   ESTIMATE scorecard from public data
  POST /api/score                full scorecard from owner-supplied activity
"""
import glob
import os
import sys
import threading
from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ghgcore import (Vessel, AnnualActivity, VoyageLeg, FuelConsumption,
                     FuelType, ShipType, VoyageScope, build_scorecard)
from ghgcore.thetis import load_thetis_cached, record_to_activity
from ghgcore.exports import ordered as _ordered_exports
from ghgcore.fueleu import compute_fueleu
from ghgcore.euets import compute_ets
from ghgcore.ukets import compute_ukets
from ghgcore.nzf import compute_nzf
from ghgcore import privacy

app = FastAPI(title="CarbonKeel", version="0.2.0")


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


@app.middleware("http")
async def _security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Permissions-Policy",
                            "camera=(), microphone=(), geolocation=()")
    return resp


def _unsupported(raw):
    """Message for a ship type we do not cover yet. The page looks for the
    phrase 'not yet supported' to offer the custom EEXI check instead."""
    return (f"Ship type “{raw}” is not yet supported. We cover 12 ship types, "
            "including container ships, bulk carriers, tankers, LNG carriers, "
            "ro-ro, ro-pax and cruise ships.")


@app.get("/")
def index():
    return FileResponse(
        os.path.join(os.path.dirname(__file__), "..", "site", "index.html"),
        headers={"Cache-Control": "no-store, must-revalidate"})


@app.get("/app")
def app_route():
    # no-store: the single-page app is edited live during demos/development;
    # a cached shell silently hides new features and breaks calls.
    return FileResponse(
        os.path.join(os.path.dirname(__file__), "static", "index.html"),
        headers={"Cache-Control": "no-store, must-revalidate"})


@app.get("/privacy")
def privacy():
    return FileResponse(
        os.path.join(os.path.dirname(__file__), "static", "privacy.html"),
        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.get("/api/search")
def search(request: Request, q: str = Query(min_length=3), limit: int = 20):
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


def _whatif(act: AnnualActivity, biofuel_pct: float, speed_pct: float) -> AnnualActivity:
    """Deterministic scenario transform (prototype physics, clearly labelled):
    - speed change: fuel per nm scales with speed^2 (cube law per unit time,
      distance held constant), so tonnes *= (1 + s/100)^2
    - biofuel: `biofuel_pct` of each fossil fuel's ENERGY switches to
      certified B100; replacement tonnage is LCV-corrected
      (t_bio = t_fossil_removed x LCV_fossil / LCV_bio), so the ship does the
      same work on ~10% more biofuel tonnes.
    """
    from ghgcore.fueleu import FUEL_PROPS
    ratio = (1 + speed_pct / 100.0) ** 2
    b = max(0.0, min(100.0, biofuel_pct)) / 100.0
    fossil = {FuelType.HFO, FuelType.LFO, FuelType.MDO_MGO}
    lcv_bio = FUEL_PROPS[FuelType.BIOFUEL_B100][0]
    legs = []
    for leg in act.legs:
        fuels: list[FuelConsumption] = []
        bio = 0.0
        for fc in leg.fuel_consumed:
            t = fc.tonnes * ratio
            if fc.fuel in fossil and b > 0:
                removed = t * b
                bio += removed * FUEL_PROPS[fc.fuel][0] / lcv_bio
                t -= removed
            fuels.append(FuelConsumption(fc.fuel, t))
        if bio > 0:
            fuels.append(FuelConsumption(FuelType.BIOFUEL_B100, bio))
        legs.append(VoyageLeg(leg.scope, leg.distance_nm, fuels,
                              leg.description + " [what-if]", uk_share=leg.uk_share))
    return AnnualActivity(act.vessel, act.year, legs, act.ets_calibration, act.fuel_is_combusted)


@app.get("/api/lookup/{imo}")
def lookup(imo: str, request: Request = None,
           dwt: Optional[float] = Query(None, gt=0),
           year: Optional[int] = None,
           biofuel_pct: float = Query(0, ge=0, le=100),
           speed_pct: float = Query(0, ge=-30, le=20),
           ice_class: bool = False,
           derogation_pct: float = Query(0, ge=0, le=100)):
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
    y = year or rec.reporting_period or 2025
    from ghgcore.ets_rules import ETSExceptions
    from ghgcore.thetis import rebuilt_ets_co2
    eu_exc = ETSExceptions(ice_class, derogation_pct / 100.0)
    verified = {"co2_tonnes": rec.co2_tonnes, "fuel_tonnes": rec.fuel_tonnes,
                "ets_scope_co2_reported": rec.co2_ets_reported_t,
                "ets_scope_co2_rebuilt": rebuilt_ets_co2(rec),
                "est_distance_nm": rec.est_distance_nm,
                "tech_efficiency": rec.tech_efficiency}
    scenario = bool(biofuel_pct or speed_pct)

    def transform(act):
        return _whatif(act, biofuel_pct, speed_pct) if scenario else act

    if dwt:
        sc = build_scorecard(transform(record_to_activity(rec, year=y, dwt=dwt)), eu_exceptions=eu_exc)
        return {"estimate": True, "scenario": scenario, "source": _EXPORT_NAME,
                "verified": verified, "scorecard": asdict(sc)}
    act = transform(record_to_activity(rec, year=y, dwt=1.0))
    feu, ets, ukets, nzf = (compute_fueleu(act), compute_ets(act, exceptions=eu_exc),
                             compute_ukets(act), compute_nzf(act))
    return {"estimate": True, "scenario": scenario, "source": _EXPORT_NAME,
            "verified": verified,
            "partial": True, "vessel_name": rec.name, "imo": rec.imo, "year": y,
            "ets": asdict(ets), "ukets": asdict(ukets), "fueleu": asdict(feu), "nzf": asdict(nzf)}


@app.get("/api/fleet")
def fleet(imos: str = Query(min_length=7), request: Request = None):
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
        feu, ets, ukets = compute_fueleu(act), compute_ets(act), compute_ukets(act)
        # carbon cost the standard lever package would remove (modelled)
        lev = _whatif(act, 20.0, -10.0)
        lever_saving = max(0.0, (ets.cost_eur + feu.penalty_eur)
                           - (compute_ets(lev).cost_eur + compute_fueleu(lev).penalty_eur))
        cpd = (rec.co2_tonnes * 1000.0 / rec.est_distance_nm
               if rec.est_distance_nm else None)
        out.append({"imo": imo, "name": rec.name, "ship_type": rec.ship_type_raw,
                    "co2_tonnes": rec.co2_tonnes, "euas": ets.allowances_due,
                    "ets_cost_eur": ets.cost_eur, "ukets_cost_gbp": ukets.cost_gbp,
                    "fueleu_cb_t": feu.compliance_balance_tco2e,
                    "fueleu_penalty_eur": feu.penalty_eur,
                    "lever_saving_eur": round(lever_saving),
                    "co2_per_nm_kg": round(cpd, 1) if cpd else None,
                    "supported": True})
        cands.append(PoolCandidate(imo, rec.name, feu.compliance_balance_tco2e,
                                   feu.ghg_intensity))
    pool = suggest_pool(cands) if cands else None
    return {"source": _EXPORT_NAME, "vessels": out,
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
def siblings(imo: str, limit: int = 60):
    """The selected ship's company fleet ('related ships') with the
    verified carbon-intensity-per-mile of each — chart fodder. CO2/nm is
    the honest cross-ship axis: a true CII per sibling would need each
    ship's DWT, which the public export lacks."""
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
                sfoc_me: float = Query(175.0, gt=0),
                sfoc_ae: float = Query(215.0, gt=0)):
    """FREE custom-vessel EEXI: any ship, no registry needed. Either supply
    the attained EEXI, or MCR + service speed to estimate it (simplified
    EEDI formula, assumptions returned in notes)."""
    from ghgcore.eexi import compute_eexi_custom
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
def audit(imo: str, dwt: float = Query(gt=0), year: Optional[int] = None):
    """Verifier-ready calculation worksheet: inputs, every parameter used
    (with source citation), intermediates, results."""
    from ghgcore.audit import build_audit
    rec = records().get(imo)
    if rec is None:
        raise HTTPException(404, f"IMO {imo} was not found in the public EU MRV register.")
    if privacy.is_suppressed(imo):
        raise HTTPException(403, privacy.SUPPRESSION_NOTE)
    if rec.ship_type is None:
        raise HTTPException(422, _unsupported(rec.ship_type_raw))
    y = year or rec.reporting_period or 2025
    return build_audit(record_to_activity(rec, year=y, dwt=dwt), estimate=True)


@app.get("/api/method")
def method():
    """The Method/trust page content: calculation notes markdown."""
    p = os.path.join(os.path.dirname(__file__), "..", "docs", "CALCULATION_NOTES.md")
    with open(p, encoding="utf-8") as f:
        return PlainTextResponse(f.read(), media_type="text/markdown")


def _require_key(key: Optional[str]) -> str:
    from ghgcore import access
    if not access.is_valid(key):
        raise HTTPException(401, "This tool is for ship operators. Enter your "
                                 "access key, or ask us for one. We issue keys to "
                                 "operators and design partners.")
    return access.label_for(key)


@app.get("/api/access/check")
def access_check(key: str = Query(...)):
    """Validate an access key (used by the UI unlock screen)."""
    label = _require_key(key)
    return {"ok": True, "issued_to": label}


class SpeedIn(BaseModel):
    ref_cons_t_per_day: float
    ref_speed_kn: float
    actual_speed_kn: float
    sea_days: float
    aux_t_per_day_at_sea: float = 0.0
    port_days: float = 0.0
    aux_t_per_day_in_port: float = 0.0
    main_fuel: FuelType = FuelType.HFO
    aux_fuel: FuelType = FuelType.MDO_MGO


class CIIIn(BaseModel):
    ship_type: ShipType
    dwt: float = 0.0
    gt: float = 0.0
    year: int = 2026
    fuel_tonnes: dict[FuelType, float] = {}
    distance_nm: float = 0.0
    speed: Optional[SpeedIn] = None
    # G5 (documented operator values only)
    excluded_co2_t: float = 0.0
    excluded_distance_nm: float = 0.0
    capacity_correction: float = 1.0
    corrections_basis: str = ""
    vessel_name: str = ""
    imo_number: str = ""


@app.post("/api/cii/compute")
def cii_compute(inp: CIIIn, key: Optional[str] = Query(None),
                request: Request = None):
    """LOCKED — owner-data CII calculation (G1–G5) with forward trajectory."""
    _require_key(key)
    from ghgcore.cii_calc import CIIInput, SpeedProfile, compute_cii_full
    from ghgcore.cii import CIICorrections
    sp = None
    if inp.speed is not None:
        sp = SpeedProfile(**inp.speed.model_dump())
    corr = None
    if (inp.excluded_co2_t or inp.excluded_distance_nm
            or inp.capacity_correction != 1.0):
        corr = CIICorrections(inp.excluded_co2_t, inp.excluded_distance_nm,
                              inp.capacity_correction, inp.corrections_basis)
    try:
        res = compute_cii_full(CIIInput(
            ship_type=inp.ship_type, dwt=inp.dwt, gt=inp.gt, year=inp.year,
            fuel_tonnes={k: v for k, v in inp.fuel_tonnes.items() if v > 0},
            distance_nm=inp.distance_nm, speed_profile=sp, corrections=corr,
            vessel_name=inp.vessel_name, imo_number=inp.imo_number))
    except (ValueError, KeyError) as e:
        raise HTTPException(422, str(e))
    return asdict(res)


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
    """Per-vessel derived figures must not be indexed: searching an operator's
    ship name should never surface our estimate of their compliance bill."""
    return PlainTextResponse(
        "User-agent: *\n"
        "Disallow: /api/\n"
        "Disallow: /report\n"
        "Allow: /$\n")


class ClaimIn(BaseModel):
    kind: str                    # claim | correct | suppress
    imos: list[str]
    company: str = ""
    contact_email: str
    message: str = ""


@app.post("/api/claim")
def claim(inp: ClaimIn, request: Request = None):
    """Operator control: claim vessels, correct our figures, or suppress our
    derived estimates. Suppression is applied straight away — we do not make an
    operator wait for a human to action a 'stop showing my data' request. It is
    then made permanent by the operator of the service (see
    CARBONKEEL_SUPPRESSED_IMOS), because a free host can lose local files."""
    _guard(request)
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
    return {"ok": True, "kind": req.kind, "imos": req.imos, "message": msg}


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
def pool_agreement(imos: str = Query(min_length=7), year: int = 2026,
                   organiser: str = "[ORGANISER LEGAL NAME]"):
    """Draft Art. 21 pooling agreement (markdown) for the given fleet."""
    from fastapi.responses import PlainTextResponse
    from ghgcore.pooling import PoolCandidate, suggest_pool
    from ghgcore.pool_agreement import draft_agreement
    recs = records()
    cands = []
    for imo in _parse_imos(imos):
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
def report(imos: str = Query(min_length=7), year: Optional[int] = None,
           request: Request = None):
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
    return HTMLResponse(fleet_report_html(records(), wanted, year))


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
    distance_nm: float
    fuel: dict[FuelType, float]        # tonnes by fuel type
    uk_share: Optional[float] = None


class ScoreIn(BaseModel):
    imo: str
    name: str
    ship_type: ShipType
    dwt: float
    gt: float = 0.0
    year: int
    legs: list[LegIn]
    eua_price: float = 70.0
    nzf_year: int = 2028


@app.post("/api/score")
def score(inp: ScoreIn):
    vessel = Vessel(inp.imo, inp.name, inp.ship_type, dwt=inp.dwt, gt=inp.gt)
    legs = [VoyageLeg(l.scope, l.distance_nm,
                      [FuelConsumption(f, t) for f, t in l.fuel.items() if t > 0],
                      "API input", uk_share=l.uk_share)
            for l in inp.legs]
    sc = build_scorecard(AnnualActivity(vessel, inp.year, legs),
                         eua_price=inp.eua_price, nzf_year=inp.nzf_year)
    return {"estimate": False, "scorecard": asdict(sc)}
