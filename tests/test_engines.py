#!/usr/bin/env python3
"""Hand-computed worked examples for the four engines.

Reconstructed after project transfer (the original 8-case suite was lost in
the export). Each expected value below was computed by hand from the module
tables — if a table changes, recompute the expectation, don't copy the
engine output.

Run: python3 tests/test_engines.py
"""
import os
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ghgcore import Vessel, ShipType, build_scorecard
from ghgcore.schema import (AnnualActivity, VoyageLeg, FuelConsumption,
                            EngineType, FuelType, VoyageScope)
from ghgcore.cii import compute_cii
from ghgcore.fueleu import compute_fueleu, target_intensity
from ghgcore.euets import compute_ets
from ghgcore.nzf import compute_nzf

PASS = 0


def check(name, got, want, tol=0.01):
    global PASS
    ok = abs(got - want) <= tol * max(1.0, abs(want))
    print(f"  [{'ok' if ok else 'FAIL'}] {name}: got {got}, want ~{want}")
    if not ok:
        raise AssertionError(name)
    PASS += 1


def check_eq(name, got, want):
    global PASS
    print(f"  [{'ok' if got == want else 'FAIL'}] {name}: got {got!r}, want {want!r}")
    if got != want:
        raise AssertionError(name)
    PASS += 1


def base_activity(year=2026, scope=VoyageScope.INTRA_EEA):
    """Bulk carrier, 50k dwt: 3,000 t HFO over 50,000 nm, single leg."""
    v = Vessel("9999999", "MV HANDCALC", ShipType.BULK_CARRIER, dwt=50_000, gt=30_000)
    leg = VoyageLeg(scope, 50_000, [FuelConsumption(FuelType.HFO, 3_000)])
    return AnnualActivity(v, year, [leg])


def test_cii():
    print("CII (bulk 50k dwt, 3000 t HFO, 50,000 nm, 2026):")
    r = compute_cii(base_activity())
    # CO2 = 3000 * 3.114 = 9342 t
    check("CO2 tonnes", r.co2_tonnes, 9342.0)
    # attained = 9342e6 / (50000*50000) = 3.7368 gCO2/dwt-nm
    check("attained", r.attained, 3.7368)
    # reference = 4745 * 50000^-0.622 = 5.668; required = ref * (1-0.11) = 5.044
    check("reference", r.reference, 5.668)
    check("required 2026 (Z=11%)", r.required, 5.044)
    # ratio 0.7407 <= d1 0.86 -> A
    check_eq("rating", r.rating, "A")


def test_cii_z_fallback():
    print("CII Z-factor fallback (year 2031, beyond adopted table):")
    r = compute_cii(base_activity(year=2031))
    check("uses latest Z (21.5%)", r.z_factor_pct, 21.5, tol=0)
    assert any("No Z factor" in n for n in r.notes)
    check_eq("fallback noted", True, True)


def test_cii_gas_carrier_split():
    print("CII gas-carrier 65k dwt split (MEPC.353/354(78) verified):")
    v_small = Vessel("1", "GAS S", ShipType.GAS_CARRIER, dwt=30_000, gt=25_000)
    v_large = Vessel("2", "GAS L", ShipType.GAS_CARRIER, dwt=80_000, gt=60_000)
    leg = VoyageLeg(VoyageScope.OUT_OF_SCOPE, 40_000, [FuelConsumption(FuelType.HFO, 2_500)])
    # <65k: ref = 8104 * 30000^-0.639 = 11.164
    r = compute_cii(AnnualActivity(v_small, 2025, [leg]))
    check("<65k reference", r.reference, 11.164)
    # >=65k: ref = 14405e7 * 80000^-2.071 = 10.098
    r = compute_cii(AnnualActivity(v_large, 2025, [leg]))
    check(">=65k reference", r.reference, 10.098)
    # >=65k uses dd (0.81,0.91,1.12,1.44): attained = 2500*3.114*1e6/(80000*40000)
    # = 2.4328; required = 10.098*0.91 = 9.189; ratio 0.265 -> A
    check_eq(">=65k rating", r.rating, "A")


def test_cii_gt_and_lng_types():
    print("CII GT-capacity + LNG-carrier types (MEPC.353/354(78)):")
    leg = VoyageLeg(VoyageScope.OUT_OF_SCOPE, 60_000,
                    [FuelConsumption(FuelType.HFO, 9_000)])
    # Cruise, GT 100,000: attained = 28026e6/(100000*60000) = 4.671;
    # ref = 930*100000^-0.383 = 11.310; required 2026 = 10.066; ratio .464 -> A
    v = Vessel("7", "CRUISER", ShipType.CRUISE, dwt=12_000, gt=100_000)
    r = compute_cii(AnnualActivity(v, 2026, [leg]))
    check("cruise attained (GT basis)", r.attained, 4.671)
    check("cruise reference", r.reference, 11.310, tol=0.005)
    check_eq("cruise rating", r.rating, "A")
    # Vehicle carrier GT 60,000: reference capped at 57,700 GT
    v = Vessel("8", "CAR CARRIER", ShipType.VEHICLE_CARRIER, dwt=20_000, gt=60_000)
    r = compute_cii(AnnualActivity(v, 2026, [leg]))
    check("vehicle ref (57,700 cap)", r.reference, 5.629, tol=0.005)
    # LNG carrier splits: 80k dwt -> 14479e10*80000^-2.673 = 11.34;
    # 150k dwt -> constant 9.827
    v = Vessel("9", "LNG MID", ShipType.LNG_CARRIER, dwt=80_000, gt=90_000)
    r = compute_cii(AnnualActivity(v, 2026, [leg]))
    check("LNG 65-100k reference", r.reference, 11.343, tol=0.005)
    v = Vessel("10", "LNG BIG", ShipType.LNG_CARRIER, dwt=150_000, gt=120_000)
    r = compute_cii(AnnualActivity(v, 2026, [leg]))
    check("LNG >=100k constant ref", r.reference, 9.827, tol=0.001)
    # GT type without GT must refuse loudly
    v = Vessel("11", "NO GT", ShipType.RO_PAX, dwt=8_000, gt=0.0)
    try:
        compute_cii(AnnualActivity(v, 2026, [leg]))
        check_eq("missing GT raises", False, True)
    except ValueError:
        check_eq("missing GT raises", True, True)


def test_euets():
    print("EU ETS 2026 (intra-EEA, CH4/N2O in scope, 100% surrender):")
    r = compute_ets(base_activity(), eua_price_eur=70.0)
    # CO2e = 9342 + 3000*(0.00005*28 + 0.00018*265) = 9342 + 147.3 = 9489.3 t
    check("CO2e in scope", r.co2e_in_scope_t, 9489.3)
    check("surrender share", r.surrender_share, 1.0, tol=0)
    check("cost EUR @70", r.cost_eur, 9489.3 * 70)


def test_euets_extra_eea_2025():
    print("EU ETS 2025 (extra-EEA 50% scope, 70% phase-in, CO2 only):")
    r = compute_ets(base_activity(year=2025, scope=VoyageScope.EXTRA_EEA), 70.0)
    # 1500 t fuel in scope * 3.114 = 4671 t CO2; EUAs = 4671 * 0.7 = 3269.7
    check("CO2e in scope", r.co2e_in_scope_t, 4671.0)
    check("allowances due", r.allowances_due, 3269.7)


def test_fueleu():
    print("FuelEU 2026 (intra-EEA HFO — deficit expected):")
    r = compute_fueleu(base_activity())
    # energy = 3000 * 40500 = 121.5e6 MJ; intensity = 91.74 (Annex II verified:
    # 13.5 + (3.114 + 0.00005*25 + 0.00018*298)/0.0405) vs target 91.16*0.98
    check("target 2026", r.target, 89.34)
    check("intensity", r.ghg_intensity, 91.74)
    # CB = (89.3368-91.74) * 121.5e6 = -292.0e6 g -> -292.0 t
    check("balance tCO2e", r.compliance_balance_tco2e, -292.0, tol=0.01)
    # penalty = 292.0e6 / (91.74*41000) * 2400 = 186,310 EUR
    check("penalty EUR", r.penalty_eur, 186_310, tol=0.01)


def test_fueleu_targets():
    print("FuelEU target steps:")
    check("2025 (-2%)", target_intensity(2025), 91.16 * 0.98)
    check("2034 holds 2030 step (-6%)", target_intensity(2034), 91.16 * 0.94)
    check("2050 (-80%)", target_intensity(2050), 91.16 * 0.20)


def test_nzf():
    print("NZF scenario 2028 (HFO -> above Base target, two-tier deficit):")
    r = compute_nzf(base_activity(), scenario_year=2028)
    # gfi = 91.74; base = 93.3*0.96 = 89.568; direct = 93.3*0.83 = 77.439
    check("attained GFI", r.attained_gfi, 91.74)
    check("base target", r.base_target, 89.57)
    check("direct target", r.direct_target, 77.44)
    # tier2 = (91.74-89.568)*121.5 = 263.9 t; tier1 = (89.568-77.439)*121.5 = 1473.7 t
    check("tier2 deficit t", r.tier2_deficit_tco2e, 263.9, tol=0.02)
    check("tier1 deficit t", r.tier1_deficit_tco2e, 1473.7, tol=0.02)
    # cost = 1473.7*100 + 263.9*380 = 247,650 USD
    check("remedial cost USD", r.remedial_cost_usd, 247_650, tol=0.02)


def test_ports_scoping():
    print("Port-pair scoping (ports.py):")
    from ghgcore.ports import scope_for_leg, uk_share_for_leg
    s, fl = scope_for_leg("Rotterdam", "Piraeus")
    check_eq("EEA-EEA -> intra", s, VoyageScope.INTRA_EEA)
    s, fl = scope_for_leg("Rotterdam", "Singapore")
    check_eq("EEA-nonEEA -> extra", s, VoyageScope.EXTRA_EEA)
    s, fl = scope_for_leg("NLRTM", "SGSIN")
    check_eq("UN/LOCODE resolves", s, VoyageScope.EXTRA_EEA)
    s, fl = scope_for_leg("Atlantis", "Rotterdam")
    check_eq("unknown port -> None + flag", (s, len(fl)), (None, 1))
    check("UK domestic share", uk_share_for_leg("London", "Liverpool"), 1.0, tol=0)
    check("GB<->NI share", uk_share_for_leg("Liverpool", "Belfast"), 0.5, tol=0)
    check("UK-EEA share", uk_share_for_leg("London", "Rotterdam"), 0.0, tol=0)


def test_ukets():
    print("UK ETS (1000 t HFO on UK domestic legs):")
    from ghgcore.ukets import compute_ukets
    v = Vessel("3", "UK COASTER", ShipType.GENERAL_CARGO, dwt=25_000, gt=18_000)
    leg = VoyageLeg(VoyageScope.OUT_OF_SCOPE, 8_000,
                    [FuelConsumption(FuelType.HFO, 1_000)], uk_share=1.0)
    r = compute_ukets(AnnualActivity(v, 2027, [leg]), uka_price_gbp=40.0)
    # CO2e = 1000*(3.114 + 0.00005*28 + 0.00018*265) = 3163.1 t
    check("CO2e in scope", r.co2e_in_scope_t, 3163.1)
    check("cost GBP @40", r.cost_gbp, 3163.1 * 40)
    # GB<->NI at 50%
    leg2 = VoyageLeg(VoyageScope.OUT_OF_SCOPE, 8_000,
                     [FuelConsumption(FuelType.HFO, 1_000)], uk_share=0.5)
    r2 = compute_ukets(AnnualActivity(v, 2027, [leg2]))
    check("GB<->NI half scope", r2.co2e_in_scope_t, 3163.1 / 2)


def test_projection():
    print("Annualisation (30 days -> 365):")
    from ghgcore.projection import annualise
    v = Vessel("4", "PARTIAL", ShipType.BULK_CARRIER, dwt=50_000, gt=30_000)
    leg = VoyageLeg(VoyageScope.INTRA_EEA, 4_110, [FuelConsumption(FuelType.HFO, 246.6)])
    p = annualise(AnnualActivity(v, 2026, [leg]), days_observed=30)
    check("scale factor", p.scale_factor, 365 / 30)
    check_eq("confidence", p.confidence, "LOW")
    # CII is scale-invariant: 246.6*3.114e6/(50000*4110) = scaled attained
    check("attained unchanged by scaling", p.scorecard.cii.attained,
          246.6 * 3.114 * 1e6 / (50_000 * 4_110), tol=0.001)
    # ETS scales: 246.6*(365/30) t fuel -> full-year EUAs
    check("ETS CO2e annualised", p.scorecard.ets.co2e_in_scope_t,
          246.6 * (365 / 30) * (3.114 + 0.00005 * 28 + 0.00018 * 265), tol=0.001)


def test_eexi():
    print("EEXI check (Reg. 23/25):")
    from ghgcore.eexi import compute_eexi, parse_technical_efficiency
    v, b = parse_technical_efficiency("EEXI (5.34 gCO₂/t·nm)")
    check_eq("parse EEXI", (v, b), (5.34, "EEXI"))
    v, b = parse_technical_efficiency("EIV (10.2 gCO₂/t·nm)")
    check_eq("parse EIV", (v, b), (10.2, "EIV"))
    # Bulk 93k dwt: ref = 961.79*93000^-0.477 = 4.103; X=20 -> required 3.283
    r = compute_eexi(ShipType.BULK_CARRIER, 93_000, 50_000, "EEXI (2.97 gCO₂/t·nm)")
    check("bulk reference", r.reference, 4.103, tol=0.005)
    check("bulk required", r.required, 3.283, tol=0.005)
    check_eq("bulk verdict", r.verdict, "COMPLIANT")
    check("bulk margin %", r.margin_pct, 9.5, tol=0.05)
    # Containership, 80,000 DWT. MEPC.364(79) 2.2.3.3: the ATTAINED index uses
    # 70% DWT, but a=174.22/c=0.201 were fitted against 100% DWT, so the
    # REQUIRED value takes full deadweight (2.2.3.3.4):
    #   reference = 174.22 * 80000^-0.201 = 18.01
    #   Reg.25 Table 3 band 80,000-120,000 DWT -> Y = 35%
    #   required  = 18.01 * 0.65 = 11.71
    r = compute_eexi(ShipType.CONTAINER, 80_000, 78_000, "EEXI (14.0 gCO₂/t·nm)")
    check("container reference on 100% DWT", r.reference, 18.01, tol=0.005)
    check("container required", r.required, 11.71, tol=0.005)
    check_eq("container verdict", r.verdict, "ABOVE REQUIRED")
    # Cruise GT 69,203: X linear = 22.1%; ref = 170.84*69203^-0.214 = 15.73;
    # required = 12.26; attained 10.6 -> compliant
    r = compute_eexi(ShipType.CRUISE, 12_000, 69_203, "EEXI (10.6 gCO₂/t·nm)")
    check("cruise X linear", r.reduction_factor_pct, 22.1, tol=0.005)
    check("cruise required", r.required, 12.26, tol=0.005)
    check_eq("cruise verdict", r.verdict, "COMPLIANT")
    # EIV basis -> indicative verdict
    r = compute_eexi(ShipType.BULK_CARRIER, 93_000, 0, "EIV (3.0)")
    check_eq("EIV indicative", r.verdict.startswith("INDICATIVE"), True)
    # below threshold
    r = compute_eexi(ShipType.TANKER, 3_000, 2_000, "EEXI (9.9)")
    check_eq("below threshold N/A", r.verdict.startswith("N/A"), True)


def test_eexi_custom():
    print("Custom-vessel EEXI (simplified attained estimate):")
    from ghgcore.eexi import compute_eexi_custom, estimate_attained_eexi
    # Bulk 93k dwt, MCR 12,000 kW, Vref 14.2 kn, HFO, SFOC 175/215:
    # P_ME = 9,000; P_AE = 0.025*12000+250 = 550
    # attained = (9000*3.114*175 + 550*3.114*215)/(93000*14.2)
    #          = (4,904,550 + 368,231)/1,320,600 = 3.99
    att, notes = estimate_attained_eexi(ShipType.BULK_CARRIER, 93_000, 50_000,
                                        mcr_kw=12_000, vref_kn=14.2)
    check("estimated attained", att, 3.99, tol=0.005)
    r = compute_eexi_custom(ShipType.BULK_CARRIER, 93_000, 50_000,
                            mcr_kw=12_000, vref_kn=14.2)
    # required = 3.283 -> above required, indicative (estimated basis)
    check_eq("verdict", r.verdict, "INDICATIVE ABOVE REQUIRED")
    check_eq("basis", r.attained_basis, "ESTIMATED")
    check("margin negative", r.margin_pct, -21.6, tol=0.05)
    # direct attained input keeps a firm verdict
    r = compute_eexi_custom(ShipType.BULK_CARRIER, 93_000, 50_000, attained=2.9)
    check_eq("direct verdict", r.verdict, "COMPLIANT")
    # small ship P_AE branch: MCR 8,000 -> P_AE = 400
    att, _ = estimate_attained_eexi(ShipType.GENERAL_CARGO, 12_000, 9_000,
                                    mcr_kw=8_000, vref_kn=13.0)
    # (6000*3.114*175 + 400*3.114*215)/(12000*13) = (3,269,700+267,804)/156,000
    check("small-ship attained", att, 22.68, tol=0.005)
    # missing inputs must raise
    try:
        compute_eexi_custom(ShipType.TANKER, 50_000, 30_000)
        check_eq("missing inputs raise", False, True)
    except ValueError:
        check_eq("missing inputs raise", True, True)


def test_messy_ingestion():
    print("Messy noon-report files (deterministic stage-1 coverage):")
    import os
    from ghgcore.ingest import ingest_noon_csv
    fx = os.path.join(os.path.dirname(__file__), "..", "fixtures")
    v = Vessel("12", "MESSY", ShipType.BULK_CARRIER, dwt=60_000, gt=35_000)
    # Synonym-variant headers + mixed port scopes -> 3 legs, all mapped
    act, rep = ingest_noon_csv(os.path.join(fx, "messy_noon_synonyms.csv"), v, 2026)
    check_eq("all columns mapped", rep["unmapped_columns"], [])
    check_eq("scope-split legs", sorted(l.scope.value for l in act.legs),
             ["extra_eea", "intra_eea", "out_of_scope"])
    check("total distance", act.total_distance_nm, 340+335+310+305+180, tol=0)
    check("HFO total", act.total_fuel_by_type()[FuelType.HFO],
          31.2+30.8+28.9+28.4, tol=0.001)
    # Cryptic headers -> must refuse and point at the LLM fallback
    try:
        ingest_noon_csv(os.path.join(fx, "messy_noon_cryptic.csv"), v, 2026)
        check_eq("cryptic file raises", False, True)
    except ValueError as e:
        check_eq("cryptic file raises", "LLM" in str(e), True)


def test_llm_mapper_contract():
    print("LLM mapper: JSON contract validation (fake client, no API call):")
    from ghgcore.ingest import match_columns_llm

    class FakeBlock:
        type = "text"
        text = ('{"mapping": {"Dist (NM)": "distance_nm", "IFO380": "hfo_t", '
                '"Ghost": "hfo_t", "Dist (NM)2": "bogus_field"}, '
                '"unmapped": [], "warnings": ["units look metric"]}')

    class FakeMsg:
        content = [FakeBlock()]

    class FakeClient:
        class messages:
            @staticmethod
            def create(**kw):
                return FakeMsg()

    headers = ["Dist (NM)", "IFO380", "Dist (NM)2"]
    mapping, unmapped, warnings = match_columns_llm(headers, [["1", "2", "3"]],
                                                    client=FakeClient())
    check_eq("valid mappings kept", mapping,
             {"Dist (NM)": "distance_nm", "IFO380": "hfo_t"})
    check_eq("invented column rejected",
             any("Ghost" in w for w in warnings), True)
    check_eq("unknown canonical rejected",
             any("bogus_field" in w for w in warnings), True)
    check_eq("unmapped tracked", unmapped, ["Dist (NM)2"])


def test_engine_type_lng():
    print("Per-engine LNG slip (Annex II col. 9):")
    leg = VoyageLeg(VoyageScope.INTRA_EEA, 30_000, [FuelConsumption(FuelType.LNG, 2_000)])
    v_otto = Vessel("5", "LNG OTTO", ShipType.GAS_CARRIER, dwt=60_000, gt=45_000,
                    engine_type=EngineType.OTTO_MS)
    v_df = Vessel("6", "LNG DF", ShipType.GAS_CARRIER, dwt=60_000, gt=45_000,
                  engine_type=EngineType.DIESEL_DF)
    # FuelEU: energy = 2000*49100 = 98.2e6 MJ; target 2026 = 89.3368
    r = compute_fueleu(AnnualActivity(v_otto, 2026, [leg]))
    # Otto MS 89.20 -> CB = (89.3368-89.20)*98.2e6 = +13.4 t (barely compliant)
    check("Otto-MS balance t", r.compliance_balance_tco2e, 13.4, tol=0.05)
    r = compute_fueleu(AnnualActivity(v_df, 2026, [leg]))
    # Diesel DF 76.08 -> CB = 13.2568*98.2e6 = +1301.8 t
    check("Diesel-DF balance t", r.compliance_balance_tco2e, 1301.8, tol=0.01)
    # ETS 2026 by the Reg. 2015/757 Annex I formula (as amended by Del. Reg. 2023/2776):
    # CO2 = (M - M_NC) x 2.750; CH4 = slip M_NC; N2O = (M - M_NC) x 0.00011; GWP 28 and 265.
    # Otto MS, M = 2,000 t, slip 3.1%: M_NC = 62, combusted = 1,938.
    #   CO2 = 1938 x 2.750 = 5329.5; CH4 = 62 x 28 = 1736.0; N2O = 1938 x 0.00011 x 265 = 56.49
    #   total 7121.99
    e = compute_ets(AnnualActivity(v_otto, 2026, [leg]))
    check("Otto-MS ETS CO2e", e.co2e_in_scope_t, 7121.99, tol=0.001)
    # Diesel DF, slip 0.2%: M_NC = 4, combusted = 1,996.
    #   CO2 = 1996 x 2.750 = 5489.0; CH4 = 4 x 28 = 112.0; N2O = 1996 x 0.00011 x 265 = 58.18
    #   total 5659.18
    e = compute_ets(AnnualActivity(v_df, 2026, [leg]))
    check("Diesel-DF ETS CO2e", e.co2e_in_scope_t, 5659.18, tol=0.001)
    # Public-register path: tonnes were backed out of combusted CO2, so slip is added on top.
    # 1,938 t combusted, slip 3.1% of the total => M = 1938 / 0.969 = 2,000 t: same 7121.99.
    leg_c = VoyageLeg(VoyageScope.INTRA_EEA, 30_000, [FuelConsumption(FuelType.LNG, 1_938)])
    e = compute_ets(AnnualActivity(v_otto, 2026, [leg_c], fuel_is_combusted=True))
    check("register path adds slip back", e.co2e_in_scope_t, 7121.99, tol=0.001)


def test_certified_override_and_g5():
    print("Art.10 certified values + G5 correction hooks:")
    # certified HFO WtW 85.0 -> CB = (89.3368-85)*121.5e6 = +526.9 t
    r = compute_fueleu(base_activity(),
                       certified_props={FuelType.HFO: (40_500.0, 85.0)})
    check("certified-WtW balance t", r.compliance_balance_tco2e, 526.9, tol=0.01)
    check_eq("override noted", any("Art. 10" in n for n in r.notes), True)
    # G5: capacity factor 1.05 divides attained by 1.05
    from ghgcore.cii import CIICorrections
    r2 = compute_cii(base_activity(),
                     CIICorrections(capacity_correction=1.05, basis="test"))
    check("corrected attained", r2.attained, 3.7368 / 1.05, tol=0.001)
    check_eq("G5 noted", any("MEPC.355(78)" in n for n in r2.notes), True)


def test_pooling():
    print("FuelEU pooling optimizer (knapsack vs hand-picked optimum):")
    from ghgcore.pooling import PoolCandidate, suggest_pool
    # Surplus 100 t. Deficits: B 60t@91.7 (pen 38,301), C 50t@80 (pen 36,585),
    # D 30t@91.7 (pen 19,150). B+C won't fit (110); optimum = B+D = 57,451.
    cands = [PoolCandidate("A", "SURPLUS A", 100.0, 85.0),
             PoolCandidate("B", "DEFICIT B", -60.0, 91.7),
             PoolCandidate("C", "DEFICIT C", -50.0, 80.0),
             PoolCandidate("D", "DEFICIT D", -30.0, 91.7)]
    s = suggest_pool(cands)
    check("avoided penalty", s.avoided_penalty_eur, 57_451, tol=0.01)
    check("pool CB", s.pool_cb_tco2e, 10.0, tol=0.05)
    check_eq("admitted", sorted(m.imo for m in s.members), ["A", "B", "D"])
    check_eq("uncovered", [u.imo for u in s.uncovered], ["C"])
    # no-surplus fleet
    s2 = suggest_pool([PoolCandidate("X", "X", -40.0, 90.0)])
    check("no capacity -> nothing avoided", s2.avoided_penalty_eur, 0.0, tol=0)
    check_eq("external partner advised",
             any("external" in n for n in s2.notes), True)


def test_ets_rules_and_exceptions():
    print("EU ETS: phase-in, exceptions, calibration to the verifier (Directive Art. 3gb, 12(3-b..e)):")
    from ghgcore.ets_rules import ETSExceptions
    # no surrender obligation before 2024 (the old code gave 100%)
    r = compute_ets(base_activity(year=2023))
    check("2023: no surrender share", r.surrender_share, 0.0, tol=0)
    check("2023: no allowances", r.allowances_due, 0.0, tol=0)
    r = compute_ets(base_activity(year=2024))
    # 3000 t HFO x 3.114 = 9342 t CO2 (CO2 only before 2026); x 40%
    check("2024: 40% of CO2 only", r.allowances_due, 9342 * 0.40, tol=0.001)
    # exceptions on the 2026 base case: CO2e 9489.3
    r = compute_ets(base_activity(), 70.0, ETSExceptions(ice_class_ia=True))
    check("ice class IA: 5% fewer allowances", r.allowances_due, 9489.3 * 0.95, tol=0.001)
    r = compute_ets(base_activity(), 70.0, ETSExceptions(derogation_share=0.30))
    check("derogation on 30% of emissions", r.allowances_due, 9489.3 * 0.70, tol=0.001)
    r = compute_ets(base_activity(), 70.0, ETSExceptions(True, 0.30))
    check("both together: 0.70 x 0.95", r.allowances_due, 9489.3 * 0.70 * 0.95, tol=0.001)
    r = compute_ets(base_activity(year=2031), 70.0, ETSExceptions(True, 0.30))
    check("exceptions end 31 Dec 2030", r.allowances_due, 9489.3, tol=0.001)
    # calibration: the verifier reported 90% of our rebuild => cost scales to it; 0 => nothing due
    a = base_activity(year=2025)
    a.ets_calibration = 0.90
    r = compute_ets(a)
    check("calibrated CO2 (2025: CO2 only)", r.co2e_in_scope_t, 9342 * 0.90, tol=0.001)
    check_eq("basis says verifier", r.basis, "verifier")
    check("rebuild kept as a cross-check", r.rebuilt_co2e_t, 9342.0, tol=0.001)
    a.ets_calibration = 0.0
    r = compute_ets(a)
    check("reported zero: no allowances", r.allowances_due, 0.0, tol=0)
    check_eq("reported zero is explained", any("below 5,000 GT" in n for n in r.notes), True)


def test_ukets_rules():
    print("UK ETS: scheme start, exclusions, surrender dates (SI 2026/392 Sch. 2A):")
    from ghgcore.ukets import compute_ukets, surrender_date
    from ghgcore.ets_rules import UKETSExceptions
    v = Vessel("3", "UK COASTER", ShipType.GENERAL_CARGO, dwt=25_000, gt=18_000)
    leg = VoyageLeg(VoyageScope.OUT_OF_SCOPE, 8_000, [FuelConsumption(FuelType.HFO, 1_000)], uk_share=1.0)
    r = compute_ukets(AnnualActivity(v, 2025, [leg]))
    check("2025: scheme not started", r.cost_gbp, 0.0, tol=0)
    r = compute_ukets(AnnualActivity(v, 2027, [leg]), exceptions=UKETSExceptions(True, "Scottish ferry service"))
    check("excluded ship pays nothing", r.cost_gbp, 0.0, tol=0)
    check_eq("excluded flag", r.excluded, True)
    check_eq("2026 surrender is 30 April 2028", surrender_date(2026), "30 April 2028")
    check_eq("2027 surrender is 30 April 2028", surrender_date(2027), "30 April 2028")
    check_eq("2028 surrender is 30 April 2029", surrender_date(2028), "30 April 2029")
    # same gases and GWPs as the EU: 1000 t HFO -> 3163.1 t CO2e
    check("UK CO2e matches EU basis", compute_ukets(AnnualActivity(v, 2027, [leg])).co2e_in_scope_t, 3163.1)


def test_ets_combined():
    print("EU ETS and UK ETS together: scopes must not overlap:")
    from ghgcore.ets_combined import compute_ets_combined, check_disjoint
    v = Vessel("8", "BOTH", ShipType.GENERAL_CARGO, dwt=25_000, gt=18_000)
    eu_leg = VoyageLeg(VoyageScope.INTRA_EEA, 5_000, [FuelConsumption(FuelType.HFO, 1_000)], uk_share=0.0)
    uk_leg = VoyageLeg(VoyageScope.OUT_OF_SCOPE, 3_000, [FuelConsumption(FuelType.HFO, 500)], uk_share=1.0)
    ni_leg = VoyageLeg(VoyageScope.OUT_OF_SCOPE, 150, [FuelConsumption(FuelType.HFO, 10)], uk_share=0.5)
    a = AnnualActivity(v, 2027, [eu_leg, uk_leg, ni_leg])
    c = compute_ets_combined(a, 70.0, 40.0, 1.15)
    check_eq("clean activity has no overlap", c.warnings, [])
    # EU: 1000 t x 3.1631 = 3163.1 t x 100% x 70; UK: (500 + 10 x 0.5) x 3.1631 = 1597.4 t x 40 GBP x 1.15
    check("EU cost", c.eu.cost_eur, 3163.1 * 70, tol=0.001)
    check("UK cost GBP", c.uk.cost_gbp, 505 * 3.1631 * 40, tol=0.001)
    check("total in EUR", c.total_eur, 3163.1 * 70 + 505 * 3.1631 * 40 * 1.15, tol=0.001)
    both = VoyageLeg(VoyageScope.INTRA_EEA, 100, [FuelConsumption(FuelType.HFO, 5)], uk_share=1.0)
    check_eq("a leg in both schemes is flagged", len(check_disjoint(AnnualActivity(v, 2027, [both]))), 1)
    bad = VoyageLeg(VoyageScope.OUT_OF_SCOPE, 100, [FuelConsumption(FuelType.HFO, 5)], uk_share=0.7)
    check_eq("an impossible UK share is flagged", len(check_disjoint(AnnualActivity(v, 2027, [bad]))), 1)


def test_register_calibration():
    print("Register path: the bill uses the verifier's own ETS-scope figure:")
    import glob
    from ghgcore.exports import latest
    from ghgcore.thetis import load_thetis_cached, record_to_activity, ets_calibration
    recs = load_thetis_cached(latest(os.path.join(os.path.dirname(__file__), "..", "fixtures")))
    r = recs["9464663"]
    act = record_to_activity(r, year=2025, dwt=1.0)
    e = compute_ets(act)
    check("equals the reported figure (7,408.97 t)", e.co2e_in_scope_t, r.co2_ets_reported_t, tol=0.0001)
    check_eq("basis", e.basis, "verifier")
    # ships that reported zero ETS-scope CO2 are not charged
    zero = next(x for x in recs.values()
                if x.co2_ets_reported_t == 0 and x.ship_type is not None and (x.co2_intra_t or 0) + (x.co2_departed_t or 0) > 0)
    z = compute_ets(record_to_activity(zero, year=2025, dwt=1.0))
    check("reported zero => no cost", z.cost_eur, 0.0, tol=0)
    check_eq("calibration is zero", ets_calibration(zero), 0.0)
    # the register's distance is the whole year's; berth time must not shorten it
    check("CII distance = the register's total distance", act.total_distance_nm, r.est_distance_nm, tol=1e-9)


def test_deadlines_and_agreement():
    print("Compliance calendar + pool agreement draft:")
    from ghgcore.deadlines import deadlines_for, to_ics
    ds = deadlines_for(2026)
    check("deadline count", len(ds), 8, tol=0)
    check_eq("sorted ascending", all(ds[i].due <= ds[i+1].due
                                     for i in range(len(ds)-1)), True)
    check_eq("UK surrender for 2026 is 30 Apr 2028",
             any(d.due.isoformat() == "2028-04-30" and d.regime == "UK ETS" and d.what.startswith("Surrender") for d in ds), True)
    check("2025 has no UK ETS dates", sum(1 for d in deadlines_for(2025) if d.regime == "UK ETS"), 0, tol=0)
    check("2023 has no ETS or FuelEU dates", sum(1 for d in deadlines_for(2023) if d.regime in ("EU ETS", "FuelEU", "UK ETS")), 0, tol=0)
    check_eq("ETS surrender 30 Sep 2027",
             any(d.due.isoformat() == "2027-09-30" and d.regime == "EU ETS"
                 for d in ds), True)
    ics = to_ics(ds)
    check("ics events", ics.count("BEGIN:VEVENT"), 8, tol=0)
    check_eq("ics valid wrapper", ics.startswith("BEGIN:VCALENDAR")
             and "END:VCALENDAR" in ics, True)

    from ghgcore.pooling import PoolCandidate, suggest_pool
    from ghgcore.pool_agreement import draft_agreement
    pool = suggest_pool([PoolCandidate("1", "SURPLUS SHIP", 500.0, 88.0),
                         PoolCandidate("2", "DEFICIT SHIP", -300.0, 91.7)])
    md = draft_agreement(pool, 2026)
    check_eq("agreement carries pool CB",
             "+200.0 tCO₂e" in md, True)
    check_eq("registration deadline", "30 April 2027" in md, True)
    check_eq("draft disclaimer", "Not legal advice" in md, True)


def test_cii_calculator():
    print("CII calculator (owner data, G1-G5 + trajectory):")
    from ghgcore.cii_calc import CIIInput, SpeedProfile, compute_cii_full
    from ghgcore.cii import CIICorrections
    # Bulk 50,000 dwt, 3,000 t HFO, 50,000 nm, 2026 — same worked example as
    # the base engine, so the two must agree exactly.
    r = compute_cii_full(CIIInput(ShipType.BULK_CARRIER, dwt=50_000, year=2026,
                                  fuel_tonnes={FuelType.HFO: 3_000},
                                  distance_nm=50_000))
    check("CO2", r.co2_tonnes, 9342.0)
    check("attained", r.attained, 3.737, tol=0.001)
    check("required", r.required, 5.044, tol=0.001)
    check_eq("rating", r.rating, "A")
    check_eq("capacity basis", r.capacity_basis, "DWT")
    check_eq("owner data not flagged estimate", r.estimated_inputs, False)
    # boundaries: dd (0.86,0.94,1.06,1.18) x required 5.0446
    check("boundary A", r.boundaries["A"], 4.338, tol=0.002)
    check("boundary C", r.boundaries["C"], 5.347, tol=0.002)
    # already A -> no gap to a better band
    check_eq("no gap when A", r.gap_to_next_band_pct, None)
    # trajectory covers 2023-2030 and tightens
    check("trajectory years", len(r.trajectory), 8, tol=0)
    # 2030: Z=21.5% -> required = reference 5.6686 x 0.785 = 4.450
    check("2030 required tightens", r.trajectory[-1]["required"], 4.450, tol=0.002)

    # A mid-fleet ship that is C now and slips later — the sales moment.
    r2 = compute_cii_full(CIIInput(ShipType.BULK_CARRIER, dwt=50_000, year=2026,
                                   fuel_tonnes={FuelType.HFO: 4_300},
                                   distance_nm=50_000))
    # attained = 4300*3.114e6/(50000*50000) = 5.356 -> ratio 1.062 -> D
    check("mid-fleet attained", r2.attained, 5.356, tol=0.002)
    check_eq("rated D in 2026", r2.rating, "D")
    # to reach C: cut to boundary C 5.347 -> (1-5.347/5.356)*100 = 0.17%
    check("cut to reach C", r2.reduction_to_reach["C"], 0.2, tol=0.5)
    check_eq("gap = cut to C", r2.gap_to_next_band_pct, r2.reduction_to_reach["C"])
    check_eq("E by 2030 at same performance",
             r2.trajectory[-1]["rating"], "E")

    # Speed-based estimation: 12 t/day at 14 kn -> 11 kn for 200 sea days
    # ratio 11/14 = 0.7857; ^3 = 0.4851; 12*0.4851 = 5.821 t/day
    # main = 1164.3 t; aux 2 t/day x 200 = 400 t; distance = 11*24*200 = 52,800
    sp = SpeedProfile(ref_cons_t_per_day=12, ref_speed_kn=14, actual_speed_kn=11,
                      sea_days=200, aux_t_per_day_at_sea=2)
    fuels, dist, _ = sp.resolve()
    check("cube-law main fuel", fuels[FuelType.HFO], 1164.3, tol=0.002)
    check("derived distance", dist, 52_800, tol=0)
    r3 = compute_cii_full(CIIInput(ShipType.BULK_CARRIER, dwt=50_000, year=2026,
                                   speed_profile=sp))
    check_eq("speed path flagged estimate", r3.estimated_inputs, True)
    # CO2 = 1164.3*3.114 + 400*3.206 = 3625.6 + 1282.4 = 4908.0 t
    check("speed-path CO2", r3.co2_tonnes, 4908.0, tol=0.002)

    # G5 corrections reduce attained
    r4 = compute_cii_full(CIIInput(ShipType.BULK_CARRIER, dwt=50_000, year=2026,
                                   fuel_tonnes={FuelType.HFO: 3_000},
                                   distance_nm=50_000,
                                   corrections=CIICorrections(
                                       excluded_co2_t=342.0, basis="STS ops, verifier ref 12")))
    # CO2 9342-342 = 9000 -> attained 3.6
    check("G5 excluded CO2 applied", r4.attained, 3.6, tol=0.002)
    check_eq("G5 noted", any("MEPC.355(78)" in n for n in r4.notes), True)

    # GT-based type uses GT
    r5 = compute_cii_full(CIIInput(ShipType.CRUISE, dwt=12_000, gt=100_000,
                                   year=2026, fuel_tonnes={FuelType.HFO: 9_000},
                                   distance_nm=60_000))
    check_eq("cruise capacity basis", r5.capacity_basis, "GT")
    check("cruise attained on GT", r5.attained, 4.671, tol=0.002)
    # missing inputs raise
    try:
        compute_cii_full(CIIInput(ShipType.TANKER, dwt=50_000, year=2026))
        check_eq("missing fuel raises", False, True)
    except ValueError:
        check_eq("missing fuel raises", True, True)


def test_public_data_fuel_assumption():
    print("Public-data fuel assumption (surplus side must be visible):")
    from ghgcore.thetis import ThetisRecord, assumed_fuel, record_to_activity
    # An all-HFO assumption puts every ship above every FuelEU target, which
    # would hide the surplus side of the pooling market entirely.
    bulk = ThetisRecord("1", "BULKER", ShipType.BULK_CARRIER, "Bulk carrier",
                        co2_tonnes=10_000, fuel_tonnes=3_211,
                        est_distance_nm=40_000)
    lng = ThetisRecord("2", "GASSHIP", ShipType.LNG_CARRIER, "LNG carrier",
                       co2_tonnes=10_000, fuel_tonnes=3_636,
                       est_distance_nm=40_000)
    check_eq("bulk assumes HFO", assumed_fuel(bulk), FuelType.HFO)
    check_eq("LNG carrier assumes LNG", assumed_fuel(lng), FuelType.LNG)
    # fuel mass is backed out with the assumed fuel's CF, not always 3.114
    act = record_to_activity(lng, year=2025, dwt=1.0)
    tonnes = act.total_fuel_by_type()[FuelType.LNG]
    check("LNG mass uses CF 2.750", tonnes, 10_000 / 2.750, tol=0.001)
    check_eq("assumption disclosed in the leg", "assumed LNG" in act.legs[0].description, True)
    # and the result must be able to come out positive
    r = compute_fueleu(act)
    check_eq("LNG carrier can show surplus", r.compliance_balance_tco2e > 0, True)
    r2 = compute_fueleu(record_to_activity(bulk, year=2025, dwt=1.0))
    check_eq("HFO bulker still deficit", r2.compliance_balance_tco2e < 0, True)


def test_privacy_controls():
    print("Data-control layer (suppression, requests, rate limit):")
    import tempfile, os as _os
    from ghgcore import privacy as pv
    tmp = tempfile.mkdtemp()
    pv.SUPPRESSED_FILE = _os.path.join(tmp, "suppressed_imos.txt")
    pv.REQUESTS_FILE = _os.path.join(tmp, "requests.jsonl")
    pv._DIR = tmp
    pv._suppressed_cache, pv._suppressed_mtime = None, -1.0

    check_eq("clean list -> nothing suppressed", pv.is_suppressed("9464663"), False)
    # a suppression request must take effect immediately, without human action
    pv.log_request("suppress", ["9464663"], "Test Owner Ltd", "ops@testowner.com")
    check_eq("suppress request applies at once", pv.is_suppressed("9464663"), True)
    check_eq("other ships unaffected", pv.is_suppressed("9463633"), False)
    # requests are logged for follow-up
    with open(pv.REQUESTS_FILE, encoding="utf-8") as f:
        import json as _json
        rec = _json.loads(f.readline())
    check_eq("request logged with kind", rec["kind"], "suppress")
    check_eq("request logged with contact", rec["contact_email"], "ops@testowner.com")
    # validation
    try:
        pv.log_request("claim", ["9464663"], "X", "not-an-email")
        check_eq("bad email rejected", False, True)
    except ValueError:
        check_eq("bad email rejected", True, True)
    try:
        pv.log_request("bogus", ["9464663"], "X", "a@b.com")
        check_eq("bad kind rejected", False, True)
    except ValueError:
        check_eq("bad kind rejected", True, True)
    # rate limiter
    key = "test-ip"
    allowed = sum(1 for _ in range(5) if pv.rate_limit_ok(key, limit=3, window_s=60))
    check("limiter allows exactly the budget", allowed, 3, tol=0)
    check_eq("separate keys independent", pv.rate_limit_ok("other-ip", limit=3), True)


def test_scorecard():
    print("Scorecard composition:")
    sc = build_scorecard(base_activity())
    # health = A(100) - 15 (FuelEU deficit) = 85
    check("regulatory health", sc.regulatory_health, 85, tol=0)
    # cost = ETS cost + FuelEU penalty
    check("cost exposure", sc.cost_exposure_eur, sc.ets.cost_eur + sc.fueleu.penalty_eur)
    assert sc.actions, "actions list must not be empty"
    check_eq("has actions", True, True)


def _raises(fn) -> bool:
    try:
        fn()
    except ValueError:
        return True
    return False


def test_fueleu_penalty_rules():
    print("FuelEU: applicability, Art. 23(2) multiplier, pooling cost:")
    from ghgcore.fueleu import penalty_multiplier, penalty_per_tco2e
    check("multiplier n=1", penalty_multiplier(1), 1.0, tol=0)
    check("multiplier n=3 = 1 + 2/10", penalty_multiplier(3), 1.2, tol=0)
    # 1e6 / (91.74 x 41,000) x 2,400 = 638.07 EUR per tCO2e
    check("statutory EUR per tCO2e at HFO intensity", penalty_per_tco2e(91.74), 638.07, tol=0.0001)
    r = compute_fueleu(base_activity(), consecutive_deficit_years=3)
    check("third consecutive deficit: 186,310 x 1.2", r.penalty_eur, 223_572, tol=0.001)
    # CB = (89.3368 - 91.74) x 121.5e6 g = -291.9888 t; x EUR 110 = 32,118.77
    r = compute_fueleu(base_activity(), pool_price_eur_per_tco2e=110.0)
    check("pooling cost at EUR 110/t", r.pooling_cost_eur, 32_118.77, tol=0.0001)
    check("statutory penalty unchanged", r.penalty_eur, 186_310, tol=0.01)
    r = compute_fueleu(base_activity(year=2024))
    check_eq("2024: FuelEU not yet in force", r.applicable, False)
    check("2024: no penalty", r.penalty_eur, 0.0, tol=0)
    a = base_activity(year=2025)
    a.ets_calibration = 0.0
    r = compute_fueleu(a)
    check_eq("verifier reported no ETS scope: outside FuelEU", r.applicable, False)
    check("no phantom FuelEU penalty", r.penalty_eur, 0.0, tol=0)


def test_whatif_physics():
    print("What-if: speed exponent, auxiliary share, berth untouched:")
    from ghgcore.whatif import apply_whatif, sea_fuel_ratio
    check("cube law, -10%: 0.9^2", sea_fuel_ratio(-10, 3.0), 0.81, tol=0.0001)
    check("exponent 2.6, -10%: 0.9^1.6", sea_fuel_ratio(-10, 2.6), 0.84486, tol=0.0001)
    check("20% auxiliary: 0.8 x 0.81 + 0.2 / 0.9", sea_fuel_ratio(-10, 3.0, 20), 0.87022, tol=0.0001)
    v = Vessel("9999999", "MV HANDCALC", ShipType.BULK_CARRIER, dwt=50_000, gt=30_000)
    act = AnnualActivity(v, 2026, [VoyageLeg(VoyageScope.INTRA_EEA, 1000, [FuelConsumption(FuelType.HFO, 1000)]),
                                   VoyageLeg(VoyageScope.AT_BERTH_EEA, 0, [FuelConsumption(FuelType.MDO_MGO, 100)])])
    w = apply_whatif(act, 0, -10)
    check("sea leg scaled", w.legs[0].fuel_consumed[0].tonnes, 810.0, tol=0.0001)
    check("berth leg not scaled by sea speed", w.legs[1].fuel_consumed[0].tonnes, 100.0, tol=0)


def test_g5_corrections():
    print("G5 (MEPC.355(78)) itemised corrections:")
    from ghgcore.g5 import (G5Deduction, G5Input, af_tanker, apply_g5, reefer_tonnes,
                            year_factor)
    from ghgcore.cii_calc import CIIInput, compute_cii_full
    check("(0.75 - 0.03y), 2026", year_factor(2026), 0.66, tol=0.0001)
    check("(0.75 - 0.03y), 2023", year_factor(2023), 0.75, tol=0.0001)
    check("AF_Tanker,STS at 100,000 dwt = 6.1742 x 1e5^-0.246", af_tanker(100_000, False), 0.36356, tol=0.001)
    check("reefer default: 2.75 x 24 x 175 x 1,000 days", reefer_tonnes(1000, 175), 11.55, tol=0.0001)
    fuels = {FuelType.HFO: 10_000.0}
    g = apply_g5(fuels, 100_000, ShipType.CONTAINER, 50_000, 2026,
                 G5Input([G5Deduction("electrical_reefer", FuelType.HFO, 11.55)]))
    # 3.114 x (10,000 - 0.66 x 11.55) = 31,116.26 t
    check("reefer deduction weighted by 0.66", g.co2_numerator_t, 31_116.26, tol=0.00001)
    res = compute_cii_full(CIIInput(ShipType.CONTAINER, dwt=50_000, year=2026, fuel_tonnes=fuels,
                                    distance_nm=100_000,
                                    g5=G5Input([G5Deduction("electrical_reefer", FuelType.HFO, 11.55)])))
    check("attained with reefer correction", res.attained, 6.22325, tol=0.0001)
    ice = G5Input([G5Deduction("voyage_ice", FuelType.HFO, 200, 1000)], ice_class="IA")
    g = apply_g5(fuels, 100_000, ShipType.BULK_CARRIER, 50_000, 2026, ice)
    check("ice voyage: fuel and distance both removed", g.co2_numerator_t * 1e6 / (50_000 * g.distance_nm),
          6.16509, tol=0.0001)
    check_eq("boiler correction refused on a bulk carrier", _raises(lambda: apply_g5(
        fuels, 1e5, ShipType.BULK_CARRIER, 5e4, 2026, G5Input([G5Deduction("boiler", FuelType.HFO, 10)]))), True)
    check_eq("STS and FC_electrical cannot be combined", _raises(lambda: apply_g5(
        fuels, 1e5, ShipType.TANKER, 1e5, 2026, G5Input([G5Deduction("sts", FuelType.HFO, 100),
                                                          G5Deduction("electrical_discharge", FuelType.HFO, 10)]))), True)
    check_eq("ice adjustment needs an ice class", _raises(lambda: apply_g5(
        fuels, 1e5, ShipType.BULK_CARRIER, 5e4, 2026, G5Input([G5Deduction("voyage_ice", FuelType.HFO, 10, 10)]))), True)
    check_eq("deductions cannot exceed the fuel", _raises(lambda: apply_g5(
        fuels, 1e5, ShipType.BULK_CARRIER, 5e4, 2026, G5Input([G5Deduction("voyage_safety", FuelType.HFO, 20_000, 10)]))), True)


def test_speed_exponent():
    print("Speed estimate with an adjustable exponent:")
    from ghgcore.cii_calc import SpeedProfile
    f3, _, _ = SpeedProfile(30, 14, 12, 200).resolve()
    check("cube law: 30 x (12/14)^3 x 200", f3[FuelType.HFO], 3778.43, tol=0.0001)
    f26, _, _ = SpeedProfile(30, 14, 12, 200, speed_exponent=2.6).resolve()
    check("exponent 2.6: 30 x (12/14)^2.6 x 200", f26[FuelType.HFO], 4018.68, tol=0.0001)
    check_eq("exponent outside 2-4.5 refused", _raises(lambda: SpeedProfile(30, 14, 12, 200, speed_exponent=6).resolve()), True)


def test_charter_split():
    print("Owner / time-charterer split (BIMCO clauses, pro rata):")
    from datetime import date
    from ghgcore.charter import split
    s = split(2025, date(2025, 3, 1), date(2025, 8, 31), {"EU ETS allowances": 100_000})
    check("184 days on charter", s.days_on_charter, 184, tol=0)
    check("charterer share 184/365", s.charterer_share, 0.5041, tol=0.0001)
    check("charterer pays 50,411", s.total_charterer_eur, 50_411, tol=0)
    check("owner pays the rest", s.total_owner_eur, 49_589, tol=0)
    s = split(2024, date(2023, 12, 1), date(2024, 1, 31), {"x": 366})
    check("clipped to the year, leap year", s.days_on_charter, 31, tol=0)
    check_eq("end before start refused", _raises(lambda: split(2025, date(2025, 5, 1), date(2025, 4, 1), {})), True)


def test_owner_bill_split():
    print("Owner-data bill by voyage scope:")
    from ghgcore.ownerbill import ScopeSplit, build_activity
    from ghgcore.ets_combined import compute_ets_combined
    act, rows = build_activity("MV OWN", "", ShipType.BULK_CARRIER, 50_000, 0, 2026, {FuelType.HFO: 4300},
                               ScopeSplit(intra_eea=40, extra_eea=30, berth_eea=10, uk_domestic=5))
    c = compute_ets_combined(act, 85.0, 40.0, 1.15)
    # EU fuel in scope = 4,300 x (0.40 + 0.5 x 0.30 + 0.10) = 2,795 t; x (3.114 + 0.0014 + 0.0477) = 8,840.86 tCO2e
    check("EU ETS CO2e in scope", c.eu.co2e_in_scope_t, 8_840.86, tol=0.0001)
    check("EU ETS cost at EUR 85", c.eu.cost_eur, 751_473, tol=0.0001)
    # UK: 215 t x 3.1631 = 680.07 tCO2e x GBP 40
    check("UK ETS cost", c.uk.cost_gbp, 27_203, tol=0.0001)
    check_eq("rows include the remainder outside scope", rows[-1]["key"], "outside")
    check_eq("shares over 100% refused", _raises(lambda: ScopeSplit(intra_eea=80, extra_eea=30).validate()), True)


def test_ukets_public_data_not_observable():
    print("UK ETS on public data: not observable, not zero-by-assumption:")
    from ghgcore.ukets import compute_ukets
    r = compute_ukets(base_activity(year=2027))
    check_eq("public-style legs have no UK share", r.data_observable, False)


def test_claim_abuse_limits():
    print("Operator requests are bounded (unauthenticated form):")
    from ghgcore import privacy as pv
    check_eq("21 IMOs in one request refused", _raises(lambda: pv.log_request(
        "suppress", [str(9100000 + i) for i in range(21)], "X", "a@b.co")), True)
    check_eq("non-IMO strings refused", _raises(lambda: pv.log_request("claim", ["12ab567"], "X", "a@b.co")), True)
    check_eq("oversized message refused", _raises(lambda: pv.log_request(
        "claim", ["9464663"], "X", "a@b.co", "m" * 2001)), True)
    old_file, old_auto = pv.SUPPRESSED_FILE, list(pv._auto_suppressed)
    old_req = pv.REQUESTS_FILE
    import tempfile
    tmp = tempfile.mkdtemp()
    pv.SUPPRESSED_FILE, pv.REQUESTS_FILE = os.path.join(tmp, "s.txt"), os.path.join(tmp, "r.jsonl")
    pv._suppressed_mtime = -1.0
    try:
        pv._auto_suppressed[:] = []
        applied = [pv.log_request("suppress", [str(9200000 + 20 * k + i) for i in range(20)], "X", "a@b.co").applied
                   for k in range(4)]
        check_eq("instant hiding stops at the daily budget (60)", applied, [True, True, True, False])
        check_eq("the fourth batch is not hidden", pv.is_suppressed("9200060"), False)
    finally:
        pv.SUPPRESSED_FILE, pv.REQUESTS_FILE = old_file, old_req
        pv._auto_suppressed[:] = old_auto
        pv._suppressed_mtime = -1.0


def test_access_toggle():
    print("Calculator access gate is off by default and switchable:")
    from ghgcore import access
    old = os.environ.pop("CARBONKEEL_REQUIRE_KEY", None)
    try:
        check_eq("open by default", access.required(), False)
        os.environ["CARBONKEEL_REQUIRE_KEY"] = "1"
        check_eq("CARBONKEEL_REQUIRE_KEY=1 closes it", access.required(), True)
    finally:
        os.environ.pop("CARBONKEEL_REQUIRE_KEY", None)
        if old is not None:
            os.environ["CARBONKEEL_REQUIRE_KEY"] = old


if __name__ == "__main__":
    for fn in (test_cii, test_cii_z_fallback, test_cii_gas_carrier_split,
               test_cii_gt_and_lng_types,
               test_euets, test_euets_extra_eea_2025, test_ets_rules_and_exceptions,
               test_ukets_rules, test_ets_combined, test_register_calibration,
               test_fueleu, test_fueleu_targets, test_nzf,
               test_ports_scoping, test_ukets, test_projection,
               test_engine_type_lng, test_certified_override_and_g5,
               test_pooling, test_eexi, test_eexi_custom,
               test_messy_ingestion, test_llm_mapper_contract,
               test_deadlines_and_agreement, test_cii_calculator,
               test_public_data_fuel_assumption,
               test_privacy_controls, test_scorecard,
               test_fueleu_penalty_rules, test_whatif_physics, test_g5_corrections,
               test_speed_exponent, test_charter_split, test_owner_bill_split,
               test_ukets_public_data_not_observable, test_access_toggle,
               test_claim_abuse_limits):
        fn()
        print()
    print(f"All checks passed ({PASS}).")
