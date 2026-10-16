"""FuelEU Maritime engine — Regulation (EU) 2023/1805.

GHG intensity of energy used onboard (well-to-wake, gCO2e/MJ) vs declining
targets from the 91.16 gCO2e/MJ 2020 baseline. Computes compliance balance,
penalty exposure (Art. 23, Annex IV Part B, with the Art. 23(2) multiplier for
consecutive deficit periods), and what pooling the deficit would cost instead
(Art. 21) at a price the user sets.

Applies from reporting period 2025 to ships above 5,000 GT carrying cargo or
passengers (Art. 2). LCV and WtW values are the Annex II defaults (verified
8 Jul 2026); certified values (Art. 10) override them.
"""
from dataclasses import dataclass
from typing import Optional
from .schema import AnnualActivity, EngineType, FuelType, Vessel, VoyageScope

BASELINE_GCO2E_MJ = 91.16
REDUCTIONS = {2025: 0.02, 2030: 0.06, 2035: 0.145, 2040: 0.31, 2045: 0.62, 2050: 0.80}
PENALTY_EUR_PER_T_VLSFO_EQ = 2400.0
VLSFO_ENERGY_MJ_PER_T = 41_000.0
FUELEU_FIRST_YEAR = 2025
MAX_CONSECUTIVE_YEARS = 20


def penalty_multiplier(consecutive_deficit_years: int) -> float:
    """Art. 23(2): penalty x (1 + (n - 1)/10), n = consecutive reporting periods with a
    FuelEU penalty for the ship, this one included. Resets after a compliant period."""
    n = max(1, min(MAX_CONSECUTIVE_YEARS, int(consecutive_deficit_years or 1)))
    return 1.0 + (n - 1) / 10.0

# (LCV MJ per tonne, WtW gCO2e/MJ). Verified 8 Jul 2026 against Reg. (EU)
# 2023/1805 Annex II default emission factors (EUR-Lex CELEX 32023R1805,
# OJ L 234/90-95): WtW = WtT + (Cf_CO2 + Cf_CH4*25 + Cf_N2O*298)/LCV, with
# LNG methane slip per Annex II column 9 (FuelEU uses AR4 GWP100 25/298 —
# note EU ETS uses AR5 28/265; the regimes intentionally differ).
#   HFO:  LCV 0.0405, WtT 13.5, Cf 3.114/0.00005/0.00018 -> 91.74
#   LFO:  LCV 0.041,  WtT 13.2, Cf 3.151/0.00005/0.00018 -> 91.39
#   MGO:  LCV 0.0427, WtT 14.4, Cf 3.206/0.00005/0.00018 -> 90.77
#   LNG (Otto dual-fuel medium speed, 3.1% slip): LCV 0.0491, WtT 18.5,
#     (0.969*(2.750+0.00011*298) + 0.031*25)/0.0491 + 18.5 -> 89.20
#     (slow-speed Otto 1.7% / Diesel DF 0.2% / LBSI 2.6% differ — engine
#     type must refine this in production)
#   Methanol (fossil NG): LCV 0.0199, WtT 31.3, Cf 1.375 + class-default
#     CH4/N2O per the TBM rule -> 103.15
#   Biofuels: WtT = E - Cf_CO2/LCV per RED II; B100 uses the UCOME-class
#     default E (pathway/certificate-specific — VERIFY per actual BDN)
FUEL_PROPS = {
    FuelType.HFO:        (40_500.0, 91.74),
    FuelType.LFO:        (41_000.0, 91.39),
    FuelType.MDO_MGO:    (42_700.0, 90.77),
    FuelType.LNG:        (49_100.0, 89.20),   # Otto DF medium-speed default
    FuelType.METHANOL:   (19_900.0, 103.15),  # fossil; e-MeOH far lower
    FuelType.BIOFUEL_B24: (40_040.0, 74.8),   # 24% UCOME/76% LFO, energy-weighted
    FuelType.BIOFUEL_B100: (37_000.0, 16.4),  # UCOME default pathway — VERIFY per BDN
}

# LNG WtW by consumer-unit class (Annex II col. 9 slip; same computation as
# above with slip 3.1/1.7/0.2/2.6%):
LNG_WTW_BY_ENGINE = {
    EngineType.OTTO_MS: 89.20,
    EngineType.OTTO_SS: 82.87,
    EngineType.DIESEL_DF: 76.08,
    EngineType.LBSI: 86.94,
}


def resolve_props(fuel: FuelType, vessel: Optional[Vessel] = None,
                  overrides: Optional[dict] = None) -> tuple[float, float]:
    """(LCV MJ/t, WtW gCO2e/MJ) for a fuel: certified override (Art. 10(4)/(5))
    first, then engine-specific LNG default, then Annex II default."""
    if overrides and fuel in overrides:
        return overrides[fuel]
    if fuel == FuelType.LNG and vessel is not None:
        return FUEL_PROPS[fuel][0], LNG_WTW_BY_ENGINE[vessel.engine_type]
    return FUEL_PROPS[fuel]


def target_intensity(year: int) -> float:
    red = 0.0
    for y in sorted(REDUCTIONS):
        if year >= y:
            red = REDUCTIONS[y]
    return BASELINE_GCO2E_MJ * (1 - red)


@dataclass
class FuelEUResult:
    ghg_intensity: float          # attained gCO2e/MJ (EU-scoped energy)
    target: float
    energy_mj: float              # EU-scoped energy
    compliance_balance_gco2e: float   # + surplus / - deficit
    compliance_balance_tco2e: float
    penalty_eur: float            # statutory penalty if the deficit is neither pooled nor borrowed
    surplus_value_note: str
    notes: list[str]
    applicable: bool = True
    penalty_multiplier: float = 1.0
    penalty_eur_per_tco2e: float = 0.0          # statutory cost of one tCO2e of deficit
    pool_price_eur_per_tco2e: Optional[float] = None
    pooling_cost_eur: Optional[float] = None    # deficit bought from a pool at that price


def _scope_share(scope: VoyageScope) -> float:
    return {VoyageScope.INTRA_EEA: 1.0, VoyageScope.AT_BERTH_EEA: 1.0,
            VoyageScope.EXTRA_EEA: 0.5, VoyageScope.OUT_OF_SCOPE: 0.0}[scope]


def _not_applicable(activity: AnnualActivity, reason: str, notes: list[str]) -> FuelEUResult:
    return FuelEUResult(0, round(target_intensity(activity.year), 2), 0, 0, 0, 0,
                        reason, notes + [reason], applicable=False)


def compute_fueleu(activity: AnnualActivity,
                   certified_props: Optional[dict] = None,
                   consecutive_deficit_years: int = 1,
                   pool_price_eur_per_tco2e: Optional[float] = None) -> FuelEUResult:
    """certified_props: {FuelType: (lcv_mj_per_t, wtw_gco2e_per_mj)} — actual
    certified values per Art. 10(4)/(5) (e.g. from the biofuel's BDN/PoS);
    they override the Annex II defaults for this computation."""
    notes = ["Fuel energy content (lower calorific value, LCV) and well-to-wake (WtW) values are the "
             "defaults in Regulation (EU) 2023/1805, Annex II (verified). For biofuel, use the "
             "certified pathway values (Article 10)."]
    if certified_props:
        notes.append(f"Certified values supplied for: "
                     f"{', '.join(f.value for f in certified_props)} (Art. 10).")
    if activity.year < FUELEU_FIRST_YEAR:
        return _not_applicable(activity, f"FuelEU Maritime applies from 1 January {FUELEU_FIRST_YEAR}, "
                                         f"so {activity.year} carries no FuelEU obligation.", notes)
    if activity.ets_calibration == 0:
        return _not_applicable(activity, "Not in FuelEU scope on the public record: the verifier reported "
                                         "no EU ETS-scope emissions for this ship. FuelEU covers ships above "
                                         "5,000 GT carrying cargo or passengers, the same ships the maritime "
                                         "ETS covers, so this ship is most likely smaller, an offshore ship, "
                                         "or exempt. Check its gross tonnage.", notes)
    energy = 0.0
    emissions = 0.0  # gCO2e
    for leg in activity.legs:
        share = _scope_share(leg.scope)
        if share == 0:
            continue
        for fc in leg.fuel_consumed:
            lcv, wtw = resolve_props(fc.fuel, activity.vessel, certified_props)
            e = fc.tonnes * lcv * share       # MJ in scope
            energy += e
            emissions += e * wtw

    if energy == 0:
        return _not_applicable(activity, "No energy used on EU-scope voyages or at EU berths, so "
                                         "FuelEU does not apply this year.", notes)

    intensity = emissions / energy
    tgt = target_intensity(activity.year)
    cb_g = (tgt - intensity) * energy          # Annex IV: CB = (target - actual) x energy
    cb_t = cb_g / 1e6
    per_t = penalty_per_tco2e(intensity)
    mult = penalty_multiplier(consecutive_deficit_years)

    penalty, pool_cost = 0.0, None
    if cb_g < 0:
        # Annex IV Part B: |CB| / (GHGIE_actual x 41,000) x EUR 2,400; Art. 23(2) multiplier
        penalty = penalty_equiv(cb_g, intensity) * mult
        if mult > 1:
            notes.append(f"Penalty multiplied by {mult:g} for {int(consecutive_deficit_years)} consecutive "
                         f"periods with a FuelEU penalty (Art. 23(2): 1 + (n - 1)/10).")
        if pool_price_eur_per_tco2e is not None:
            pool_cost = abs(cb_t) * pool_price_eur_per_tco2e
            notes.append(f"Pooling instead: {abs(cb_t):,.1f} tCO₂e bought at €{pool_price_eur_per_tco2e:,.0f} "
                         f"per tonne is €{pool_cost:,.0f}, against a statutory €{per_t * mult:,.0f} per tonne. "
                         f"Pool prices are negotiated; check yours.")

    if cb_t > 0:
        val = ("A surplus can be banked (Article 20) or pooled (Article 21). Its market value is "
               "negotiated and cannot exceed the penalty the other party avoids "
               f"(≈€{penalty_equiv(cb_g, intensity):,.0f} if they paid instead).")
    else:
        val = ("A deficit can be pooled with a surplus ship (Article 21), part-borrowed from next "
               "year with 10% added (Article 20), or paid as a penalty.")

    return FuelEUResult(round(intensity, 2), round(tgt, 2), round(energy, 0),
                        round(cb_g, 0), round(cb_t, 1), round(penalty, 0), val, notes,
                        applicable=True, penalty_multiplier=mult,
                        penalty_eur_per_tco2e=round(per_t, 2),
                        pool_price_eur_per_tco2e=pool_price_eur_per_tco2e,
                        pooling_cost_eur=None if pool_cost is None else round(pool_cost, 0))


def penalty_equiv(cb_g: float, intensity: float) -> float:
    return abs(cb_g) / (intensity * VLSFO_ENERGY_MJ_PER_T) * PENALTY_EUR_PER_T_VLSFO_EQ


def penalty_per_tco2e(intensity: float) -> float:
    """Statutory penalty per tonne CO2e of deficit at this intensity (before Art. 23(2))."""
    return 1e6 / (intensity * VLSFO_ENERGY_MJ_PER_T) * PENALTY_EUR_PER_T_VLSFO_EQ if intensity else 0.0
