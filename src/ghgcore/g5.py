"""CII correction factors and voyage adjustments — MEPC.355(78), 2022 Interim Guidelines (G5).

Attained CII with G5 (section 4):

    sum_j CF_j * { FC_j - ( FC_voyage,j + TF_j + (0.75 - 0.03*y_i) * (FC_electrical,j + FC_boiler,j + FC_others,j) ) }
    -------------------------------------------------------------------------------------------------------------------
                                 fi * fm * fc * fiVSE * Capacity * (D_t - D_x)

y_i counts from y_2023 = 0. TF_j = (1 - AF_Tanker) * FC_S,j, with
AF_Tanker,STS = 6.1742 * DWT^-0.246 (para 4.2, STS voyages per para 2.8) and
AF_Tanker,Shuttle = 5.6805 * DWT^-0.208 (shuttle tankers with DP, para 2.9; FC_S,j = FC_j).
If TF_j > 0, FC_electrical, FC_boiler and FC_others are not used (para 3.3, 4.2).

Every deduction is checked against the guideline's eligibility rule for the ship type;
the operator still has to hold the evidence (logbook, kWh meters, BAPLIE, ice charts).
"""
from dataclasses import dataclass, field
from typing import Optional

from .schema import FuelType, ShipType
from .cii import CF_TCO2_PER_T

REEFER_DEFAULT_KW = 2.75            # Appendix 1 Part A 1.2: Cx
SFOC_DEFAULT_2_STROKE = 175.0       # g/kWh, ships without a Technical File
SFOC_DEFAULT_4_STROKE = 200.0
AF_STS = (6.1742, 0.246)
AF_SHUTTLE = (5.6805, 0.208)

KINDS = {
    "voyage_safety": ("Voyage adjustment: situation endangering safe navigation (MARPOL Annex VI reg. 3.1)",
                      "G5 para 4.1.1"),
    "voyage_ice": ("Voyage adjustment: ice-classed ship sailing within the ice edge", "G5 para 4.1.2"),
    "electrical_reefer": ("Electrical consumption of refrigerated containers", "G5 para 4.3.1, Appendix 1 Part A.1"),
    "electrical_cooling": ("Cargo cooling or reliquefaction on gas and LNG carriers", "G5 para 4.3.2, Appendix 1 Part A.2"),
    "electrical_discharge": ("Electric cargo discharge pumps on tankers", "G5 para 4.3.3, Appendix 1 Part A.3"),
    "boiler": ("Oil-fired boiler for cargo heating or steam cargo pumps on tankers", "G5 para 4.4, Appendix 1 Part B.1"),
    "others": ("Standalone engine-driven cargo pumps on tankers", "G5 para 4.5, Appendix 1 Part B.2"),
    "sts": ("Ship-to-ship (STS) voyages on tankers", "G5 paras 2.8 and 4.2"),
}
VOYAGE_KINDS = {"voyage_safety", "voyage_ice"}
FACTOR_KINDS = {"electrical_reefer", "electrical_cooling", "electrical_discharge", "boiler", "others"}
TANKER_ONLY = {"electrical_discharge", "boiler", "others", "sts"}
GAS_ONLY = {"electrical_cooling"}
ICE_CLASSES_FM = {"IA", "IA SUPER"}


@dataclass
class G5Deduction:
    kind: str
    fuel: FuelType
    tonnes: float
    distance_nm: float = 0.0      # voyage adjustments only (D_x)
    basis: str = ""


@dataclass
class G5Input:
    deductions: list[G5Deduction] = field(default_factory=list)
    shuttle_tanker: bool = False
    ice_class: str = ""           # "" none, "IA", "IA Super", or another ice class
    fi: float = 1.0               # from the EEDI/EEXI Technical File (para 4.6)
    fm: float = 1.0
    fc: float = 1.0
    fivse: float = 1.0
    self_unloading: bool = False


@dataclass
class G5Line:
    kind: str
    label: str
    source: str
    fuel: str
    tonnes: float
    weight: float                 # 1, the (0.75 - 0.03y) factor, or (1 - AF)
    co2_deducted_t: float
    distance_nm: float


@dataclass
class G5Applied:
    co2_numerator_t: float        # corrected numerator, tonnes CO2
    distance_nm: float            # D_t - D_x
    denominator_factor: float     # fi * fm * fc * fiVSE
    lines: list[G5Line]
    notes: list[str]


def year_factor(year: int) -> float:
    """0.75 - 0.03 * y_i with y_2023 = 0."""
    return 0.75 - 0.03 * max(0, year - 2023)


def af_tanker(dwt: float, shuttle: bool) -> float:
    a, b = AF_SHUTTLE if shuttle else AF_STS
    return a * dwt ** (-b)


def reefer_tonnes(reefer_days: float, sfoc_g_per_kwh: float = SFOC_DEFAULT_2_STROKE) -> float:
    """Appendix 1 Part A 1.2: Cx x 24 x SFOC x reefer-days, for ships without reefer kWh meters."""
    return REEFER_DEFAULT_KW * 24.0 * sfoc_g_per_kwh * reefer_days / 1e6


def _eligibility(kind: str, ship_type: ShipType, inp: G5Input) -> Optional[str]:
    if kind not in KINDS:
        return f"Unknown G5 correction '{kind}'."
    if kind in TANKER_ONLY and ship_type != ShipType.TANKER:
        return f"{KINDS[kind][0]} applies to tankers only ({KINDS[kind][1]})."
    if kind in GAS_ONLY and ship_type not in (ShipType.GAS_CARRIER, ShipType.LNG_CARRIER):
        return f"{KINDS[kind][0]} applies to gas carriers and LNG carriers only ({KINDS[kind][1]})."
    if kind == "voyage_ice" and not inp.ice_class.strip():
        return "The ice voyage adjustment is only for ice-classed ships (G5 para 4.1.2). State the ice class."
    return None


def apply_g5(fuels: dict, distance_nm: float, ship_type: ShipType, dwt: float, year: int,
             inp: G5Input) -> G5Applied:
    """Raises ValueError on any deduction the guideline does not allow."""
    notes: list[str] = []
    k = year_factor(year)
    errors = []
    for d in inp.deductions:
        e = _eligibility(d.kind, ship_type, inp)
        if e:
            errors.append(e)
        if d.tonnes < 0 or d.distance_nm < 0:
            errors.append(f"{KINDS.get(d.kind, (d.kind,))[0]}: quantities cannot be negative.")
        if d.fuel not in fuels and d.tonnes > 0:
            errors.append(f"{KINDS.get(d.kind, (d.kind,))[0]}: no {d.fuel.value.upper()} was reported, "
                          "so none can be deducted.")
    for name, val in (("fi", inp.fi), ("fm", inp.fm), ("fc", inp.fc), ("fiVSE", inp.fivse)):
        if val <= 0:
            errors.append(f"{name} must be positive.")
    if inp.fm != 1.0 and inp.ice_class.strip().upper() not in ICE_CLASSES_FM:
        errors.append("fm applies only to ice class IA or IA Super (G5 section 4).")
    if inp.fc != 1.0 and ship_type != ShipType.TANKER:
        errors.append("fc (cubic capacity) applies only to chemical tankers (G5 section 4).")
    if inp.fivse != 1.0 and not (ship_type == ShipType.BULK_CARRIER and inp.self_unloading):
        errors.append("fiVSE applies only to self-unloading bulk carriers (G5 section 4).")
    if inp.fi != 1.0 and not inp.ice_class.strip():
        errors.append("fi is the capacity correction for ice-classed ships; state the ice class.")
    if inp.shuttle_tanker and ship_type != ShipType.TANKER:
        errors.append("The shuttle-tanker correction applies to tankers with dynamic positioning only (G5 para 2.9).")

    sts = [d for d in inp.deductions if d.kind == "sts" and d.tonnes > 0]
    factor_ded = [d for d in inp.deductions if d.kind in FACTOR_KINDS and d.tonnes > 0]
    if inp.shuttle_tanker and (sts or factor_ded):
        errors.append("With the shuttle-tanker correction, the STS correction and FC_electrical, FC_boiler "
                      "and FC_others are not used (G5 para 4.2).")
    if sts and factor_ded:
        errors.append("With the STS correction, FC_electrical, FC_boiler and FC_others are not used "
                      "(G5 paras 3.3 and 4.2).")
    if errors:
        raise ValueError(" ".join(dict.fromkeys(errors)))

    lines: list[G5Line] = []
    deducted: dict = {f: 0.0 for f in fuels}
    dx = 0.0

    if inp.shuttle_tanker:
        af = af_tanker(dwt, shuttle=True)
        for f, t in fuels.items():
            w = 1.0 - af
            deducted[f] += w * t
            lines.append(G5Line("shuttle", "Shuttle tanker with dynamic positioning: AF_Tanker,Shuttle "
                                f"= 5.6805 x DWT^-0.208 = {af:.4f}", "G5 paras 2.9 and 4.2",
                                f.value, round(t, 3), round(w, 4), round(w * t * CF_TCO2_PER_T[f], 1), 0.0))
    af_sts = af_tanker(dwt, shuttle=False) if sts else None

    for d in inp.deductions:
        if d.tonnes <= 0 and d.distance_nm <= 0:
            continue
        label, src = KINDS[d.kind]
        if d.kind in VOYAGE_KINDS:
            w = 1.0
            dx += d.distance_nm
            if d.distance_nm == 0:
                notes.append(f"{label}: no distance entered. G5 para 4.1 requires the distance sailed in the "
                             "voyage period to be deducted too.")
        elif d.kind == "sts":
            w = 1.0 - af_sts
            label = f"{label}: AF_Tanker,STS = 6.1742 x DWT^-0.246 = {af_sts:.4f}"
        else:
            w = k
        deducted[d.fuel] = deducted.get(d.fuel, 0.0) + w * d.tonnes
        lines.append(G5Line(d.kind, label, src, d.fuel.value, round(d.tonnes, 3), round(w, 4),
                            round(w * d.tonnes * CF_TCO2_PER_T[d.fuel], 1), round(d.distance_nm, 1)))
        if d.basis:
            notes.append(f"{label}: evidence {d.basis}.")

    over = [f.value.upper() for f, t in fuels.items() if deducted.get(f, 0.0) > t + 1e-9]
    if over:
        raise ValueError(f"G5 deductions exceed the {', '.join(over)} reported for the year.")
    if dx >= distance_nm:
        raise ValueError("Excluded voyage distance cannot reach the total distance sailed.")

    numerator = sum(CF_TCO2_PER_T[f] * (t - deducted[f]) for f, t in fuels.items())
    denom = inp.fi * inp.fm * inp.fc * inp.fivse
    if factor_ded:
        notes.append(f"FC_electrical, FC_boiler and FC_others are deducted at (0.75 - 0.03 x {max(0, year - 2023)}) "
                     f"= {k:.2f} for {year}; the share falls by 0.03 each year (G5 section 4).")
    if denom != 1.0:
        notes.append(f"Capacity correction fi x fm x fc x fiVSE = {denom:.4f}, taken from the EEDI/EEXI "
                     "Technical File (G5 para 4.6).")
    notes.append("Report total fuel, hours under way and total distance to the Administration as usual; "
                 "each G5 parameter used must also be reported and recorded in the logbook (G5 section 4).")
    return G5Applied(numerator, distance_nm - dx, denom, lines, notes)
