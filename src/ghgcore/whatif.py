"""Scenario transform for the what-if lever (modelled, always labelled as a scenario).

Speed change s on the same distance:
- main engine: power ~ V^n, so fuel per nautical mile ~ V^(n-1). n = 3 is the cube law;
  ships with a power limitation or modern hull forms often sit nearer 2.6 to 3.5.
- auxiliary engines and boilers at sea burn a roughly constant amount per day, and the
  voyage takes 1/V as long, so their fuel scales with 1/V.
- time at berth does not change with sea speed, so berth legs are left alone.

Biofuel: `biofuel_pct` of each fossil fuel's ENERGY switches to certified B100, with the
replacement tonnage LCV-corrected, so the ship does the same work on more biofuel tonnes.
"""
from .schema import AnnualActivity, FuelConsumption, FuelType, VoyageLeg, VoyageScope

FOSSIL = {FuelType.HFO, FuelType.LFO, FuelType.MDO_MGO}


def sea_fuel_ratio(speed_pct: float, speed_exp: float = 3.0, aux_pct: float = 0.0) -> float:
    v = 1.0 + speed_pct / 100.0
    a = max(0.0, min(100.0, aux_pct)) / 100.0
    return (1.0 - a) * v ** (speed_exp - 1.0) + a / v


def apply_whatif(act: AnnualActivity, biofuel_pct: float = 0.0, speed_pct: float = 0.0,
                 speed_exp: float = 3.0, aux_pct: float = 0.0) -> AnnualActivity:
    from .fueleu import FUEL_PROPS
    sea = sea_fuel_ratio(speed_pct, speed_exp, aux_pct)
    b = max(0.0, min(100.0, biofuel_pct)) / 100.0
    lcv_bio = FUEL_PROPS[FuelType.BIOFUEL_B100][0]
    legs = []
    for leg in act.legs:
        ratio = 1.0 if leg.scope == VoyageScope.AT_BERTH_EEA else sea
        fuels: list[FuelConsumption] = []
        bio = 0.0
        for fc in leg.fuel_consumed:
            t = fc.tonnes * ratio
            if fc.fuel in FOSSIL and b > 0:
                removed = t * b
                bio += removed * FUEL_PROPS[fc.fuel][0] / lcv_bio
                t -= removed
            fuels.append(FuelConsumption(fc.fuel, t))
        if bio > 0:
            fuels.append(FuelConsumption(FuelType.BIOFUEL_B100, bio))
        legs.append(VoyageLeg(leg.scope, leg.distance_nm, fuels,
                              leg.description + " [what-if]", uk_share=leg.uk_share))
    return AnnualActivity(act.vessel, act.year, legs, act.ets_calibration, act.fuel_is_combusted)
