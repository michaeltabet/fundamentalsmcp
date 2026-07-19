---
name: company-dossier
description: Full primary-source company workup on a single filer using the fundamentals MCP — the business model, the risks, the multi-year financials + ratios, market multiples, and insider activity, assembled into one analyst-grade dossier. Use when the user says "work up", "full dossier", "tell me everything about", "analyze this company", "is this a good business", or wants a complete tear-sheet. Every claim traces to a filing. Never opinions about what other investors are doing.
---

# Company dossier (primary-source workup)

You are producing a complete, analyst-grade profile of ONE company from its
own filings, using the `fundamentals` MCP. The whole point is that this is grounded
in primary sources — the company's 10-K, its XBRL facts, its insider forms —
not vibes, not headlines, not what "the market thinks".

## Hard rules — read before you write a word

1. **Primary source or it doesn't go in.** Every number cites `[acc …,
   concept]`. Every qualitative claim about the business cites the section it
   came from (`[10-K Item 1]`, `[10-K Item 1A]`). If you can't cite it, cut it.
2. **Never assert what other investors, banks, or analysts are doing.** No
   "JPMorgan is buying this", no "the Street expects", no "analysts rate it
   a buy", no imagined price targets. You have no such data and inventing it
   is an instant credibility failure. The ONLY third-party ownership you may
   state is what you actually pulled: `insider_transactions` (Forms 3/4/5) and
   `fund_holdings` (13F) — and you name the exact source.
3. **Analyze the company, not the ticker's mood.** Business quality, unit
   economics, balance-sheet strength, cash generation, risk. Price/multiples
   are context, never the thesis.
4. **No invented figures.** If the dossier tool returns null for a line, say
   "not separately tagged", don't estimate it into existence.
5. **Numbers get a sanity pass.** DuPont must tie (`net_margin ×
   asset_turnover × equity_multiplier ≈ ROE`). If a ratio looks absurd, trace
   it with `explain_number` before reporting it — don't launder a parsing
   error into a "finding".

## Workflow

### 1. Identity & spine
- `find_company(target)` → CIK, SIC, fiscal year end.
- `company_dossier(target, years=5, ticker=<market symbol>)` → the full
  three-statement spine, ratio suite, growth, provenance, and market
  multiples in one call. This is the quantitative backbone. Read the
  `provenance` block so you can cite each line.

### 2. Business model (what the company actually does)
- `read_section(acc, "Item 1")` (Business) — summarize: what they sell, to
  whom, how they make money, segments, customer/supplier concentration,
  competitive position **as the company describes it**. Cite `[10-K Item 1]`.
- Tie the narrative to the numbers: segment revenue via `search_facts(acc,
  "<segment>")` or the dossier's dimensioned facts. If they say "services is
  our growth engine", show the services line growing.

### 3. Risks (real ones, ranked)
- `read_section(acc, "Item 1A")` (Risk Factors) — do NOT dump the list.
  Extract the 4–6 that are specific and material (concentration, leverage
  maturities, litigation, regulatory, key-supplier/customer), skip boilerplate
  ("general economic conditions"). Where a risk is quantifiable, quantify it
  from the facts (e.g. debt maturity wall, customer concentration %).

### 4. Quality of earnings & insiders
- `analyst_flags(acc)` / `forensic_scan(acc)` — surface the adjustments; if
  the user wants the interactive bridge, hand off to `forensic-deep-dive`.
- `insider_transactions(target)` — who bought/sold, role, code, size. Report
  the pattern factually (e.g. "CEO sold 100k under a 10b5-1 plan on 2025-…"),
  never a motive you can't source.

### 4b. Comps & YoY (put it in context)
- **YoY** is already in the dossier (`growth` block: revenue, net income, EPS)
  — lead the financials with the trend, not a single snapshot.
- **Comps**: a company in isolation means little. Build a 3–6 name peer set
  (`compare_peers("us-gaap:Revenues", "CY<year>")` filtered to similar scale +
  known business-model peers) and run `compare_companies(a, b)` for the
  common-sized quality scan, or hand off to the `comps-analysis` skill for a
  full adjusted peer table. Same iron rule: adjusted, side-by-side, sourced —
  and still no "what other investors think", only the filed fundamentals.

### 5. The dossier (deliverable)
Assemble in this order — data first, prose tight:
1. **Snapshot** — name, ticker, SIC/industry, FY end, market cap & multiples
   (labelled as market data, dated).
2. **Business model** — 4–6 sentences, cited to Item 1, tied to segment numbers.
3. **Financials** — the multi-year table (revenue, gross/op/net margin, EPS,
   FCF, ROE with DuPont, leverage, liquidity), each line traceable.
4. **Quality of earnings** — the adjustments that matter and their direction.
5. **Risks** — the ranked, quantified few.
6. **Insider/ownership** — only what you pulled, sourced.
7. **Bottom line** — 3–5 sentences on business quality and balance-sheet
   resilience, grounded in the above. NOT a buy/sell call, NOT a price target.

## Pitfalls
- **Warm first.** `company_dossier` warms the store itself, but if you query
  facts directly, check `fact_store_status`.
- **Company-name string.** The store keys facts on the filing's company name
  (e.g. "Apple Inc."); `find_company` gives you the canonical string.
- **Multiples need a real ticker.** Pass the correct market symbol (global OK:
  `D05.SI`, `.L`, `.HK`). EDGAR has no prices — multiples come from market data.
- **Segment vs consolidated.** Never compare a dimensioned (segment) fact to a
  consolidated total.
