"""Market assumptions. These are inputs, not regulatory facts: every result echoes the
value it used, and the user can change each one.

Levels checked on 17 Oct 2026:
- EU allowance: September 2026 average EUR 85.6/t, 12 Oct 2026 EUR 88.3/t (Carbon Pulse,
  reported by IndexBox).
- FuelEU pool surplus: OceanScore Pool-Price Index EUR 118.90/tCO2e (Aug 2026, offers);
  BetterSea volume-weighted trades EUR 106.52/tCO2e (Jul 2026). No official price exists.
- UK allowance: no current published level found; GBP 40 is indicative only.
"""
DEFAULT_EUA_PRICE_EUR = 85.0
DEFAULT_UKA_PRICE_GBP = 40.0
DEFAULT_EUR_PER_GBP = 1.15
DEFAULT_POOL_PRICE_EUR_PER_TCO2E = 110.0
ASSUMPTIONS_CHECKED = "17 October 2026"

PRICE_NOTES = {
    "eua": "EU allowance price: an assumption near the September 2026 market average "
           "(EUR 85.6/t). Set your own.",
    "uka": "UK allowance price: indicative only. Set your own.",
    "fx": "Pounds converted to euros at an assumed rate.",
    "pool": "FuelEU pool price: negotiated, no official price. Mid-2026 market levels were "
            "about EUR 105-120 per tCO2e (OceanScore index, BetterSea trades). Use your "
            "broker's quote.",
}


def assumptions_block(eua: float, uka: float, fx: float, pool: float) -> dict:
    return {"eua_price_eur": eua, "uka_price_gbp": uka, "eur_per_gbp": fx,
            "pool_price_eur_per_tco2e": pool, "checked": ASSUMPTIONS_CHECKED,
            "notes": PRICE_NOTES}
