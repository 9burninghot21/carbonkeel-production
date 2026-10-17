"""Audit worksheet — every number's provenance, for verifier scrutiny.

build_audit() returns a plain dict: the exact inputs, every regulatory
parameter used (with its source), the intermediate values, and the results.
Architecture rule 1 made this possible: engines are deterministic, so the
worksheet IS the calculation, restated.
"""
from dataclasses import asdict
from .schema import AnnualActivity, FuelType, ShipType
from . import cii as cii_mod
from . import fueleu as feu_mod
from . import euets as ets_mod
from .scorecard import build_scorecard
from .assumptions import DEFAULT_EUA_PRICE_EUR

SOURCES = {
    "cf": "CF factors: 2018 DCS Guidelines / MEPC.352(78) (G1)",
    "g2": "Reference lines: MEPC.353(78) Annex 15 Table 1 (verified 8 Jul 2026)",
    "g3": "Z factors: MEPC.338(76) as amended by MEPC.400(83)",
    "g4": "Rating boundaries: MEPC.354(78) Annex 16 Table 1 (verified 8 Jul 2026)",
    "fueleu": "Reg. (EU) 2023/1805: baseline 91.16 gCO2e/MJ (Art. 4, Annex I); fuel LCV and "
              "WtW = Annex II defaults (verified 8 Jul 2026); penalty Art. 23 and Annex IV Part B, "
              "EUR 2,400 per t VLSFO-equivalent, x (1 + (n-1)/10) for consecutive deficits (Art. 23(2))",
    "ets": "Directive 2003/87/EC: scope Art. 3ga, phase-in 40/70/100% Art. 3gb, CH4/N2O from 2026 "
           "(Annex I; GWP100 28/265, Delegated Reg. 2020/1044); emission factors and slip from "
           "Reg. 2015/757 Annex I Part A as amended by Delegated Reg. 2023/2776",
    "ukets": "SI 2026/392 Schedule 2A: domestic voyages and UK berths, GB<->NI 50%, "
             "CO2+CH4+N2O, no phase-in",
    "nzf": "IMO Net-Zero Framework as approved at MEPC 83 (SCENARIO: not adopted)",
}


def build_audit(activity: AnnualActivity, eua_price: float = DEFAULT_EUA_PRICE_EUR,
                nzf_year: int = 2028, estimate: bool = False) -> dict:
    v = activity.vessel
    sc = build_scorecard(activity, eua_price=eua_price, nzf_year=nzf_year)

    fuel_totals = {f.value: round(t, 3)
                   for f, t in activity.total_fuel_by_type().items()}
    a, c = cii_mod._g2_params(v.ship_type, v.dwt, v.gt)
    dd = cii_mod._dd(v.ship_type, v.dwt)
    capacity, ref_capacity = cii_mod._capacities(v.ship_type, v.dwt, v.gt)

    return {
        "meta": {
            "generated_by": "CarbonKeel calculation engines v0.3 — deterministic; "
                            "touches any figure in this worksheet",
            "estimate": estimate,
            "eua_price_assumption_eur": eua_price,
        },
        "inputs": {
            "vessel": asdict(v),
            "year": activity.year,
            "legs": [asdict(l) for l in activity.legs],
            "fuel_totals_t": fuel_totals,
            "total_distance_nm": activity.total_distance_nm,
        },
        "parameters_used": {
            "cf_tco2_per_t": {f.value: cii_mod.CF_TCO2_PER_T[f]
                              for f in activity.total_fuel_by_type()},
            "g2_reference_line": {"a": a, "c": c, "capacity": capacity,
                                  "reference_capacity": ref_capacity},
            "g3_z_factor_pct": sc.cii.z_factor_pct,
            "g4_dd_vector": dd,
            "fueleu": {
                "baseline_gco2e_mj": feu_mod.BASELINE_GCO2E_MJ,
                "target_gco2e_mj": sc.fueleu.target,
                "penalty_rate": feu_mod.PENALTY_EUR_PER_T_VLSFO_EQ,
                "fuel_props_lcv_wtw": {f.value: feu_mod.FUEL_PROPS[f]
                                       for f in activity.total_fuel_by_type()},
            },
            "ets": {
                "surrender_share": sc.ets.surrender_share,
                "non_co2_ef": {f.value: ets_mod.NON_CO2_EF[f]
                               for f in activity.total_fuel_by_type()},
            },
            "sources": SOURCES,
        },
        "intermediates": {
            "co2_tonnes": sc.cii.co2_tonnes,
            "cii_reference": sc.cii.reference,
            "cii_required": sc.cii.required,
            "fueleu_energy_mj": sc.fueleu.energy_mj,
            "fueleu_intensity": sc.fueleu.ghg_intensity,
            "ets_co2e_in_scope_t": sc.ets.co2e_in_scope_t,
        },
        "results": asdict(sc),
    }
