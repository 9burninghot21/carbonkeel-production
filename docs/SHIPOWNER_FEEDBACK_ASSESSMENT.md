# CarbonKeel: Shipowner Feedback & Priority Assessment

## Source
Commercial shipowner / technical manager operating an international fleet.
**Verdict:** "Promising as a sanity-check tool, but cannot rely on it for contractual or financial commitments."

---

## 1. TRUST & TRANSPARENCY ISSUES

### **Issue: "One person, not a bot" undermines confidence**

**Owner's Pain:**
- Managing multi-million-euro exposure under EU ETS/FuelEU
- Feels like a "hobbyist side-project"
- No clear accountability if calculations fail

**Fix Required:**
Present formal corporate identity:
- [ ] Name naval architects, software engineers, maritime consultants
- [ ] Legal entity details
- [ ] References to accreditation/verification frameworks
- [ ] Clear liability statement

**Priority:** 🔴 **CRITICAL** — Must fix BEFORE contacting enterprise prospects  
**Timeline:** Implement before Phase 1 customer outreach (Week 1)

---

### **Issue: Broken Privacy & Data Handling Pages (403)**

**Owner's Pain:**
- Site asks for sensitive data (BDNs, consumption, fleet IMOs)
- Privacy link broken → signals carelessness
- No clarity on client-side vs. server-side data handling

**Fix Required:**
Publish enterprise-grade policy:
- [ ] Complete, accessible Privacy Policy
- [ ] NDA terms for fleet data
- [ ] **Explicit statement:** "Data processed entirely client-side in browser; zero operational logs stored on servers"
- [ ] GDPR/commercial confidentiality compliance

**Priority:** 🔴 **CRITICAL** — Blocks enterprise pilots  
**Timeline:** Week 1

---

### **Issue: Access Key Gate = Friction Point**

**Owner's Pain:**
- "Enter your access key... Just ask" = must email to test
- Kills spontaneous adoption
- Owner will switch to DNV Emissions Connect or ZeroNorth instead

**Fix Required (Choose One):**

**Option A (Recommended for now):**
- [ ] Keep key gate for /app
- [ ] BUT: Add prominent "Request Free Demo Key" button on landing page
- [ ] Auto-issue key within 2 hours (founder/script)
- [ ] Show sandbox results WITHOUT key (non-saved)

**Option B (Aggressive Growth):**
- [ ] Remove key gate entirely
- [ ] Open /app to all
- [ ] Reserve keys only for saved fleets / API access

**Priority:** 🟡 **HIGH** — Blocks first-contact conversion  
**Timeline:** Implement Option A by Week 2

---

## 2. OPERATIONAL BLIND SPOTS (Data Gaps)

### **Issue: Voyage-Type Splitting (50% vs 100% ETS)**

**Owner's Reality:**
- Intra-EU voyages = 100% ETS surrender
- Extra-EU (inbound/outbound) = 50% surrender
- Flat calculation on total fuel = **inaccurate liability forecast**

**Example:**
A 50,000 DWT tanker doing:
- 60% intra-EU routes (100% scope)
- 40% extra-EU routes (50% scope)
- Current CarbonKeel: treats all 100%
- **Real liability:** ~30% lower than shown

**Fix Required:**
- [ ] Vessel profile: allow % split (Intra-EU / Inbound / Outbound / Berth)
- [ ] Recalculate EU ETS with correct scope percentages
- [ ] Show breakdown: "Your €200k cost assumes 60% EU scope; adjust for actual voyage profile"

**Priority:** 🔴 **CRITICAL for accuracy** — without this, CarbonKeel gives wrong numbers  
**Timeline:** Phase 0.5 UAT (before pilot customers)

---

### **Issue: Charter Party Allocation (BIMCO)**

**Owner's Reality:**
- Owner rarely pays 100% of carbon bill
- Under time charters, charterer pays EUAs + FuelEU deficit
- "Ship's Total Bill" doesn't tell owner what they owe vs. charterer

**Example:**
€500k ship bill, but under charter 2026-01 to 2026-06:
- Owner owes: ~€250k (6 months fixed cost)
- Charterer owes: ~€250k (fuel risk during charter)
- But current CarbonKeel shows: €500k (unclear who pays what)

**Fix Required:**
- [ ] Charter Allocation toggle: input start/end dates
- [ ] Auto-apportion ETS cost by month
- [ ] Generate "Owner vs. Charterer Liability" statement
- [ ] Show BIMCO clause references

**Priority:** 🟡 **HIGH** — needed for contract negotiations  
**Timeline:** Phase 1 (after pilot feedback)

---

### **Issue: FuelEU Pooling = Penalty Oversimplification**

**Owner's Reality:**
- Statutory penalty: €2,400/t VLSFO-equivalent deficit (worst case)
- Real market: bio-bunkered vessels trade compliance at €500–€1,200/t
- Showing flat €2,400 penalty is "too simplistic"

**Example:**
A 40,000 DWT bulk carrier with €148k FuelEU deficit:
- Statutory: 148,000 / 1.17 = 126.5 t deficit × €2,400 = **€303.6k penalty**
- Realistic pooling: same deficit purchased at €800/t = **€101.2k cost**
- Current CarbonKeel: shows €148k (neither number is useful)

**Fix Required:**
- [ ] Display two FuelEU scenarios:
  - **Statutory (worst-case):** assumes no pooling, full penalty
  - **Market (realistic):** estimated pooling cost at €500/€800/€1,200/t (toggle)
- [ ] Show: "Your realistic cost if you pool: €101k (vs €303k if you take the penalty)"

**Priority:** 🟡 **HIGH** — owners need range, not point estimate  
**Timeline:** Phase 1

---

### **Issue: Rigid Speed-Cube Law Assumption**

**Owner's Reality:**
- Textbook: P ∝ V³ (power scales with speed cubed)
- Reality: modern eco-ships often 2.6–3.5 exponent
- **Auxiliary loads ignored:** hotel loads, reefers, boilers, cargo heating

**Example:**
A 50,000 DWT bulk carrier:
- Textbook P ∝ V³ at 13.5 knots = 40 t/day HFO + 5 t/day MDO auxiliary
- Real ship with EPL + reefer = 38 t/day HFO + 12 t/day MDO auxiliary
- Current CarbonKeel assumes all 45 t = 40 + 5 (wrong auxiliary split)
- Error: ~+15% on propulsion fuel, -60% on auxiliary

**Fix Required:**
- [ ] Split input: "Main Engine fuel" vs. "Auxiliary + Boiler" (t/day)
- [ ] Allow exponent override (default 3.0, range 2.6–3.5)
- [ ] For speed scenarios, apply exponent only to main engine
- [ ] Keep auxiliary load constant (day-rate base)

**Priority:** 🟡 **MEDIUM** — affects accuracy of what-if scenarios  
**Timeline:** Phase 1 UAT

---

## 3. UI/WORKFLOW GAPS

### **Issue: Fixed Static EUA Price**

**Owner's Pain:**
EUA price fluctuates €55–€85+. Hardcoded rate = outdated budget.

**Fix Required:**
- [ ] Editable EUA Price Slider (default €70, range €50–€100)
- [ ] Show sensitivity: "At €60/t: €450k bill. At €80/t: €600k."
- [ ] Optional: live ICE Futures price feed

**Priority:** 🟡 **MEDIUM** — easy win, high perceived value  
**Timeline:** Phase 1

---

### **Issue: No PDF / Excel Export**

**Owner's Pain:**
Cannot take results into board meetings, bank refinancing, chartering negotiations.

**Fix Required:**
- [ ] "Download Verifier-Ready PDF" button
- [ ] Includes: vessel name, IMO, year, all calculations, regulatory references, footnotes
- [ ] Optional CSV for fleet analysis

**Priority:** 🟡 **HIGH** — essential for enterprise workflow  
**Timeline:** Phase 1

---

### **Issue: Disjointed Vessel Lookup**

**Owner's Pain:**
Separate modules for "Ship Bill", "EEXI Check", "CII Calculator" = fragmented UX.

**Current State:**
- Search IMO → see EU ETS/FuelEU bill
- Click "CII" → separate form
- Click "EEXI" → another form

**Fix Required:**
- [ ] Single Unified Dashboard: IMO → populate all four engines simultaneously
- [ ] Tabs: ETS | FuelEU | CII | EEXI (all from one search)
- [ ] No re-entry needed

**Priority:** 🟡 **MEDIUM** — improves UX, reduces friction  
**Timeline:** Phase 1

---

### **Issue: G5 Correction Factors (MEPC.355)**

**Owner's Pain:**
Ice navigation, cargo heating, STS transfers buried in dropdown with no guidance.
Owner doesn't know which ones qualify.

**Fix Required:**
- [ ] Step-by-step checklist for G5 deductions
- [ ] **Clear pass/fail thresholds** (e.g., "Ice: applies if >50 days in ice zones")
- [ ] Links to MEPC.355 refs
- [ ] Auto-calculate G5 impact on CII rating

**Priority:** 🟢 **LOW** — only affects subset of ships (ice-class, reefers)  
**Timeline:** Phase 2

---

## PRIORITY ROADMAP FOR CUSTOMER ACQUISITION

### **Phase 0.5 (This Week) — Fix Trust Issues**
1. ✅ Landing page with hero search
2. 🔴 **Add corporate identity section to footer** (1 hr)
3. 🔴 **Fix Privacy Policy & NDA pages** (2 hrs)
4. 🔴 **Add liability disclaimer on calculator** (1 hr)
5. 🟡 **Implement "Request Demo Key" flow with 2-hour auto-issue** (4 hrs)

**Rationale:** Cannot pitch to prospects without trust signals.

---

### **Phase 1 (Weeks 1-2) — Fix Critical Data Gaps**
1. 🔴 **Voyage-type splitting (50%/100% ETS scope)**
2. 🟡 **FuelEU pooling range (statutory vs. market cost)**
3. 🟡 **EUA price slider**
4. 🟡 **PDF export**

**Rationale:** Without voyage splitting, numbers are wrong for ~40% of the fleet.

---

### **Phase 2 (Month 2) — Enterprise Features**
1. 🟡 Charter party allocation (BIMCO)
2. 🟡 Unified dashboard (all four engines from one search)
3. 🟡 Auxiliary load split + exponent override
4. 🟢 G5 correction checklist

---

## QUICK WINS (This Week)

| Fix | Effort | Impact | Owner's Reaction |
|-----|--------|--------|-------------------|
| **Corporate identity in footer** | 30 min | 🟢 High | "OK, there's a real team here" |
| **Fix privacy page** | 1 hr | 🟢 High | "Safe to enter fleet data" |
| **"Request Key" button on landing** | 2 hrs | 🟢 High | "I can try without email friction" |
| **Voyage split input on calculator** | 4 hrs | 🔴 Critical | "Now the numbers match reality" |
| **FuelEU pooling range** | 2 hrs | 🟡 Medium | "This is useful for budgeting" |

---

## SHIPOWNER'S VERDICT (Current vs. Future)

**Now:** "Promising sanity-check tool; cannot rely for contracts/finance."

**After Phase 0.5:** "OK for rough estimates; need voyage split before I trust it."

**After Phase 1:** "Can use for budget planning; still not for chartering disputes."

**After Phase 2:** "Can use for commercial negotiations; accounting-ready."

---

## NEXT STEPS

1. **This week:** Add corporate identity, fix privacy, voyage split input
2. **Next week:** Get 3-5 shipowner pilots on latest version
3. **Feedback loop:** Record which gaps hurt most in real usage
4. **Adjust priorities:** Move Phase 2 items forward if pilots demand them

