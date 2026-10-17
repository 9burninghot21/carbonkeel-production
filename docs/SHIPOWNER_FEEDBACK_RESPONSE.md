# Shipowner review — what changed (17 October 2026)

A commercial shipowner / technical manager reviewed CarbonKeel. Each point, what was true,
and what the product does now. Figures are from the engines; see docs/CALCULATION_NOTES.md.

| Point raised | Finding | What changed |
|---|---|---|
| "One person, not a bot" reads as a hobby project | Fair | CarbonKeel presented as an independent business (a sole proprietorship), with a "Who we are, and what we are not" section: independent, **not an accredited verifier**. No credentials claimed that do not exist. |
| Privacy page broken (403) | True on the old host | `/privacy` served by the app. Notice names the controller, the real hosts (Fly.io Amsterdam, Namecheap, Gmail) and says calculator inputs are used for the answer and not stored. It does **not** claim "client-side only": the server does the maths. |
| Access key is friction | Fair | Calculator open to everyone. `CARBONKEEL_REQUIRE_KEY=1` turns the key back on. |
| Voyage split (50% vs 100%) ignored | **Not true for the public lookup**: the register's own scope split was already applied, and the bill uses the verifier's figure. It was not visible. | Every ship now shows the split table (between EU ports 100%, leaving or arriving 50%, berth 100%). The your-data calculator takes the operator's own split, UK domestic and GB–NI included. |
| Charter-party (BIMCO) allocation | Missing | Charter dates (or the charter period's share of emissions) split EU ETS, UK ETS and FuelEU between owner and charterer, citing the BIMCO ETS 2022 and FuelEU 2024 time-charter clauses. Pro rata by days, and labelled as such. |
| FuelEU flat penalty is unrealistic | Fair | Every result shows the statutory penalty (about €638 per tCO₂e at HFO intensity, with the Art. 23(2) repeat-deficit multiplier) **and** the cost of buying the deficit from a pool at a price the user sets (default €110/t, mid-2026 market). The user picks which heads the bill. |
| Rigid cube law, auxiliaries ignored | Partly: the speed estimate already took auxiliary and port fuel separately | Speed exponent adjustable (2 to 4.5). In the what-if, auxiliary fuel per day is separate and rises when slow steaming adds days; berth fuel no longer scales with sea speed (a real error, fixed). |
| Static allowance price | Partly: €60 and €100 sensitivity was shown | Editable EU and UK allowance prices and €/£, default €85 (September 2026 average), sensitivity ±€15. Remembered on the visitor's device only. |
| No PDF / Excel export | True for single ships | Printable single-ship report (save as PDF) and CSV, with every assumption and the legal references. Calculator results print and export as CSV too. |
| Fragmented lookup | Fair | One lookup with DWT now gives EU ETS, UK ETS, FuelEU, NZF, CII and EEXI together. |
| G5 corrections opaque | Fair | Itemised MEPC.355(78) corrections, shown only where the guideline allows them for the ship type, with the exact formula, the (0.75 − 0.03y) factor, STS and shuttle-tanker factors, the reefer default and the exclusion rules. Invalid entries are refused with the paragraph cited. |

## Other fixes found while doing this

- FuelEU was charged on ships the verifier reported as outside the ETS (mostly below
  5,000 GT): now shown as outside FuelEU. FuelEU no longer produces a figure before 2025.
- UK ETS showed £0 on public data as if checked. It now says UK domestic voyages are not in
  the EU register and cannot be costed from it.
- Behind Fly.io's proxy every visitor shared one rate-limit bucket; `CARBONKEEL_PROXY_HOPS=1`.
- A `.dockerignore` keeps personal files, git history and request logs out of the image.
- Ship names from the register are escaped before display; CSV cells cannot run as formulas.
- IMO Net-Zero Framework wording updated: not adopted; decision postponed in October 2025.

## Still open

- A live allowance price feed (needs a licensed data source).
- Legal entity: the site names an individual operator until a company exists.
- Email: enquiry@carbonkeel.com needs forwarding set up at Namecheap.
- Verifier or class partnership: nothing is claimed until one exists.
