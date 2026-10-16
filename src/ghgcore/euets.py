"""EU ETS maritime engine: Directive 2003/87/EC as amended by Directive (EU) 2023/959.

Scope (Art. 3ga): 100% of emissions on voyages between ports of Member States and
within ports; 50% of emissions on voyages into or out of the Union. Ships of 5,000 GT
and above (Reg. 2015/757 Art. 2). Offshore ships of 5,000 GT and above join the ETS
from 2027 (Annex I excludes them until 31 Dec 2026); cargo ships of 400 to 5,000 GT
and offshore ships below 5,000 GT report under the MRV Regulation but are outside
the ETS.

Surrender (Art. 3gb, Art. 12(3)): 40% of 2024 emissions, 70% of 2025, 100% from 2026,
by 30 September of the following year. Gases: CO2 from 2024; CH4 and N2O from 2026.
Exceptions (Art. 12(3-b) to (3-e)): see `ETSExceptions`.

The monitoring formula and the shared constants are in `ets_rules.py`.

Public-register path. The register publishes, for each ship, the verifier's own
"CO2 emissions to be reported under Directive 2003/87/EC". That figure already reflects
everything we cannot see (ports of call, transhipment stops, ship size, derogations),
so when it is available the engine scales its rebuild to it (`activity.ets_calibration`)
and the rebuild is kept only as a cross-check.
"""
from dataclasses import dataclass, field
from typing import Optional

from .schema import AnnualActivity, VoyageScope
from .ets_rules import (GWP_CH4, GWP_N2O, NON_CO2_EF, LNG_SLIP_BY_ENGINE, PHASE_IN,  # noqa: F401  (re-exported)
                        EU_NON_CO2_FROM_YEAR, EU_DEROGATIONS_END_YEAR, EU_FIRST_SURRENDER_YEAR,
                        ICE_CLASS_DISCOUNT, EU_EXCESS_PENALTY_EUR_PER_T, ETSExceptions,
                        eu_phase_in, gas_emissions, non_co2 as _non_co2_new)
from .schema import EngineType, FuelType
from .assumptions import DEFAULT_EUA_PRICE_EUR

SCOPE_SHARE = {VoyageScope.INTRA_EEA: 1.0, VoyageScope.AT_BERTH_EEA: 1.0,
               VoyageScope.EXTRA_EEA: 0.5, VoyageScope.OUT_OF_SCOPE: 0.0}


def _non_co2(fuel: FuelType, engine: EngineType) -> tuple:
    """(CH4, N2O) per tonne of fuel including LNG slip as methane, for older callers."""
    ch4, n2o = NON_CO2_EF[fuel]
    if fuel == FuelType.LNG:
        ch4 = LNG_SLIP_BY_ENGINE[engine]
    return ch4, n2o


@dataclass
class ETSResult:
    co2e_in_scope_t: float         # emissions in scope for the year, before phase-in
    surrender_share: float         # phase-in (0 before 2024)
    allowances_due: float          # EUAs, after phase-in and any exceptions
    cost_eur: float
    eua_price_used: float
    notes: list[str]
    basis: str = "rebuilt"         # "verifier" when scaled to the verifier-reported figure
    rebuilt_co2e_t: float = 0.0    # our own rebuild, before any scaling
    calibration: Optional[float] = None
    exceptions_applied: list[str] = field(default_factory=list)
    surrender_by: str = ""
    excess_penalty_eur_per_t: float = EU_EXCESS_PENALTY_EUR_PER_T


def compute_ets(activity: AnnualActivity, eua_price_eur: float = DEFAULT_EUA_PRICE_EUR,
                exceptions: Optional[ETSExceptions] = None) -> ETSResult:
    notes: list[str] = []
    year = activity.year
    exc = (exceptions or ETSExceptions()).clean()
    include_non_co2 = year >= EU_NON_CO2_FROM_YEAR
    if year < EU_FIRST_SURRENDER_YEAR:
        notes.append(f"{year} emissions carry no EU ETS surrender obligation: the maritime scheme "
                     f"starts with 2024 emissions (40%).")
    elif not include_non_co2:
        notes.append("Before 2026 only CO₂ is in the ETS scope; from 2026 methane and nitrous oxide count too.")

    rebuilt = 0.0
    for leg in activity.legs:
        share = SCOPE_SHARE[leg.scope]
        if share == 0:
            continue
        for fc in leg.fuel_consumed:
            g = gas_emissions(fc.fuel, fc.tonnes * share, activity.vessel.engine_type,
                              activity.fuel_is_combusted)
            rebuilt += g.co2e(include_non_co2)

    co2e, basis, k = rebuilt, "rebuilt", activity.ets_calibration
    if k is not None:
        co2e, basis = rebuilt * k, "verifier"
        if k == 0:
            notes.append("This ship reported no ETS-scope emissions to EMSA for this year, so no "
                         "allowances are due. Likely reasons: it is below 5,000 GT (smaller cargo "
                         "ships report under EU MRV from 2025 but are outside the ETS), it is an "
                         "offshore ship (in the ETS from 2027), or it is exempt.")
        else:
            notes.append("Scope CO₂ is the figure the ship’s verifier reported to EMSA, which already "
                         "reflects ports of call, transhipment stops, ship size and derogations. Our own "
                         "rebuild from the scope split is shown only as a cross-check.")

    surrender = eu_phase_in(year)
    factor, applied = 1.0, []
    if year <= EU_DEROGATIONS_END_YEAR:
        if exc.derogation_share > 0:
            factor *= 1.0 - exc.derogation_share
            applied.append(f"derogation on {exc.derogation_share * 100:.0f}% of in-scope emissions "
                           f"(Art. 12(3-b) to (3-d), until 31 Dec 2030)")
        if exc.ice_class_ia:
            factor *= 1.0 - ICE_CLASS_DISCOUNT
            applied.append("ice class IA or IA Super: 5% fewer allowances (Art. 12(3-e), until 31 Dec 2030)")
    elif exc.derogation_share > 0 or exc.ice_class_ia:
        notes.append(f"The exceptions in Article 12(3-b) to (3-e) end on 31 December {EU_DEROGATIONS_END_YEAR}; "
                     f"they are ignored for {year}.")

    allowances = co2e * surrender * factor
    notes.append("Sustainable biofuel can be zero-rated if it is certified under the Renewable "
                 "Energy Directive (RED). In what-if scenarios 100% biofuel (B100) is counted as "
                 "zero-rated, which assumes it is certified; every other fuel uses its fossil "
                 "emission factor.")
    notes.append(f"If allowances are not surrendered by 30 September, the excess emissions penalty is "
                 f"€{EU_EXCESS_PENALTY_EUR_PER_T:.0f} per tonne of CO₂e (indexed to inflation) and the "
                 f"allowances are still owed.")
    return ETSResult(round(co2e, 1), surrender, round(allowances, 1),
                     round(allowances * eua_price_eur, 0), eua_price_eur, notes,
                     basis=basis, rebuilt_co2e_t=round(rebuilt, 1), calibration=k,
                     exceptions_applied=applied, surrender_by=f"30 September {year + 1}")
