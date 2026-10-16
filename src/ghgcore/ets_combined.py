"""EU ETS and UK ETS computed together, for the same ship-year.

The two schemes are designed not to overlap: the EU scheme counts voyages and port time
that touch an EU port, the UK scheme counts voyages that start and end in the UK plus
time in UK ports. A voyage between the EU and the UK is EU ETS at 50% and not UK ETS.
Northern Ireland ports are UK ports for the UK scheme and are not EU ports.

Running them together lets us (a) add the two bills on one basis, (b) refuse to double
count a leg, and (c) say plainly which data we could not see.
"""
from dataclasses import dataclass, field
from typing import Optional

from .schema import AnnualActivity, VoyageScope
from .euets import compute_ets, ETSResult
from .ukets import compute_ukets, UKETSResult, DEFAULT_UKA_PRICE_GBP
from .ets_rules import ETSExceptions, UKETSExceptions
from .assumptions import DEFAULT_EUA_PRICE_EUR, DEFAULT_EUR_PER_GBP

EU_SCOPES = (VoyageScope.INTRA_EEA, VoyageScope.EXTRA_EEA, VoyageScope.AT_BERTH_EEA)
VALID_UK_SHARES = (0.0, 0.5, 1.0)


@dataclass
class CombinedETS:
    eu: ETSResult
    uk: UKETSResult
    eur_per_gbp: float
    total_eur: float
    warnings: list[str] = field(default_factory=list)


def check_disjoint(activity: AnnualActivity) -> list[str]:
    """Problems that would double count or mis-scope a leg across the two schemes."""
    out: list[str] = []
    for i, leg in enumerate(activity.legs, 1):
        uk = leg.uk_share
        if uk is not None and uk not in VALID_UK_SHARES:
            out.append(f"Leg {i}: UK share {uk} is not 0, 0.5 or 1.")
        if leg.scope in EU_SCOPES and (uk or 0.0) > 0:
            out.append(f"Leg {i} ({leg.description or leg.scope.value}) is counted in both schemes. "
                       f"A leg that touches an EU port cannot also be a UK domestic leg.")
    return out


def compute_ets_combined(activity: AnnualActivity, eua_price_eur: float = DEFAULT_EUA_PRICE_EUR,
                         uka_price_gbp: float = DEFAULT_UKA_PRICE_GBP,
                         eur_per_gbp: float = DEFAULT_EUR_PER_GBP,
                         eu_exceptions: Optional[ETSExceptions] = None,
                         uk_exceptions: Optional[UKETSExceptions] = None) -> CombinedETS:
    warnings = check_disjoint(activity)
    eu = compute_ets(activity, eua_price_eur, eu_exceptions)
    uk = compute_ukets(activity, uka_price_gbp, uk_exceptions)
    if warnings:
        eu.notes.extend(warnings)
    total = eu.cost_eur + uk.cost_gbp * eur_per_gbp
    return CombinedETS(eu, uk, eur_per_gbp, round(total, 0), warnings)
