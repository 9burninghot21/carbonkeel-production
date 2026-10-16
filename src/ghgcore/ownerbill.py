"""Owner-data carbon bill: the operator's own annual fuel, split by voyage scope.

The split is the operator's statement of where the fuel was burned (share of each fuel
type, by mass). Each share becomes one leg with the regulation's own scope rule:
  intra-EEA voyages              EU 100%   (Directive Art. 3ga; FuelEU Art. 2)
  voyages into or out of the EEA EU 50%
  at berth in an EEA port        EU 100%
  UK domestic voyages and berth  UK 100%   (SI 2026/392 Sch. 2A paras 7, 15)
  Great Britain <-> N. Ireland   UK 50%
  everything else                out of scope
"""
from dataclasses import dataclass

from .schema import (AnnualActivity, EngineType, FuelConsumption, FuelType, ShipType, Vessel,
                     VoyageLeg, VoyageScope)

SPLIT_KEYS = ("intra_eea", "extra_eea", "berth_eea", "uk_domestic", "uk_gb_ni")
SPLIT_LABELS = {
    "intra_eea": ("Voyages between EEA ports", VoyageScope.INTRA_EEA, None, "EU 100%"),
    "extra_eea": ("Voyages into or out of the EEA", VoyageScope.EXTRA_EEA, None, "EU 50%"),
    "berth_eea": ("At berth in EEA ports", VoyageScope.AT_BERTH_EEA, None, "EU 100%"),
    "uk_domestic": ("UK domestic voyages and UK berths", VoyageScope.OUT_OF_SCOPE, 1.0, "UK 100%"),
    "uk_gb_ni": ("Great Britain to Northern Ireland voyages", VoyageScope.OUT_OF_SCOPE, 0.5, "UK 50%"),
}


@dataclass
class ScopeSplit:
    intra_eea: float = 0.0     # percent of the year's fuel
    extra_eea: float = 0.0
    berth_eea: float = 0.0
    uk_domestic: float = 0.0
    uk_gb_ni: float = 0.0

    def validate(self) -> float:
        vals = [getattr(self, k) for k in SPLIT_KEYS]
        if any(v < 0 or v > 100 for v in vals):
            raise ValueError("Each voyage share must be between 0 and 100%.")
        total = sum(vals)
        if total > 100.0001:
            raise ValueError(f"The voyage shares add up to {total:g}%; they cannot exceed 100%.")
        return 100.0 - total


def build_activity(name: str, imo: str, ship_type: ShipType, dwt: float, gt: float, year: int,
                   fuels: dict, split: ScopeSplit,
                   engine: EngineType = EngineType.OTTO_MS) -> tuple[AnnualActivity, list[dict]]:
    outside = split.validate()
    vessel = Vessel(imo, name, ship_type, dwt=dwt, gt=gt or dwt, engine_type=engine)
    legs, rows = [], []
    parts = [(k, getattr(split, k)) for k in SPLIT_KEYS] + [("outside", outside)]
    for key, pct in parts:
        if pct <= 0:
            continue
        if key == "outside":
            label, scope, uk, rule = "Outside EU and UK scope", VoyageScope.OUT_OF_SCOPE, 0.0, "0%"
        else:
            label, scope, uk, rule = SPLIT_LABELS[key]
            uk = 0.0 if uk is None else uk
        share = pct / 100.0
        legs.append(VoyageLeg(scope, 0.0, [FuelConsumption(f, t * share) for f, t in fuels.items() if t > 0],
                              f"Owner data: {label}", uk_share=uk))
        rows.append({"key": key, "label": label, "pct": round(pct, 2), "rule": rule,
                     "fuel_t": round(sum(t for t in fuels.values()) * share, 1)})
    return AnnualActivity(vessel, year, legs), rows
