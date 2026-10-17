# Calculation notes — audit this by hand

Every number CarbonKeel shows comes from one of seven deterministic engines.
This document states each engine's formula, parameters (with source), and a
worked example you can recompute on a calculator. The same examples run as
assertions in `tests/test_engines.py` (226 checks) — if you change a table,
the tests force the hand-computation to be redone.

## 1. CII (MARPOL Annex VI Reg. 28 — `cii.py`)

```
attained CII = Σ(fuel_t × CF) × 10⁶ / (Capacity × Distance_nm)     [G1]
reference    = a × Capacity_ref^(-c)                               [G2]
required     = reference × (1 − Z/100)                             [G3]
rating       = A/B/C/D/E via attained/required vs dd vector        [G4]
```
- CF (tCO₂/t fuel): HFO 3.114, LFO 3.151, MDO/MGO 3.206, LNG 2.750,
  methanol 1.375 (2018 DCS Guidelines / G1).
- (a, c) and dd vectors verified line-by-line against the official
  MEPC.353(78) / MEPC.354(78) PDFs, including: gas-carrier 65k dwt split,
  general-cargo 20k split, LNG-carrier 65k/100k splits, bulk 279k cap,
  vehicle-carrier 57,700 GT reference cap, GT capacity basis for
  ro-ro/ro-pax/cruise/vehicle.
- Z factors: 2023–26 = 5/7/9/11%; 2027–30 = 13.625/16.25/18.875/21.5%
  (MEPC.400(83)).
- G5 corrections (MEPC.355(78)) are applied only when the operator supplies
  documented values — never inferred. See section 1b.

**Worked example** (test `test_cii`): bulk carrier, 50,000 dwt, 3,000 t HFO,
50,000 nm, 2026. CO₂ = 3,000×3.114 = 9,342 t. Attained =
9,342×10⁶/(50,000×50,000) = **3.737**. Reference = 4745×50,000^-0.622 =
**5.668**. Required = 5.668×0.89 = **5.044**. Ratio 0.741 ≤ d1 0.86 → **A**.

**Known estimate-path caveats** (public-data lookup only): distance is backed out of
"CO₂ per distance" in the MRV filing; DWT/GT is user-supplied; fuel mix is
assumed HFO-equivalent. Owner data removes all three.

## 1b. CII corrections and voyage adjustments (MEPC.355(78), G5 — `g5.py`)

```
         Σ_j CF_j · { FC_j − ( FC_voyage,j + TF_j + (0.75 − 0.03·y) · (FC_electrical,j + FC_boiler,j + FC_others,j) ) }
CII  =  ──────────────────────────────────────────────────────────────────────────────────────────────
                                 fi · fm · fc · fiVSE · Capacity · (D_t − D_x)
```
- y counts from 2023 = 0, so the electrical, boiler and other deductions count at
  0.75 in 2023, 0.66 in 2026 and 0.54 in 2030 (G5 section 4).
- Voyage adjustments (para 4.1): situations endangering safe navigation under
  MARPOL Annex VI reg. 3.1, and ice-classed ships sailing within the ice edge. The
  fuel and the distance of the period both come out.
- FC_electrical (para 4.3): refrigerated containers on any ship (Appendix 1 Part A.1:
  without a kWh meter, 2.75 kW × 24 h × SFOC × reefer-days, SFOC 175 g/kWh 2-stroke
  or 200 g/kWh 4-stroke); cargo cooling on gas and LNG carriers; electric discharge
  pumps on tankers. FC_boiler (para 4.4): cargo heating and steam cargo pumps on
  tankers. FC_others (para 4.5): standalone engine-driven cargo pumps on tankers.
- STS voyages on tankers (paras 2.8, 4.2: each leg ≤ 600 nm and ≤ 72 h):
  TF = (1 − 6.1742 × DWT^−0.246) × fuel on STS voyages. Shuttle tankers with
  dynamic positioning (para 2.9): TF = (1 − 5.6805 × DWT^−0.208) × all fuel. With
  either, the electrical, boiler and other deductions are not used.
- fi, fm (IA and IA Super), fc (chemical tankers) and fiVSE (self-unloading bulk
  carriers) only if they are in the ship's EEDI/EEXI Technical File (para 4.6).
- The calculator refuses any deduction the guideline does not allow for the ship
  type, any deduction larger than the fuel reported, and combinations the guideline
  excludes. The rating trajectory recomputes the deduction share for each year.

**Worked example** (test `test_g5_corrections`): container ship, 50,000 dwt,
10,000 t HFO, 100,000 nm, 2026, 11.55 t HFO for reefers (1,000 reefer-days at
175 g/kWh). Numerator = 3.114 × (10,000 − 0.66 × 11.55) = **31,116.26 t**;
attained = 31,116.26 × 10⁶ / (50,000 × 100,000) = **6.2233** (6.228 without).

## 2. EEXI (Reg. 23/25 — `eexi.py`)

```
required EEXI = (1 − X/100) × a × Capacity^(-c)      [EEDI reference line]
verdict: reported attained (from the ship's own MRV filing) vs required
```
- Reduction factors (Y) per MARPOL Annex VI **Reg. 25 Table 3** — verified
  line-by-line against the consolidated Annex VI text on 2 Oct 2026; all twelve
  ship types match. The cruise band applies to cruise passenger ships having
  non-conventional propulsion and is measured in GT.
- **Capacity basis per MEPC.364(79) §2.2.3** (verified 2 Oct 2026):
  - §2.2.3.1 bulk, tanker, gas, LNG, ro-ro cargo (incl. vehicle carrier),
    ro-ro passenger, general cargo, refrigerated cargo, combination → **deadweight**
  - §2.2.3.2 passenger and cruise passenger ships -> **gross tonnage**
  - §2.2.3.3 containerships -> **70% deadweight for the attained index**, but
    §2.2.3.3.3-.4 state a = 174.22 and c = 0.201 were fitted against *100%*
    deadweight, so the **required** value uses full DWT. Using 70% in both
    places understates the required value and lets a non-compliant ship look
    compliant — this was a real bug, fixed 2 Oct 2026.
- Reg. 25.2: for ro-ro cargo and ro-ro passenger ships the phase-2 reference
  line under Reg. 24.3 applies.
- If the filing reports EEDI/EIV instead of EEXI, the verdict is labelled
  INDICATIVE (design index ≠ certified EEXI).

**Worked example** (test `test_eexi`): bulk 93,000 dwt, reported
"EEXI (2.97)". Reference = 961.79×93,000^-0.477 = **4.103**; X = 20% →
required = **3.283**. 2.97 ≤ 3.283 → **COMPLIANT**, margin +9.5%.

## 3. EU ETS (Directive 2003/87/EC — `euets.py`)

```
CO₂e = Σ_legs Σ_fuels tonnes × scope_share × (CF + CH₄_EF×28 + N₂O_EF×265)
EUAs = CO₂e × phase-in (2024: 40%, 2025: 70%, 2026+: 100%)
```
- Scope shares: intra-EEA & berth 100%, one-EEA-end 50%.
- CH₄/N₂O included from reporting year 2026, GWP100 AR5 (28/265).
- Liquid-fuel EFs 0.00005/0.00018 t/t (verified vs Annex II/Reg. 2015/757);
  LNG methane = engine-type slip: Otto-MS 3.1%, Otto-SS 1.7%, Diesel-DF
  0.2%, LBSI 2.6% of fuel mass.
- **The bill uses the verifier-reported figure.** The register publishes each ship's
  "CO2 to be reported under Directive 2003/87/EC". It already reflects ship size,
  a container ship's stops at neighbouring transhipment ports, ports of call and
  derogations, none of which the public file exposes. The engine scales its
  rebuild to it (`activity.ets_calibration`); the rebuild stays as a cross-check.
- Cross-check, over every ship with EU-scope activity in the 2025 report v6
  (14,734 ships; `scripts/verifier_match.py`): our rebuild matches exactly for
  68.5%, within 1% for 74.6% and within 2% for 77.2%; 17.1% differ by more,
  and in 90% of those our rebuild is the higher one (median +11%). A further 839
  ships (5.7%) reported zero ETS-scope CO2 while our rebuild was positive: mostly
  general cargo ships of 400 to 5,000 GT, which report under EU MRV from 2025 but
  are outside the ETS. Charging them was an error of the old rebuild-only method.
  Example of an exact match: IMO 9464663, 7,409.0 t both.
- **CO2 is calculated on combusted fuel**, per Reg. 2015/757 Annex I Part A as
  amended by Delegated Reg. 2023/2776: CO2 = sum (M - M_NC) x EF, and CH4 includes
  the slipped fuel M_NC (a percentage of fuel mass: LNG Otto medium speed 3.1%,
  Otto slow speed 1.7%, Diesel dual-fuel 0.2%, LBSI 2.6%).
- **Exceptions** (Directive Art. 12(3-b) to (3-e), until 31 Dec 2030): ice class IA
  or IA Super may surrender 5% fewer allowances; voyages between an outermost
  region and a port of the same Member State carry no obligation; island services
  by passenger (non-cruise) and ro-pax ships, and transnational public-service
  routes, are exempt where the Commission has adopted an implementing act. The
  user states these (ice class; share of emissions covered by a derogation).
  Container-ship stops at listed neighbouring transhipment ports are not ports of
  call (Art. 3(z)); this is in the verifier's figure.
- **Scope in time**: no surrender obligation for emissions before 2024; CO2 only
  until 2025; CH4 and N2O from 1 Jan 2026 (Directive Annex I). Offshore ships of
  5,000 GT and above enter in 2027; cargo ships of 400 to 5,000 GT and offshore
  ships below 5,000 GT report under EU MRV but are outside the ETS.
- If allowances are not surrendered by 30 September: EUR 100 per tonne of CO2e
  (indexed), and the allowances are still owed (Art. 16(3)).

## 4. FuelEU Maritime (Reg. (EU) 2023/1805 — `fueleu.py`)

```
intensity = Σ(tonnes × LCV × WtW) / Σ(tonnes × LCV)     [in-scope energy]
CB [gCO₂e] = (target − intensity) × energy               [Annex IV]
penalty    = |CB| / (intensity × 41,000) × €2,400        [Art. 23]
```
- Target: 91.16 × (1−2%) for 2025–29, −6% from 2030, etc.
- LCV/WtW verified against Annex II (EUR-Lex CELEX 32023R1805): HFO 91.74,
  LFO 91.39, MGO 90.77, LNG 89.20/82.87/76.08/86.94 by engine, fossil
  methanol 103.15. FuelEU GWPs are AR4 (25/298) — deliberately different
  from ETS.
- Certified values (Art. 10) override defaults via `certified_props`.

- Applies from reporting period 2025 (no FuelEU result before that) to ships above
  5,000 GT carrying cargo or passengers (Art. 2). On public data, a ship whose
  verifier reported no ETS-scope emissions is shown as outside FuelEU too: the two
  schemes cover the same ships, and charging it would be a phantom penalty.
- **Repeat deficits** (Art. 23(2)): the penalty is multiplied by 1 + (n − 1)/10,
  where n is the number of consecutive reporting periods with a FuelEU penalty for
  the ship. The user states n; the public record cannot show it.
- **Pooling instead of paying.** The statutory penalty per tonne of deficit is
  10⁶ / (intensity × 41,000) × €2,400, about **€638 per tCO₂e** at HFO's 91.74.
  Pool surplus trades far below that (mid-2026 market levels about €105–120 per
  tCO₂e), so every result also shows the deficit bought from a pool at a price the
  user sets (default €110). Both totals are shown; the user picks which one heads
  the bill.

**Worked example** (test `test_fueleu`): 3,000 t HFO intra-EEA, 2026.
Energy = 121.5×10⁶ MJ; intensity 91.74 vs target 89.3368 → CB = **−292 t**;
penalty = 292×10⁶/(91.74×41,000)×2,400 = **€186,310**. Third consecutive deficit:
× 1.2 = **€223,572** (test `test_fueleu_penalty_rules`). Pooled at €110/t instead:
291.99 × 110 = **€32,119**.

## 5. UK ETS (`ukets.py`) — SI 2026/392, Schedule 2A
Same gases, factors, GWPs (28 and 265) and monitoring formula as the EU ETS
(`ets_rules.py`). Scope, from the Order: ships of 5,000 GT and above, except armed
services, law enforcement, fishing, research and rescue ships, wooden and
non-mechanical ships, **ships operating a Scottish ferry service**, and offshore
ships until 31 Dec 2026 (para 5). A voyage starts at the last berth in a UK port
and ends at the first berth in a UK port without arriving at a port outside the UK
(para 7), so **EU-UK voyages are EU ETS at 50% and not UK ETS**. In-port time,
moored or anchored, is covered. Surrender (para 15): 50% of Great Britain to
Northern Ireland voyages, 100% of everything else; no phase-in. Due 30 April of
the following year, **except 2026 emissions, due 30 April 2028**. Verified report by
31 March. The first scheme year is 1 July to 31 December 2026 and the engine does
not pro-rate. UKA price is an input (default £40, indicative). Fuel emission
reduction claims (para 37) are not applied: they need a ministerial direction and
verification.

## 5b. EU ETS and UK ETS together (`ets_combined.py`)
Both are computed for the same ship-year, added in euros, and checked so that no
leg is counted in both (a leg that touches an EU port cannot be a UK domestic leg).

## 5c. Your own fuel, split by voyage scope (`ownerbill.py`)
The operator states the share of the year's fuel burned on each kind of voyage:
between EU/EEA ports (EU 100%), into or out of the EU/EEA (EU 50%), at EU/EEA
berths (EU 100%), UK domestic and UK berths (UK 100%), Great Britain to Northern
Ireland (UK 50%); the rest is out of scope. Each share becomes one leg, and the EU
ETS, UK ETS and FuelEU engines apply their own rules to it. G5 corrections change
the CII only; the bill uses all the fuel.

**Worked example** (test `test_owner_bill_split`): 4,300 t HFO, 2026, 40% between
EU ports, 30% into or out of the EU, 10% at EU berths, 5% UK domestic. EU fuel in
scope = 4,300 × (0.40 + 0.5 × 0.30 + 0.10) = 2,795 t; CO₂e = 2,795 × (3.114 +
0.00005 × 28 + 0.00018 × 265) = **8,840.86 t**; at €85 = **€751,473**. UK: 215 t ×
3.1631 = 680.07 t at £40 = **£27,203**.

## 5d. Owner and time-charterer split (`charter.py`)
BIMCO's ETS Allowances Clause for Time Charter Parties 2022 and FuelEU Maritime
Clause for Time Charter Parties 2024 put the cost of emissions during the charter
period on the charterer. Without voyage data the split is pro rata by days
(charter days in the year ÷ days in the year); with voyage data the user enters the
charter period's share of emissions directly. The clauses allocate the emissions
actually reported for the period, so the result says which basis it used.
Example (test `test_charter_split`): 1 March to 31 August 2025 = 184 of 365 days,
50.41%: of a €100,000 ETS cost the charterer pays €50,411.

## 5e. What-if levers (`whatif.py`)
Speed change s on the same distance: main-engine fuel per mile scales with
(1 + s)^(n − 1) (n = 3, the cube law, by default; adjustable from 2 to 4.5);
auxiliary and boiler fuel burns per day, so it scales with 1/(1 + s); fuel at berth
does not change with sea speed. Biofuel: a share of each fossil fuel's energy moves
to certified B100, with the tonnage corrected for its lower calorific value. Every
what-if result is labelled as a scenario.

## 6. IMO Net-Zero Framework (`nzf.py`) — SCENARIO until adopted
```
GFI = Σ(tonnes × LCV × WtW) / Σ(tonnes × LCV)    [all voyages, WtW]
above Base target   → Tier 2 units @ $380/t (plus Tier 1 band)
Base…Direct band    → Tier 1 units @ $100/t
below Direct target → Surplus Units
```
Targets per MEPC 83 approval (2028 Base −4% and Direct −17% against 93.3). Every
output carries the "not yet adopted" note. In October 2025 the IMO postponed the
adoption decision by one year; it had not been adopted when these notes were last
checked (17 October 2026).

## 7. Pooling optimizer (`pooling.py`)
0/1 knapsack: admit deficit ships (weight = |CB|, value = standalone
penalty) into the surplus pool such that Σ CB ≥ 0, maximising avoided
penalty. Exact DP at 1-tonne granularity below 500k t capacity; greedy
density fallback above. Test pins the optimum against a hand-built case.

## Cross-cutting rules
- Every figure comes from these deterministic calculations; the same inputs always
  give the same result.
- ESTIMATE labelling on all public-data outputs. Every parameter and its source is
  listed in a full calculation worksheet, available from the Verifier view of any ship.
- Market assumptions are inputs, not facts, and every result echoes the value it
  used: EU allowance €85 (the September 2026 market average was €85.6), UK
  allowance £40 (indicative), €/£ 1.15, FuelEU pool price €110 per tCO₂e (mid-2026
  market levels). The user can change each one, and the bill also shows the EU
  allowance cost €15 either side.
- CarbonKeel is not an accredited verifier. Allowances are surrendered, and FuelEU
  balances settled, on the figures the ship's verifier accepts.
