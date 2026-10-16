"""IMO Net-Zero Framework scenario engine (draft Chapter 5, MARPOL Annex VI).

STATUS: approved in principle at MEPC 83 (Apr 2025); on 17 Oct 2025 the extraordinary
session voted to adjourn adoption for one year. Not adopted as of 17 Oct 2026 (re-check
imo.org; reported dates for the vote differ). All parameters are configurable because the
final text may change.

Mechanics (as approved): GFI (well-to-wake gCO2e/MJ) vs two declining targets
from the 93.3 gCO2e/MJ 2008 reference:
- above Base target        -> Tier 2 remedial units @ ~$380/tCO2e
- between Base and Direct  -> Tier 1 remedial units @ ~$100/tCO2e
- below Direct target      -> earns Surplus Units (bankable/transferable)
"""
from dataclasses import dataclass
from .schema import AnnualActivity, VoyageScope
from .fueleu import FUEL_PROPS

GFI_REFERENCE = 93.3  # gCO2e/MJ, 2008 fleet average

# % reductions vs reference (as approved MEPC 83; VERIFY against final adopted text)
BASE_TARGET = {2028: 4, 2029: 6, 2030: 8, 2031: 12.4, 2032: 16.8,
               2033: 21.2, 2034: 25.6, 2035: 30}
DIRECT_TARGET = {2028: 17, 2029: 19, 2030: 21, 2031: 25.4, 2032: 29.8,
                 2033: 34.2, 2034: 38.6, 2035: 43}

RU_TIER1_USD = 100.0
RU_TIER2_USD = 380.0

NZF_STATUS = ("Not adopted. The IMO postponed the adoption decision by one year in "
              "October 2025; the vote is due in late 2026.")


@dataclass
class NZFResult:
    year: int
    attained_gfi: float
    base_target: float
    direct_target: float
    tier1_deficit_tco2e: float
    tier2_deficit_tco2e: float
    surplus_units_tco2e: float
    remedial_cost_usd: float
    notes: list[str]


def compute_nzf(activity: AnnualActivity, scenario_year: int = 2028) -> NZFResult:
    """Applies the vessel's current fuel mix to a future NZF compliance year.

    NZF scope = ALL international energy (not just EU) — we include every leg.
    """
    notes = ["IMO Net-Zero Framework (NZF): scenario only. " + NZF_STATUS,
             "Well-to-wake fuel values here are provisional defaults. The final regime will use the "
             "IMO life-cycle assessment guidelines (MEPC.391(81))."]
    energy = 0.0
    emissions = 0.0
    for leg in activity.legs:
        if leg.scope == VoyageScope.AT_BERTH_EEA:
            pass  # berth energy still counts globally
        for fc in leg.fuel_consumed:
            lcv, wtw = FUEL_PROPS[fc.fuel]
            energy += fc.tonnes * lcv
            emissions += fc.tonnes * lcv * wtw

    gfi = emissions / energy if energy else 0.0
    base = GFI_REFERENCE * (1 - BASE_TARGET[scenario_year] / 100)
    direct = GFI_REFERENCE * (1 - DIRECT_TARGET[scenario_year] / 100)

    tier1 = tier2 = surplus = 0.0
    if gfi > base:
        tier2 = (gfi - base) * energy / 1e6
        tier1 = (base - direct) * energy / 1e6
    elif gfi > direct:
        tier1 = (gfi - direct) * energy / 1e6
    else:
        surplus = (direct - gfi) * energy / 1e6

    cost = tier1 * RU_TIER1_USD + tier2 * RU_TIER2_USD
    return NZFResult(scenario_year, round(gfi, 2), round(base, 2), round(direct, 2),
                     round(tier1, 1), round(tier2, 1), round(surplus, 1),
                     round(cost, 0), notes)
