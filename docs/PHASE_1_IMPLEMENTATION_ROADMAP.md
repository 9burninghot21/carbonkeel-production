# Phase 1: Critical Features Implementation Roadmap

## Status: DEPLOYED ✅
- [x] Landing page (site/index.html) as home
- [x] Calculator at /app
- [x] Privacy policy (zero data transmission statement)
- [x] Corporate identity in footer
- [x] Trust signals added

**Live at:** https://carbonkeel.com/  
**Last updated:** 17 October 2026

---

## NEXT: Week 1 Critical Features (Top 3)

### **#1: Voyage-Type Splitting (50% vs 100% ETS Scope)**

**Why It's Critical:**
- Current CarbonKeel: assumes ALL fuel = 100% EU ETS scope
- Reality: 60% intra-EU (100%) + 40% extra-EU (50%) = real scope ~70%
- Owner seeing €200k cost but real is €140k = **distrust**

**Implementation (4-6 hours):**

#### A. UI Changes (api/static/index.html, after fuel inputs)
```html
<details class="whatif" style="margin-top:16px">
  <summary>Voyage split (EU ETS scope allocation)</summary>
  <p class="dim" style="font-size:12.5px;margin:8px 0">
    How is your fleet operating? Each percentage affects the EU ETS allowances you buy.
    Intra-EU = 100% scope. Inbound/Outbound to EU = 50% scope. Outside EU = 0% scope.
  </p>
  <div class="row">
    <div style="flex:1">
      <label>Intra-EU voyages (%)</label>
      <input id="scope_intra" type="number" min="0" max="100" value="100" step="5" placeholder="0-100">
    </div>
    <div style="flex:1">
      <label>Inbound/Outbound (%)</label>
      <input id="scope_inbound" type="number" min="0" max="100" value="0" step="5" placeholder="0-100">
    </div>
    <div style="flex:1">
      <label>Outside EU (%)</label>
      <input id="scope_outside" type="number" min="0" max="100" value="0" step="5" placeholder="0-100" disabled>
    </div>
  </div>
  <p class="dim" style="font-size:12px;margin:6px 0;text-align:right">Must add to 100%</p>
</details>
```

#### B. JavaScript Changes (in calculation logic)
**Current:** 
```javascript
const ets_scope_co2 = reported_co2 * 1.0  // assumes 100%
```

**New:**
```javascript
const intra_pct = parseFloat(document.getElementById('scope_intra').value || 100) / 100;
const inbound_pct = parseFloat(document.getElementById('scope_inbound').value || 0) / 100;
const outside_pct = parseFloat(document.getElementById('scope_outside').value || 0) / 100;

// Validate
if (Math.abs((intra_pct + inbound_pct + outside_pct) - 1.0) > 0.01) {
  throw new Error("Voyage percentages must add to 100%");
}

// Calculate weighted scope
const scope_factor = (intra_pct * 1.0) + (inbound_pct * 0.5) + (outside_pct * 0.0);
const ets_scope_co2 = reported_co2 * scope_factor;
```

#### C. Output Display (in results section)
Show breakdown:
```
ETS Scope Allocation:
  Intra-EU (100%): 60% × €200k = €120k (100% scope)
  Inbound/Outbound (50%): 40% × €200k = €80k (50% scope) = €40k cost
  Total EU ETS: €160k
```

**Testing:**
- Validate: 100/0/0 → same as current
- Validate: 0/100/0 → cost = current × 0.5
- Validate: 50/50/0 → cost = current × 0.75
- UI: Show validation error if percentages don't sum to 100

**Deployed:** Week 1 (3 days after this plan)

---

### **#2: EUA Price Slider (€50–€100)**

**Why It's Critical:**
- Current: hardcoded €70/t EUA price
- Reality: market fluctuates €55–€85+
- Owner: "Your estimates are already outdated"

**Implementation (2-3 hours):**

#### A. UI Changes (in CII results section header)
```html
<div class="card" style="background:#f0f8ff;border:1px solid #0a5aa0;margin-bottom:14px">
  <label style="display:block;font-weight:700;font-size:13px;color:#0a5aa0;margin-bottom:6px">
    EUA Price Assumption
  </label>
  <div style="display:flex;gap:12px;align-items:center">
    <input id="euaPrice" type="range" min="50" max="100" value="70" step="1" style="flex:1">
    <span style="font-weight:800;font-size:16px;color:#0a5aa0;min-width:50px">
      €<span id="euaPriceDisplay">70</span>/t
    </span>
  </div>
  <p style="font-size:12px;color:#586f8c;margin-top:6px">
    Adjust to see how EUA price changes your EU ETS cost.
    Current ICE Futures 1Y: ~€72/t (reference only).
  </p>
</div>
```

#### B. JavaScript Changes (recalculate on input)
```javascript
const euaPrice = parseFloat(document.getElementById('euaPrice').value);
document.getElementById('euaPriceDisplay').textContent = euaPrice;

// Recalculate costs
const ets_cost_eur = ets_allowances_due * euaPrice;

// Show sensitivity
const costAt60 = ets_allowances_due * 60;
const costAt80 = ets_allowances_due * 80;
// Display: "At €60/t: €XXXk. At €80/t: €XXXk."
```

#### C. Output Display
```
EU ETS Cost @ €70/t EUA: €363k
Sensitivity: 
  @ €60/t: €311k (−14%)
  @ €80/t: €414k (+14%)
```

**Testing:**
- Input €50 → cost = (current / 70) × 50
- Input €100 → cost = (current / 70) × 100
- Slider tracks live

**Deployed:** Week 1 (alongside voyage split)

---

### **#3: FuelEU Pooling Range (Statutory vs. Market)**

**Why It's Critical:**
- Current: shows flat €148k penalty
- Reality: owner can buy compliance from pool at €500–€1,200/t instead of statutory €2,400/t
- Owner seeing worst-case only → doesn't trust it for budgeting

**Implementation (2-3 hours):**

#### A. UI Changes (in FuelEU results section)
```html
<div class="card">
  <b>FuelEU Compliance Deficit Strategy</b>
  <p class="dim">Your deficit: 126.5 t VLSFO-equivalent. You have two choices:</p>
  
  <div style="margin-top:12px">
    <label style="display:block;font-weight:700;color:#ef4444;font-size:14px">
      Option 1: Statutory Penalty (Worst-Case)
    </label>
    <p style="font-size:13px;color:#0b2545;margin:6px 0">
      Take the full penalty. No pooling, no surplus purchase.
    </p>
    <p style="font-size:18px;font-weight:900;color:#ef4444;margin:4px 0">
      €303.6k penalty (126.5 t × €2,400/t)
    </p>
  </div>

  <div style="margin-top:16px;padding-top:16px;border-top:1px solid #ddd">
    <label style="display:block;font-weight:700;color:#0f7a52;font-size:14px">
      Option 2: Realistic Pooling (Market Cost)
    </label>
    <p style="font-size:13px;color:#0b2545;margin:6px 0">
      Buy compliance from a pool at a negotiated premium. Range: €500–€1,200/t
    </p>
    <div style="display:flex;gap:10px;margin:10px 0">
      <div style="flex:1">
        <label style="font-size:11px;color:#586f8c;text-transform:uppercase;font-weight:700">Conservative (€500/t)</label>
        <p style="font-size:18px;font-weight:900;color:#0f7a52">€63.3k</p>
      </div>
      <div style="flex:1">
        <label style="font-size:11px;color:#586f8c;text-transform:uppercase;font-weight:700">Mid-Market (€800/t)</label>
        <p style="font-size:18px;font-weight:900;color:#0f7a52">€101.2k</p>
      </div>
      <div style="flex:1">
        <label style="font-size:11px;color:#586f8c;text-transform:uppercase;font-weight:700">Premium (€1,200/t)</label>
        <p style="font-size:18px;font-weight:900;color:#0f7a52">€151.8k</p>
      </div>
    </div>
  </div>

  <p style="font-size:12px;color:#586f8c;margin-top:12px;border-top:1px solid #ddd;padding-top:12px">
    <strong>Budget for:</strong> €100–€150k (realistic range) instead of €300k (statutory worst-case).
    Pooling price depends on market demand and your vessel's compliance surplus/deficit profile.
  </p>
</div>
```

#### B. JavaScript Calculation
```javascript
// FuelEU deficit calculation
const deficit_tonnes = fueleu_deficit_tco2e / 1.17; // VLSFO-equivalent

// Statutory (worst-case)
const statutory_penalty = deficit_tonnes * 2400;

// Pooling range
const pooling_conservative = deficit_tonnes * 500;
const pooling_midmarket = deficit_tonnes * 800;
const pooling_premium = deficit_tonnes * 1200;

// Recommendation
let recommendation = "";
if (pooling_midmarket < statutory_penalty * 0.4) {
  recommendation = "Pooling is strongly recommended. Cost is ~⅓ of the statutory penalty.";
}
```

**Testing:**
- Calculate deficit correctly
- Verify: pooling costs are 20–50% of statutory
- Show: "You'd save €XXXX by pooling"

**Deployed:** Week 1 (within 2 hours of voyage split)

---

## Summary: What Ships Will See

### **Before (Currently Live)**
```
EU ETS Cost: €363k
FuelEU Penalty: €148k
Total: €511k
```

### **After Phase 1 (This Week)**
```
Voyage Allocation:
  Your profile: 70% EU-scope (you enter 60% intra-EU, 40% inbound)
  Adjusted ETS cost: €254k (not €363k)

EUA Price Assumption:
  Market: €70/t [you can adjust €50–€100]
  At €80/t: €290k | At €60/t: €218k

FuelEU Deficit Strategy:
  Statutory penalty: €303k (worst-case, if you take the hit)
  Realistic pooling: €101k @ €800/t (what you'll likely pay)

Revised Total:
  Conservative estimate: €355k (vs €511k before)
  Why it changed: better voyage profile + realistic pooling cost
```

---

## Acceptance Criteria

✅ **Voyage Split:**
- [ ] Input three voyage percentages
- [ ] Validation: error if not 100%
- [ ] ETS cost recalculates automatically
- [ ] Shows breakdown in results

✅ **EUA Price Slider:**
- [ ] Slider €50–€100
- [ ] Live recalculation
- [ ] Shows sensitivity (cost at €60/t, €80/t)
- [ ] Default €70

✅ **FuelEU Pooling Range:**
- [ ] Shows statutory penalty (€2,400/t worst-case)
- [ ] Shows pooling range (€500/€800/€1,200/t)
- [ ] Highlights recommended option
- [ ] Computes total revised bill

---

## Testing & Rollout

**Testing Environment (Dev Server):**
1. Load calculator at localhost:8000/app
2. Enter test vessel (PETER OLDENDORFF)
3. Adjust voyage split → ETS cost changes ✅
4. Adjust EUA price slider → all ETS figures change ✅
5. Check FuelEU pooling section shows all three scenarios ✅

**Deploy:**
- Commit to main
- `git push origin main`
- Fly.io auto-deploys (2-3 mins)
- Check live at https://carbonkeel.com/app

**Tell Prospects:**
"Updated our calculator with three critical features: voyage-scope allocation (50/100% ETS), live EUA pricing, and realistic pooling costs. Your numbers just got more accurate."

---

## Next: Phase 2 (Month 2)

After these three are live and tested:
- Charter party allocation (owner vs. charterer split by date)
- Auxiliary load separation (main engine vs. hotel load)
- PDF export with full calculation trail
- G5 correction checklist

