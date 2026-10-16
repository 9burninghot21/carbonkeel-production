"""CII calculator — the owner-data tool (locked feature).

The free lookup reconstructs a CII from public data and is labelled ESTIMATE.
This module is the other half: the operator supplies their own numbers, so
the result is an owner-data computation that follows the IMO guideline set
end to end.

Rule set implemented
--------------------
G1  MEPC.352(78)  attained CII = Σ(FC_j × CF_j) / (Capacity × Distance)
G2  MEPC.353(78)  reference line  CII_ref = a × Capacity^(-c)
G3  MEPC.338(76)/MEPC.400(83)  required CII = ref × (1 − Z/100)
G4  MEPC.354(78)  A–E boundaries via the dd vector
G5  MEPC.355(78)  voyage adjustments & correction factors — applied from
                  operator-supplied, documented values (we never invent one)

Two ways in
-----------
1. **Actual fuel** — tonnes per fuel type from BDNs/noon reports. Preferred.
2. **Speed-based estimate** — when fuel is not to hand, a power law against a
   known reference point (sea-trial or charter-party description):
   main-engine consumption/day scales with (V/V_ref)^n, n = 3 by default
   (the cube law) and adjustable, since eco-ships and ships with a power
   limitation often sit between about 2.6 and 3.5. Auxiliary and port
   consumption are added flat per day. Clearly labelled as an estimate.

Beyond the rating, the value is in the forward view: the Z factor tightens
every year to 2030, so a vessel that is C today can be E in 2029 without
changing anything. `trajectory` shows that, and `reduction_to_reach` says
how much CO₂ has to come out to hold a target band.
"""
from dataclasses import dataclass, field
from typing import Optional

from .schema import FuelType, ShipType, Vessel
from .cii import (CF_TCO2_PER_T, Z_FACTORS, CIICorrections, _capacities,
                  _dd, _g2_params)
from .g5 import G5Input, apply_g5

RATING_ORDER = ["A", "B", "C", "D", "E"]
SPEED_EXPONENT_RANGE = (2.0, 4.5)


# ---------------------------------------------------------------- inputs --
@dataclass
class SpeedProfile:
    """Fuel estimation from a known reference consumption point.

    ref_cons_t_per_day @ ref_speed_kn comes from the vessel's sea-trial
    curve or charter-party description. Cube law: the main-engine daily
    consumption scales with the cube of the speed ratio.
    """
    ref_cons_t_per_day: float
    ref_speed_kn: float
    actual_speed_kn: float
    sea_days: float
    aux_t_per_day_at_sea: float = 0.0
    port_days: float = 0.0
    aux_t_per_day_in_port: float = 0.0
    main_fuel: FuelType = FuelType.HFO
    aux_fuel: FuelType = FuelType.MDO_MGO
    speed_exponent: float = 3.0

    def resolve(self) -> tuple[dict, float, list[str]]:
        """-> ({fuel: tonnes}, distance_nm, notes)"""
        for name, v in (("ref_cons_t_per_day", self.ref_cons_t_per_day),
                        ("ref_speed_kn", self.ref_speed_kn),
                        ("actual_speed_kn", self.actual_speed_kn)):
            if v <= 0:
                raise ValueError(f"{name} must be positive")
        if self.sea_days <= 0:
            raise ValueError("sea_days must be positive")
        lo, hi = SPEED_EXPONENT_RANGE
        if not lo <= self.speed_exponent <= hi:
            raise ValueError(f"speed exponent must be between {lo} and {hi}")
        n = self.speed_exponent
        ratio = self.actual_speed_kn / self.ref_speed_kn
        me_per_day = self.ref_cons_t_per_day * ratio ** n
        me_total = me_per_day * self.sea_days
        aux_total = (self.aux_t_per_day_at_sea * self.sea_days
                     + self.aux_t_per_day_in_port * self.port_days)
        distance = self.actual_speed_kn * 24.0 * self.sea_days
        fuels: dict = {}
        fuels[self.main_fuel] = fuels.get(self.main_fuel, 0.0) + me_total
        if aux_total > 0:
            fuels[self.aux_fuel] = fuels.get(self.aux_fuel, 0.0) + aux_total
        notes = [
            f"Fuel ESTIMATED from speed: {me_per_day:,.1f} t/day at "
            f"{self.actual_speed_kn} kn ({'cube law' if n == 3 else f'speed exponent {n:g}'} from "
            f"{self.ref_cons_t_per_day} t/day at {self.ref_speed_kn} kn) × {self.sea_days:g} sea days "
            f"= {me_total:,.1f} t main engine.",
            f"Distance derived as speed × 24 × sea days = {distance:,.0f} nm; "
            "replace with logged distance when available.",
        ]
        if aux_total > 0:
            notes.append(f"Auxiliary/boiler added flat: {aux_total:,.1f} t.")
        return fuels, distance, notes


@dataclass
class CIIInput:
    ship_type: ShipType
    dwt: float = 0.0
    gt: float = 0.0
    year: int = 2026
    # option 1: actual consumption
    fuel_tonnes: dict = field(default_factory=dict)   # {FuelType: tonnes}
    distance_nm: float = 0.0
    # option 2: estimate from speed
    speed_profile: Optional[SpeedProfile] = None
    # G5: either the summary form (CIICorrections) or the itemised MEPC.355(78) form (G5Input)
    corrections: Optional[CIICorrections] = None
    imo_number: str = ""
    vessel_name: str = ""
    g5: Optional[G5Input] = None


# --------------------------------------------------------------- results --
@dataclass
class YearPoint:
    year: int
    z_factor_pct: float
    required: float
    rating: str
    ratio: float


@dataclass
class CIIComputation:
    vessel_name: str
    imo_number: str
    ship_type: str
    year: int
    capacity: float
    capacity_basis: str          # "DWT" | "GT"
    distance_nm: float
    fuel_tonnes: dict            # {fuel value: tonnes}
    co2_tonnes: float
    attained: float
    reference: float
    required: float
    z_factor_pct: float
    rating: str
    ratio: float
    boundaries: dict             # {"A": x, ...} absolute gCO2/cap-nm
    gap_to_next_band_pct: Optional[float]   # % CO2 cut to improve one band
    reduction_to_reach: dict     # {"A": %, "B": %, "C": %, "D": %}
    trajectory: list             # [YearPoint...] 2023-2030 at this performance
    estimated_inputs: bool       # True when fuel came from the speed model
    notes: list
    g5_lines: list = field(default_factory=list)


def _rating_for(ratio: float, dd) -> str:
    d1, d2, d3, d4 = dd
    if ratio <= d1:
        return "A"
    if ratio <= d2:
        return "B"
    if ratio <= d3:
        return "C"
    if ratio <= d4:
        return "D"
    return "E"


def compute_cii_full(inp: CIIInput) -> CIIComputation:
    notes: list[str] = []
    estimated = False

    # --- resolve fuel & distance (G1 inputs) ---
    fuels = dict(inp.fuel_tonnes or {})
    distance = inp.distance_nm
    if inp.speed_profile is not None and not fuels:
        fuels, est_distance, sp_notes = inp.speed_profile.resolve()
        notes.extend(sp_notes)
        estimated = True
        if distance <= 0:
            distance = est_distance
        else:
            notes.append(f"Logged distance {distance:,.0f} nm used in place of "
                         f"the speed-derived {est_distance:,.0f} nm.")
    if not fuels:
        raise ValueError("Provide fuel_tonnes, or a speed_profile to estimate it.")
    if distance <= 0:
        raise ValueError("distance_nm must be positive (or supply a speed profile).")
    for f, t in fuels.items():
        if t < 0:
            raise ValueError(f"negative fuel quantity for {f}")

    # --- capacity (G1/G2 basis) ---
    capacity, ref_capacity = _capacities(inp.ship_type, inp.dwt, inp.gt)
    basis = "GT" if inp.ship_type.value in (
        "ro_ro", "ro_pax", "cruise", "vehicle_carrier") else "DWT"

    # --- CO2 (G1) ---
    co2_t = sum(t * CF_TCO2_PER_T[f] for f, t in fuels.items())

    # --- G5 corrections, only from documented operator values ---
    corr = inp.corrections
    if corr is not None and inp.g5 is not None:
        raise ValueError("Give G5 corrections either as itemised MEPC.355(78) entries or as "
                         "summary totals, not both.")
    g5_lines: list = []
    attained_for = None
    if inp.g5 is not None:
        dwt = inp.dwt or inp.gt
        fuels0, dist0 = dict(fuels), distance
        g = apply_g5(fuels0, dist0, inp.ship_type, dwt, inp.year, inp.g5)
        co2_t = g.co2_numerator_t
        distance = g.distance_nm
        capacity *= g.denominator_factor
        g5_lines = [vars(x) for x in g.lines]
        notes.extend(g.notes)
        cap0 = capacity

        def attained_for(y: int) -> float:
            gy = apply_g5(fuels0, dist0, inp.ship_type, dwt, y, inp.g5)
            return (gy.co2_numerator_t * 1e6) / (cap0 * gy.distance_nm)
    if corr is not None:
        co2_t = max(0.0, co2_t - corr.excluded_co2_t)
        distance = max(1e-9, distance - corr.excluded_distance_nm)
        capacity *= corr.capacity_correction
        notes.append(
            f"G5 (MEPC.355(78)) applied: −{corr.excluded_co2_t:,.1f} t CO₂, "
            f"−{corr.excluded_distance_nm:,.0f} nm, capacity × "
            f"{corr.capacity_correction}. Basis: "
            f"{corr.basis or 'NOT DOCUMENTED — a verifier will ask'}.")

    attained = (co2_t * 1e6) / (capacity * distance)

    # --- reference & required (G2/G3) ---
    a, c = _g2_params(inp.ship_type, inp.dwt, inp.gt)
    reference = a * ref_capacity ** (-c)
    z = Z_FACTORS.get(inp.year)
    if z is None:
        z = Z_FACTORS[max(Z_FACTORS)]
        notes.append(f"No Z factor published for {inp.year}; using {z}% "
                     "(latest adopted).")
    required = reference * (1 - z / 100)

    # --- rating (G4) ---
    dd = _dd(inp.ship_type, inp.dwt)
    ratio = attained / required
    rating = _rating_for(ratio, dd)
    bounds = {k: round(d * required, 3) for k, d in zip("ABCD", dd)}

    # --- how far to the next band, and to each band ---
    reduction = {}
    for band in "ABCD":
        target = bounds[band]
        pct = (1 - target / attained) * 100 if attained > 0 else 0.0
        reduction[band] = round(max(0.0, pct), 1)
    gap = None
    idx = RATING_ORDER.index(rating)
    if idx > 0:
        better = RATING_ORDER[idx - 1]
        gap = reduction[better]

    # --- forward view: same performance, tightening Z ---
    traj = []
    for y in sorted(Z_FACTORS):
        zy = Z_FACTORS[y]
        req_y = reference * (1 - zy / 100)
        ry = (attained_for(y) if attained_for else attained) / req_y
        traj.append(YearPoint(y, zy, round(req_y, 3), _rating_for(ry, dd),
                              round(ry, 3)))
    worst = traj[-1]
    if worst.rating != rating:
        notes.append(f"At today's performance this vessel is {rating} in "
                     f"{inp.year} but {worst.rating} in {worst.year} — the Z "
                     "factor tightens every year to 2030.")

    if estimated:
        notes.append("Inputs are speed-derived estimates, not measured "
                     "consumption. Replace with BDN/noon-report figures for a "
                     "verifier-grade result.")
    else:
        notes.append("Computed from operator-supplied consumption and distance "
                     "— not a public-data estimate.")

    return CIIComputation(
        vessel_name=inp.vessel_name, imo_number=inp.imo_number,
        ship_type=inp.ship_type.value, year=inp.year,
        capacity=round(capacity, 1), capacity_basis=basis,
        distance_nm=round(distance, 1),
        fuel_tonnes={f.value: round(t, 3) for f, t in fuels.items()},
        co2_tonnes=round(co2_t, 1), attained=round(attained, 3),
        reference=round(reference, 3), required=round(required, 3),
        z_factor_pct=z, rating=rating, ratio=round(ratio, 3),
        boundaries=bounds, gap_to_next_band_pct=gap,
        reduction_to_reach=reduction,
        trajectory=[vars(p) for p in traj],
        estimated_inputs=estimated, notes=notes, g5_lines=g5_lines)
