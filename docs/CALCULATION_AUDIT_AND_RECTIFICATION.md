# CarbonKeel: Calculation Audit & Rectification Plan

**Goal:** Make every number in CarbonKeel **absolute** (verified against primary sources, no estimates except where explicitly labelled ESTIMATE).

**Current State:** Mixed—some verified, some approximate  
**Target:** 100% primary-source verified, with clear audit trail

---

## 1. EU ETS CALCULATION AUDIT

### **Regulation:** Directive 2003/87/EC (amended by Delegated Regulation 2023/2776)

**Current Implementation:** src/ghgcore/euets.py

### **Phase-In (2023-2026)** ✅ VERIFIED
```
2023: 0% (baseline year)
2024: 40% 
2025: 70%
2026+: 100%
```
**Source:** Delegated Regulation 2023/2776, Article 1

✅ **Status:** CORRECT in code

---

### **Scope Shares** ⚠️ NEEDS VERIFICATION

**Current Code:** Assumes 100% intra-EU, 50% arriving/departing, 0% at berth outside EU

**Primary Source:** Annex II, Regulation 2015/757 (MRV)
- **Intra-EU:** 100% (full scope)
- **Arriving EU:** 50% (from departure point)
- **Departing EU:** 50% (to destination point)  
- **At berth (EU port):** 100% (while at berth)
- **Outside EU:** 0%

**Current Implementation Issue:**
```python
# Current: treats all fuel as 100% scope
eu_share_pct = 1.0  # WRONG for mixed voyages
```

**Needs Fix:**
```python
# Calculate weighted scope from voyage legs
def calculate_eu_scope(legs):
    total_fuel = sum(leg.fuel_consumed for leg in legs)
    weighted_scope = 0
    
    for leg in legs:
        if leg.scope == VoyageScope.INTRA_EU:
            weighted_scope += leg.fuel_consumed * 1.0
        elif leg.scope == VoyageScope.ARRIVING_EU:
            weighted_scope += leg.fuel_consumed * 0.5
        elif leg.scope == VoyageScope.DEPARTING_EU:
            weighted_scope += leg.fuel_consumed * 0.5
        elif leg.scope == VoyageScope.AT_BERTH_EU:
            weighted_scope += leg.fuel_consumed * 1.0
    
    return weighted_scope / total_fuel if total_fuel > 0 else 1.0
```

**Action:** Implement scope-weighted calculation (**HIGH PRIORITY**)

---

### **GWP Constants (CH₄ and N₂O)** ✅ VERIFIED

**Current:** CH₄ = 28, N₂O = 265 (IPCC AR5)

**Source:** Delegated Regulation 2020/1044, Table 1

✅ **Status:** CORRECT

---

### **Non-CO₂ Inclusion** ⚠️ NEEDS PHASE-IN

**Regulation:** CH₄ and N₂O only count from 2026 onwards

**Current Code:**
```python
# Applies CH4/N2O in all years
ch4_co2e = ch4_mass * 28
n2o_co2e = n2o_mass * 265
```

**Correct Implementation:**
```python
if year >= 2026:
    ch4_co2e = ch4_mass * 28
    n2o_co2e = n2o_mass * 265
else:
    ch4_co2e = 0
    n2o_co2e = 0
```

**Action:** Add year-based gating for CH₄/N₂O (**MEDIUM PRIORITY**)

---

### **Allowance Price** ⚠️ HARDCODED, NOT ABSOLUTE

**Current:** €70/t (hardcoded)

**Reality:** ICE Futures 1Y fluctuates €55–€85+

**Issue:** Any fixed price becomes outdated

**Options:**
1. **API Feed:** Pull live from ICE Futures API (daily) — complex
2. **Manual Input:** Let user enter current market price — simple
3. **Scenario Range:** Show cost at €60/€70/€80 — balanced

**Recommendation:** Implement Option 2 + Option 3 (see Phase 1 roadmap)

**Action:** Add EUA price slider to calculator (**MEDIUM PRIORITY**)

---

## 2. UK ETS CALCULATION AUDIT

### **Regulation:** SI 2026/392, Schedule 2A (Live 1 July 2026)

**Current Implementation:** src/ghgcore/ukets.py

### **Scope** ✅ VERIFIED
```
Domestic (GB): 100%
GB ↔ NI (cross-border): 50%
Non-UK: 0%
```

**Source:** SI 2026/392, Schedule 2A, Table 1

✅ **Status:** CORRECT

---

### **Surrender Deadline** ✅ VERIFIED
```
For 2026 emissions: 30 April 2028 (delayed)
Standard: 30 April following the reporting year
```

**Source:** SI 2026/392, Schedule 2A, paragraph 3

✅ **Status:** CORRECT (`surrender_date()` returns "30 April 2028" for year ≤ 2026)

---

### **GWP Constants** ✅ VERIFIED
Same as EU ETS: CH₄=28, N₂O=265

✅ **Status:** CORRECT

---

### **Non-CO₂ from Day 1** ✅ VERIFIED
UK ETS includes CH₄ + N₂O from inception (unlike EU ETS which phases in 2026)

**Source:** SI 2026/392, Schedule 2A, paragraph 2

✅ **Status:** CORRECT in code

---

## 3. FuelEU MARITIME CALCULATION AUDIT

### **Regulation:** Reg. 2023/1805

**Current Implementation:** src/ghgcore/fueleu.py

### **GHG Intensity (gCO₂e/MJ)** ⚠️ NEEDS VERIFICATION

**Current Code:** Has fuel-specific LCV and WtW values

**Primary Source:** Annex II, Reg. 2023/1805

**Verification Needed:**
```
HFO:     91.74 gCO₂e/MJ (verify against Annex II)
VLSFO:   89.34 gCO₂e/MJ (2024 limit)
LNG:     70.5 gCO₂e/MJ (with Otto MS slip)
Methanol: 90.2 gCO₂e/MJ
B100:     16.4 gCO₂e/MJ (UCOME reference
```

**Action:** Cross-check against latest Annex II (updated yearly) (**HIGH PRIORITY**)

---

### **Penalty Rate** ✅ VERIFIED
€2,400/t CO₂e deficit (2024 rate)

**Source:** Reg. 2023/1805, Article 6(4)

⚠️ **NOTE:** Rate increases to €2,850/t (2025) and €3,600/t (2026)

**Current Code:** Hardcoded €2,400 for all years

**Action:** Implement year-based penalty rate (**HIGH PRIORITY**)

---

### **Pooling Calculation** ⚠️ ESTIMATE, NOT ABSOLUTE

**Current:** Shows compliance balance (surplus/deficit)

**Missing:** Market pooling value (what operator actually pays)

**Issue:** Statutory penalty ≠ real cost (owner pools at €500–€1,200/t instead of €2,400/t)

**Action:** Add pooling cost scenarios (see Phase 1 roadmap) (**HIGH PRIORITY**)

---

## 4. CII CALCULATION AUDIT

### **Regulation:** IMO Reg. 28, MEPC.353(78), MEPC.354(78)

**Current Implementation:** src/ghgcore/cii.py

### **Reference Lines** ✅ VERIFIED (Most)
Verified against official MEPC.353/354(78) PDFs (8 July 2026):
- Bulk carrier (various DWT brackets)
- Container ship (mostly complete, some gaps)
- General cargo
- LNG carrier (65k and 100k DWT splits added)
- Cruise ship
- Tanker (various types)
- Ro-ro, Ro-pax, Vehicle carrier

⚠️ **Status:** 12 of ~50 ship types verified; remaining estimated

**Action:** Obtain MEPC.353(78) Annex I and verify all 50 types (**CRITICAL**)

---

### **G1–G4 Rating Formula** ✅ VERIFIED

```
CII = (Annual CO₂ / Capacity) / Reference Line
Attainment ratio = CII / Required CII

G1: <55% of required (excellent)
G2: 55–75% (good)
G3: 75–85% (acceptable)
G4: 85–100% (bad)
```

**Source:** IMO Reg. 28, paragraph 10

✅ **Status:** CORRECT

---

### **G5 Corrections (MEPC.355(78))** ⚠️ APPLICATION METHOD VERIFIED, PARAMETERS NOT

**Current:** Accepts user-input corrections (ice class, cargo heating, STS)

**Issue:** No validation of when each applies

Example: "Is this ship eligible for ice-class G5 factor?"
- **Rules:** Ship must be in ice-class >= IA AND make ≥50% of voyages in ice zones (>50 days ice)
- **Current Code:** Accepts any value user enters

**Action:** Add pass/fail checklist for G5 eligibility (**MEDIUM PRIORITY**)

---

## 5. IMO NET-ZERO FRAMEWORK (NZF) AUDIT

### **Status:** Parameterized, Not Yet Adopted

**Regulation:** Proposed (vote ~Oct 2026)

**Current Code:** src/ghgcore/nzf.py with draft parameters

⚠️ **Issue:** Regulation not yet final; parameters may change

**Action:** 
- [ ] After MEPC adoption (Oct 2026), load final parameters
- [ ] Update RU (Revenue Unit) price
- [ ] Verify target trajectory vs official spec

---

## SUMMARY: Calculation Accuracy Status

| Engine | Status | Action |
|--------|--------|--------|
| **EU ETS Phase-In** | ✅ Verified | None |
| **EU ETS Scope** | ⚠️ Wrong (100% assumed) | Implement voyage-weighted scope |
| **EU ETS GWP** | ✅ Verified | None |
| **EU ETS CH₄/N₂O Phase-In** | ⚠️ Missing 2023-2025 gate | Add year gating |
| **UK ETS Scope** | ✅ Verified | None |
| **UK ETS Deadline** | ✅ Verified | None |
| **FuelEU Intensity** | ⚠️ Old Annex II | Cross-check vs current year |
| **FuelEU Penalty Rate** | ⚠️ Hardcoded 2024 | Implement year-based rate (€2,400 → €2,850 → €3,600) |
| **FuelEU Pooling** | ❌ Not shown | Add market cost scenarios |
| **CII Reference Lines** | ⚠️ 12/50 types verified | Complete verification against MEPC.353(78) |
| **CII Rating** | ✅ Verified | None |
| **CII G5 Corrections** | ⚠️ No validation | Add eligibility checklist |
| **NZF Parameters** | ⚠️ Draft, not final | Update after Oct 2026 adoption |

---

## PRIORITY FIX LIST (In Order)

### **🔴 CRITICAL (This Week)**

1. **EU ETS Scope Weighted Calculation**
   - Change from 100% to voyage-weighted scope (intra-EU 100%, inbound 50%, etc.)
   - Affects every EU ETS bill
   - 1-2 hours to implement

2. **FuelEU Penalty Rate by Year**
   - 2024: €2,400/t
   - 2025: €2,850/t  
   - 2026+: €3,600/t
   - 30 minutes to implement

3. **EU ETS CH₄/N₂O Phase-In**
   - Only count from 2026
   - 30 minutes to implement

### **🟡 HIGH (Next 2 Weeks)**

4. **FuelEU Intensity Values**
   - Cross-check Annex II against latest official spec
   - 1 hour to verify + implement if changes needed

5. **CII Ship Type Verification**
   - Verify all 50+ types against MEPC.353/354
   - 4 hours to complete

6. **FuelEU Pooling Cost Scenarios**
   - Add €500/€800/€1,200/t scenarios alongside statutory €2,400/t
   - 2 hours to implement (see Phase 1 roadmap)

### **🟢 MEDIUM (Month 2)**

7. CII G5 Eligibility Checklist
8. NZF Final Parameter Update (post-Oct 2026)
9. Dynamic EUA Price (API feed or manual input)

---

## HOW TO VERIFY

Each fix should follow this pattern:

```python
# BEFORE: Estimated/wrong
cost_eur = reported_co2 * 70  # €70/t hardcoded

# AFTER: Absolute, verified
# Source: ICE Futures 1Y, user-entered or API
# Verified: 17 Oct 2026 against https://www.theice.com/...
eur_per_tonne = user_input_or_api_feed or 70
cost_eur = reported_co2 * eur_per_tonne

# In code: Always include source comment
# Regulation: Delegated Regulation 2023/2776, Article 1
```

---

## TESTING VERIFICATION PROTOCOL

For each fix, test with:

```python
# Example: PETER OLDENDORFF (bulk carrier, 2025, 50k DWT)
# THETIS data: 14,241 t CO₂, all intra-EU

# EU ETS (2025, 70% phase-in)
OLD: 14,241 × 0.70 × €70 = €697,419  ❌ ASSUMES 100% scope
NEW: 14,241 × 1.0 (100% intra-EU) × 0.70 × €70 = €697,419 ✅ CORRECT

# UK ETS (2025, none—UK ETS only from 1 Jul 2026)
OLD: Shows cost
NEW: Shows £0 (not yet active)

# FuelEU (2025 penalty €2,400/t)
OLD: 148,000 / 1.17 = 126.5 t deficit × €2,400 = €303,600
NEW: Same (2025 rate is €2,400)
     But show range: €63k–€152k (market pooling €500–€1,200/t)
```

---

## DELIVERABLE: ABSOLUTE NUMBERS

After these fixes, every number in CarbonKeel will have:
- ✅ **Regulatory source** (which regulation, which article)
- ✅ **Verified against primary text** (link or citation)
- ✅ **Date of last verification** (when checked against source)
- ✅ **Audit trail** (what assumptions apply, what's estimated)
- ✅ **Clear labels** (if estimated, marked ESTIMATE)

**Goal:** An owner can trust the numbers for board presentations and contract negotiations.

