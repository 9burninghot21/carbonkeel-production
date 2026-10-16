"""UK ETS maritime engine: the Greenhouse Gas Emissions Trading Scheme (Amendment)
(Extension to Maritime Activities) Order 2026, SI 2026/392, in force 1 July 2026.

Scope (Schedule 2A, checked against the Order on 6 Oct 2026):
- Ships of 5,000 GT or more (para 5), except armed-service and government ships,
  fishing, research, search-and-rescue and similar ships, non-mechanically propelled
  and primitive wooden ships, **ships operating a Scottish ferry service**, and, up to
  and including 31 Dec 2026, offshore ships.
- A "voyage" starts at the last berth at a UK port and ends at the first berth at a UK
  port, and does not arrive at a port outside the UK (para 7). International voyages are
  therefore outside the scheme. In-port activity (movements in port and time at berth,
  moored or anchored) is covered.
- Surrender (para 15): 50% of emissions on voyages between Great Britain and Northern
  Ireland, 100% of everything else. No phase-in. Due by 30 April of the following year,
  except that 2026 emissions are due by **30 April 2028**.
- Gases: CO2, CH4 and N2O from the start, with the same GWPs as the EU (28 and 265).
- A verified report is due by 31 March of the following year (para 14).
- Fuel emission reduction claims (para 37) can set the factor of an eligible fuel to zero;
  they need a ministerial direction and verification, so they are not applied here.

The monitoring formula and shared constants are in `ets_rules.py`. The 2026 scheme year
runs only from 1 July: callers must pass second-half activity, the engine does not prorate.
"""
from dataclasses import dataclass, field
from typing import Optional

from .schema import AnnualActivity
from .ets_rules import (gas_emissions, UKETSExceptions, UK_FIRST_SCHEME_YEAR)
from .assumptions import DEFAULT_UKA_PRICE_GBP


@dataclass
class UKETSResult:
    co2e_in_scope_t: float
    allowances_due: float          # UKAs (100% surrender, no phase-in)
    cost_gbp: float
    uka_price_used: float
    notes: list[str]
    surrender_by: str = ""
    excluded: bool = False
    # False when no leg carries a UK share at all (the EU register cannot show UK voyages)
    data_observable: bool = True


def surrender_date(year: int) -> str:
    return "30 April 2028" if year <= 2026 else f"30 April {year + 1}"


def compute_ukets(activity: AnnualActivity,
                  uka_price_gbp: float = DEFAULT_UKA_PRICE_GBP,
                  exceptions: Optional[UKETSExceptions] = None) -> UKETSResult:
    notes = ["UK ETS covers domestic UK voyages and time in UK ports only (voyages between Great "
             "Britain and Northern Ireland count at 50%). Voyages that arrive at a port outside "
             "the UK are outside the scheme."]
    year = activity.year
    by = surrender_date(year) if year >= UK_FIRST_SCHEME_YEAR else ""
    if year < UK_FIRST_SCHEME_YEAR:
        notes.append(f"The UK ETS covers shipping only from 1 July {UK_FIRST_SCHEME_YEAR}, so {year} "
                     f"emissions carry no obligation.")
        return UKETSResult(0.0, 0.0, 0.0, uka_price_gbp, notes, by, False)
    if exceptions and exceptions.excluded_ship:
        notes.append("This ship is in an excluded class under Schedule 2A para 5"
                     + (f" ({exceptions.reason})" if exceptions.reason else "")
                     + ", so no allowances are due.")
        return UKETSResult(0.0, 0.0, 0.0, uka_price_gbp, notes, by, True)

    observable = any(leg.uk_share is not None for leg in activity.legs)
    co2e, any_uk = 0.0, False
    for leg in activity.legs:
        share = leg.uk_share or 0.0
        if share <= 0:
            continue
        any_uk = True
        for fc in leg.fuel_consumed:
            g = gas_emissions(fc.fuel, fc.tonnes * share, activity.vessel.engine_type,
                              activity.fuel_is_combusted)
            co2e += g.co2e(True)
    if not observable:
        notes.append("UK domestic voyages are not in the EU register, so the UK ETS cannot be "
                     "estimated from public data. Enter UK voyages with your own data to include it.")
        return UKETSResult(0.0, 0.0, 0.0, uka_price_gbp, notes, by, False, data_observable=False)
    if not any_uk:
        notes.append("No UK domestic voyages were found in this ship’s data.")
    if year == UK_FIRST_SCHEME_YEAR:
        notes.append("The 2026 UK ETS period runs only from 1 July to 31 December. Enter "
                     "second-half activity; this estimate does not pro-rate.")
    notes.append(f"Surrender by {by}. The verified report is due by 31 March {year + 1}.")
    return UKETSResult(round(co2e, 1), round(co2e, 1), round(co2e * uka_price_gbp, 0),
                       uka_price_gbp, notes, by, False)
