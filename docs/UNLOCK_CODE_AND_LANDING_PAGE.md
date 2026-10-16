# CarbonKeel: Landing Page & Access Control

---

## **1. LANDING PAGE (Entry Point)**

### **What Users See:**

When someone visits **https://carbonkeel.com**, they land on:

**File:** `site/index.html`

**Current Flow:**
1. **Hero Section** - "What carbon costs your ships" with canvas ocean animation
2. **Search Box** - Free lookup by ship IMO/name (e.g., 9464663)
3. **Example Ships** - Quick links to PETER OLDENDORFF, AIDADIVA, etc.
4. **Regulatory Overview** - Brief explanation of EU ETS, FuelEU, UK ETS, CII, NZF
5. **Methodology** - How we rebuild and verify figures
6. **Night Scene** - Lighthouse animation with stars

**Navigation:** Links to:
- `/` (home)
- `/method` (methodology)
- `/calendar` (compliance calendar)
- `/contact` (contact form)

### **Customization Options:**

You can change ANY of this anytime:
- Hero section text ✅
- Example ships ✅
- Feature descriptions ✅
- Call-to-action buttons ✅
- Colors, fonts, animations ✅

**How:**
Edit `site/index.html` directly, commit to GitHub, and Fly.io auto-deploys within 2-3 minutes.

---

## **2. CII UNLOCK CODE (Access Gating)**

### **What It Is:**

A **shared-secret key system** that locks the CII calculator behind a code.

**File:** `src/ghgcore/access.py`

**Location in Code:**
```
data/access_keys.txt  ← List of valid keys
```

### **Why It Exists:**

According to the code comments:

> *"This is a shared-secret gate, not an authentication system. It exists so the CII calculator and other owner-data tools are not open to the anonymous internet during the pilot phase: you hand a key to a design partner, they paste it once, it is remembered in their browser."*

**Reason:** During pilot/MVP phase, you want to control who can use the CII calculator because:
1. It requires DWT (deadweight tonnage) - owner-specific data
2. You want early feedback from controlled partners, not random internet users
3. It's a differentiator for paid/premium features
4. Prevents abuse during scaling

### **How It Works:**

1. **User enters key** on the website → stored in browser
2. **Key validated** against `data/access_keys.txt`
3. **Access granted** to `/cii` pages and calculations
4. **Revoking:** Delete the key from the file

### **Can You Change It? YES, ABSOLUTELY ✅**

You can modify this **anytime, anywhere** based on your business requirements:

---

## **3. OPTIONS: KEEP OR REMOVE THE UNLOCK CODE**

### **Option A: Keep Lock (Current)**

**When:** During early customer acquisition (design partners, beta users)

**How to manage:**
```bash
# Issue a new key to a partner:
python3 -c "from ghgcore.access import issue; print(issue('Partner Name'))"

# Output: ck-a1b2c3d4e5f6g7h8  ← Give this to the partner

# Revoke: Delete the line from data/access_keys.txt
```

**Edit file:** `data/access_keys.txt`
```
ck-founder01  # Your founder key
ck-partner01  # Design partner 1
ck-partner02  # Design partner 2
```

**Pros:**
- Control who accesses premium feature
- Track which partners have access
- Easy to revoke per partner
- Can monetize later ("unlock for €X/month")

---

### **Option B: Remove Lock Entirely**

**When:** Public launch, free tier launch, or just to get momentum

**Steps to remove:**

1. **Delete the gating logic** from `api/main.py`:
   ```python
   # Remove this check from CII endpoint:
   if not access.is_valid(key):
       raise HTTPException(401, "Invalid access key")
   ```

2. **Remove the access module:**
   ```bash
   rm src/ghgcore/access.py
   rm data/access_keys.txt
   ```

3. **Make CII public:**
   Edit `api/static/index.html` to show CII tab without key requirement

4. **Deploy:**
   ```bash
   git add .
   git commit -m "Remove unlock code gate — CII calculator now public"
   git push origin main
   ```

**Pros:**
- Anyone can use CII instantly
- No friction on landing
- Higher conversion (no gate to lose users)
- Simple

---

## **4. WHAT TO DO RIGHT NOW**

### **For Customer Acquisition Phase (Recommended):**

**Keep the unlock code BUT:**

1. **Make it easy to request a key** on the landing page
   - Add: "Want to try? Request a free key" button
   - Links to `/contact` with auto-fill

2. **Issue keys to prospects:**
   ```bash
   python3 -c "from ghgcore.access import issue; print(issue('Prospect Name'))"
   ```

3. **Revoke when relationship ends:**
   Delete line from `data/access_keys.txt`

### **Copy for Landing Page:**

```
"CII Calculator — By Invitation

The CII calculator requires your vessel's specific data (DWT, type, performance).
Request a free key below — responses within 24 hours.

[Request Key Button]
```

---

## **5. TIMELINE TO REMOVE LOCK**

**Phase 1 (Now):** Keep lock, issue keys to design partners (2-4 partners)
**Phase 2 (Month 2):** Remove lock when you have 5-10 paying customers
**Phase 3 (Month 3+):** Open to all, offer premium features

---

## **6. TECHNICAL CHANGES NEEDED**

To change the landing page or unlock system:

### **Landing Page Changes:**
```bash
# Edit directly:
nano site/index.html

# Or via code editor:
# File → site/index.html

# Redeploy:
git add site/index.html
git commit -m "Update landing page copy"
git push origin main
# Live in 2-3 mins
```

### **Unlock Code Changes:**
```bash
# Issue new key:
python3 -c "from ghgcore.access import issue; print(issue('Customer Name'))"

# Revoke key:
# Edit data/access_keys.txt, delete the line
# Changes apply immediately

# Remove lock entirely:
# Follow Option B above
```

---

## **7. YOUR BUSINESS DECISION**

| Factor | Keep Lock | Remove |
|--------|-----------|--------|
| **Customer Control** | High (qualify leads) | Low (open access) |
| **Monetization Path** | Easier (premium feature) | Harder (free) |
| **Conversion** | Lower (friction) | Higher (no gate) |
| **Support Load** | Lower (fewer users) | Higher (everyone) |
| **Phase** | MVP/Pilot | Public/Launch |

---

## **Summary**

✅ **You can change EVERYTHING anytime:**
- Landing page copy: Edit `site/index.html` → redeploy (2 mins)
- Unlock codes: Edit `data/access_keys.txt` → immediate
- Remove lock entirely: Delete gating code → redeploy

**Recommendation for now:**
Keep the unlock code, issue keys to your first 5-10 prospects, use it to qualify leads and gather feedback before public launch.

**You have full control.** Make the business call that fits your go-to-market strategy.

