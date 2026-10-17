# Launch kit — domain, hosting, emails, contacts

Everything needed to put the site live and start the outreach in the same week.
Total cost: **~$10.44 for the first year. Nothing else.**

---

## 1. Cheapest place to put it (researched 2 Oct 2026)

### Domain — register at Cloudflare

| Registrar | .com/yr | Notes |
|---|---|---|
| **Cloudflare Registrar** | **~$10.44** | At-cost, no markup ever, free WHOIS privacy, free DNS + CDN + SSL. No upsells, no renewal shock. |
| Spaceship | ~$9.98 renewal | Marginally cheaper; you then pay for DNS/CDN elsewhere. |
| Porkbun | ~$10.37 | Good, free WHOIS privacy. |
| Namecheap / GoDaddy | $17–20 renewal | Cheap first year, expensive after. Avoid. |

**Recommendation: Cloudflare.** The $0.46/yr you'd save at Spaceship is not
worth splitting DNS, CDN and SSL across two providers. Cloudflare bundles all
of it free, and at-cost pricing means no renewal surprise in year two.

> Cloudflare requires you to add the domain to a (free) Cloudflare account
> first. Buy → it lands in your dashboard with DNS already managed.

### Hosting — two pieces, both free

Your app is small: the entire 16,673-ship register occupies **~14 MB resident,
22 MB peak** — comfortably inside any free instance.

| Piece | Where | Cost | Why |
|---|---|---|---|
| **Landing page** (`site/index.html`) | **Cloudflare Pages** | free | Static, global CDN, instant, no cold start. This is what a prospect clicks from your email. |
| **The app** (FastAPI) | **Render free tier** | free | 512 MB RAM, 750 instance-hours/month. Only real permanent free tier left — Fly.io and Railway both ended theirs. |

**The one catch:** Render's free tier sleeps after 15 minutes idle and takes
~50 seconds to wake. That is fine for a prospect browsing, and **not** fine
mid-demo. So:

- For **live demos**, run locally (`uvicorn api.main:app`) — instant, and you
  control it.
- For the **public link**, accept the cold start, or hit `/healthz` every 10
  minutes from a free cron (cron-job.org) — 744 h/month fits inside the 750 h
  allowance, just.

### DNS once the domain is live

| Record | Name | Points to |
|---|---|---|
| CNAME | `@` (or `www`) | your Cloudflare Pages project |
| CNAME | `app` | your Render service hostname |

So `carbonkeel.com` → landing page, `app.carbonkeel.com` → the tool. The
landing page already links to `app.carbonkeel.com`.

### Email on the domain

Cloudflare **Email Routing** is free: `enquiry@carbonkeel.com` forwards to your
Gmail. To *send* as that address, add it in Gmail under "Send mail as" with a
free SMTP relay, or pay ~$6/mo for Google Workspace once replies justify it.
Start with forwarding — it costs nothing and looks identical to a recipient.

### Deploy steps (about 30 minutes, once)

1. `git init && git add . && git commit -m "CarbonKeel"` and push to a **private**
   GitHub repo.
2. Render → New → Blueprint → pick the repo. It reads `render.yaml` and builds.
3. Cloudflare Pages → Create project → same repo → build output directory `site`.
4. Add the two CNAMEs above. SSL is automatic.
5. Check `https://app.carbonkeel.com/healthz` returns `{"ok": true, ...}`.

**Before step 1**, make sure `data/access_keys.txt` is in `.gitignore` — that
file is your CII calculator key.

---

## 2. The cold emails

Three versions, because the two sides of the pooling market need opposite
openings. Send from `enquiry@carbonkeel.com`, sign with your own name.

### A · Deficit holder — the common case

> **Subject:** [Company] — your 2026 FuelEU position, before the pooling window
>
> Hi [Name],
>
> We pulled [Company]'s [N] ships from the public EU-MRV register and ran the
> FuelEU numbers on them. On 2025 verified data the fleet is carrying roughly
> **[X] tonnes of compliance deficit — about €[Y] of penalty exposure** at the
> Article 23 rate of €2,400 per tonne of VLSFO-equivalent.
>
> There is a cheaper way out than paying it, and it has a hard date on it. Under
> Article 21 a deficit ship can pool with a surplus ship instead of paying — but
> the pool has to be registered by **30 April 2027**. After that, the penalty is
> the only option left for the 2026 year.
>
> A one-page breakdown of every ship is attached. It is built entirely from the
> figures your own verifier filed with EMSA, so please treat it as an estimate —
> we label it as one. We check ourselves against your verifier’s own ETS-scope
> number: across the whole 2025 report we match it exactly for about two ships in
> three, and to within 2% for about three in four.
>
> What we do, briefly: EU ETS and UK ETS cost, FuelEU balance and penalty, CII
> rating and its trajectory to 2030, EEXI, and IMO Net-Zero exposure — all in
> euros rather than letter grades, with an audit worksheet your verifier can
> check. We can also help you work out whether pooling is worth doing.
>
> If the attached is roughly right, making it exact takes one noon-report export.
> Worth twenty minutes before the window closes?
>
> [Your name]
> CarbonKeel · carbonkeel.com

### B · Surplus holder — **send these first**

Surplus is scarce. Across every LNG operator in the EU trade we can see only
about **5,200 tCO₂e of surplus**, while a *single* container manager is short
20,800 t. These owners have pricing power they have almost certainly not priced.

> **Subject:** [Company] — your LNG fleet is holding a sellable FuelEU surplus
>
> Hi [Name],
>
> Most owners we talk to are short on FuelEU. [Company] is not — and that is
> worth money to you.
>
> Running your [N] [LNG carriers/ships] through the FuelEU calculation on public
> 2025 data, the fleet comes out **in surplus**. Under Article 21 that surplus
> can be pooled with ships that are in deficit, and they will pay for it: their
> alternative is the €2,400 per tonne penalty, so a pooled tonne is worth a
> negotiated share of that rather than nothing.
>
> Today most surplus simply expires unused, because the owners holding it do not
> know it is an asset and have no counterparty. We are building exactly that
> matching service, and demand is running far ahead of supply — we currently see
> several multiples more deficit than surplus in the European trade.
>
> We are not asking for a commitment. We would like to confirm your position with
> real bunker data rather than our estimate, and have a conversation about what
> your surplus should be worth before the 30 April 2027 registration deadline.
>
> Fleet breakdown attached. Twenty minutes?
>
> [Your name]
> CarbonKeel · carbonkeel.com

### C · Follow-up (day 4–5, if no reply)

> **Subject:** Re: [original subject]
>
> Hi [Name] — short follow-up in case this got buried.
>
> The one number from the attachment: **€[X]** of FuelEU exposure on [Company]'s
> fleet for a single compliance year, and a pooling route that closes 30 April.
>
> If this sits with someone else — technical, commercial, or whoever owns the
> ETS budget — I would be grateful for the name. And if it is simply not a
> priority, tell me and I will stop.
>
> [Your name]

### LinkedIn version (shorter, when email bounces)

> Hi [Name] — we ran [Company]'s [N] ships through the FuelEU calculation using
> EMSA's public verified data. The fleet looks [X] tonnes [short / in surplus],
> which is roughly €[Y] [of penalty exposure / of sellable surplus] for one
> compliance year. Pooling has to be registered by 30 April 2027. Happy to send
> the per-ship breakdown — worth a look?

### Rules
- **Never send a report you have not opened.** They are estimates; you are the
  last check.
- One personalised sentence minimum. The numbers already personalise it — do not
  also paste a generic paragraph about decarbonisation.
- No follow-up before day 4, and never more than two.
- If they say no, log `--log dead` and move on. A clean no is worth more than a
  maybe you keep re-reading.

---

## 3. Who to contact

You already have the list: **`outreach/targets_2025.csv`** — 311 companies
inside the ICP (8–60 ships, majority container/bulk/tanker), ranked by verified
ETS exposure, each row carrying fleet size, CO₂, estimated allowance cost and
sample IMO numbers.

`python scripts/daily.py --targets 10` pulls the next ten and computes each
one's live FuelEU and pooling position.

### Priority order

1. **Surplus holders first** (`--surplus`): Knutsen OAS, Nakilat, MOL Global
   Ship Management, Maran Gas and the other LNG operators. Scarce side, email B.
2. **Mid-list independents**: Technomar, Peter Döhle, Tsakos, Anglo-Eastern
   Germany and similar — 20–60 ships, real exposure, a reachable decision maker.
3. **Skip the mega-carrier subsidiaries** (CMA, Evergreen, MSC, COSCO...). The
   console already filters them out: huge exposure, but procurement will eat six
   months and you have an hour a day.

### The person, by title — in order of who actually replies

| Role | Why them |
|---|---|
| Fleet Performance / Energy Efficiency Manager | Owns the CII problem daily |
| Technical Director / Superintendent | Owns the fix and the budget |
| Commercial / Chartering Manager | Owns who *pays* under the charter — often the fastest to care about euros |
| DPA / HSQE Manager | Owns the audit trail and the SEEMP |
| Sustainability / ESG Manager | Owns the reporting, but often has no budget |

### Finding them, free
LinkedIn search: company name + one of the titles above. Take the name and role
into the pipeline (`--log target --company "X" --contact "Name, Role"`). For the
address, the company website's contact page gives you the domain and usually the
house pattern — confirm rather than guess, and if you cannot confirm, send the
LinkedIn message instead. **Do not invent email addresses**: a bounce costs you
the domain's sending reputation, which you cannot buy back for $10.

---

## 4. Running site build and outreach in parallel

The rule that keeps both moving: **outreach every weekday, building only on
Friday.** The product is already far ahead of the market work; another feature
will not get you a customer, and a sent email might.

| | |
|---|---|
| Mon | `--targets 10`, find contacts |
| Tue | Send 5 (surplus holders first) |
| Wed | Send 5 |
| Thu | Follow-ups, calls |
| **Fri** | **Build** — deploy, or whatever a prospect asked for this week |

Week 1's Friday build is the deployment above. After that, Fridays belong to
whatever the week's conversations demanded — which is a far better roadmap than
anything either of us would guess in advance.
