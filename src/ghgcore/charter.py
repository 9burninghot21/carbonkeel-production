"""Owner / time-charterer split of the carbon bill.

BIMCO's ETS Allowances Clause for Time Charter Parties 2022 and FuelEU Maritime Clause
for Time Charter Parties 2024 put the cost of emissions during the charter period on the
charterer, with the owner remaining the party the regulators deal with. The clauses
allocate the emissions actually reported for the charter period; without voyage-level
data we split pro rata by days, and say so.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional

CLAUSES = ("BIMCO ETS Allowances Clause for Time Charter Parties 2022; "
           "BIMCO FuelEU Maritime Clause for Time Charter Parties 2024")


@dataclass
class CharterSplit:
    year: int
    charter_from: str
    charter_to: str
    days_on_charter: int
    days_in_year: int
    charterer_share: float
    lines: list[dict]          # {item, total_eur, charterer_eur, owner_eur}
    total_charterer_eur: float
    total_owner_eur: float
    notes: list[str]


def days_in_year(year: int) -> int:
    return (date(year + 1, 1, 1) - date(year, 1, 1)).days


def overlap_days(year: int, start: date, end: date) -> int:
    if end < start:
        raise ValueError("The charter end date is before its start date.")
    lo, hi = max(start, date(year, 1, 1)), min(end, date(year, 12, 31))
    return max(0, (hi - lo).days + 1)


def split(year: int, start: date, end: date, items: dict[str, float],
          share_override: Optional[float] = None) -> CharterSplit:
    """items: {label: cost in EUR}. share_override (0-1) replaces the pro-rata day share,
    for when the charter period's share of emissions is known from voyage data."""
    n, total_days = overlap_days(year, start, end), days_in_year(year)
    share = n / total_days
    notes = [f"Charter {start.isoformat()} to {end.isoformat()}: {n} of {total_days} days in {year}."]
    if share_override is not None:
        share = max(0.0, min(1.0, share_override))
        notes.append(f"Charterer share set to {share * 100:.1f}% from the charter period's own emissions.")
    else:
        notes.append("Split pro rata by days. The clauses allocate the emissions reported for the "
                     "charter period, which differ if the ship was idle or off hire; use those figures "
                     "for the contractual statement.")
    notes.append(f"Basis: {CLAUSES}. Check the clause wording and elections in your charter party.")
    lines, tc, to = [], 0.0, 0.0
    for label, eur in items.items():
        c = round(eur * share, 0)
        o = round(eur - c, 0)
        lines.append({"item": label, "total_eur": round(eur, 0), "charterer_eur": c, "owner_eur": o})
        tc += c
        to += o
    return CharterSplit(year, start.isoformat(), end.isoformat(), n, total_days, round(share, 4),
                        lines, tc, to, notes)
