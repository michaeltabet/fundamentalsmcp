---
name: comps-analysis
description: Adjustment-first comparable-companies analysis and multi-year time-series analysis of SEC filers, built on the edgar MCP. Use when the user asks to "comp" companies, compare fundamentals across peers, analyze a company over time, build an adjusted-earnings bridge, or asks how a company's reported numbers differ from its economic reality. Every number must carry provenance (accession + XBRL tag).
---

# Comps & time-series analysis (adjustment-first)

You are running a fundamental analyst workflow on top of the `edgar` MCP
server. Two modes: **COMPS** (cross-sectional, N companies, one period) and
**TIME-SERIES** (one company, many periods). Both share the same iron rules.

## Iron rules (never break these)

1. **Adjustments are the product.** A comps table of as-reported numbers is
   surface-level and forbidden as a final answer. Every table shows
   REPORTED and ADJUSTED side by side, and the adjustment ledger that
   bridges them is part of the deliverable.
2. **Provenance on every number.** Each figure traces to an accession
   number + XBRL concept. Footnote format: `[acc 0000320193-25-000079,
   us-gaap:GrossProfit]`. If you computed it, show the formula.
3. **EDGAR has no market prices.** Never invent multiples. This is an
   *operating* comps framework (growth, margins, quality, balance sheet).
   If the user wants EV/EBITDA or P/E, ask for prices or a price source;
   share counts and net debt come from filings, so multiples are one
   price away.
4. **Verify before you compare.** Key aggregates get an
   `explain_number` arithmetic check (`ties_out: true`) before use.
   Never compare a dimensioned (segment) fact to a consolidated one.
5. **Data-first output.** Tables, then a short "what the adjustments
   change" section. No narrative padding.

## Mode 1 — COMPS

### Step 1: peer set (justify it)
- `find_company(target)` → note SIC code and description.
- Candidate pool: `compare_peers("us-gaap:Revenues", "CY<latest>")`
  filtered to similar scale, plus any peers the user names, plus known
  business-model peers the SIC misses (SIC is crude — say when you
  override it and why).
- 4–8 peers. List each with CIK, SIC, fiscal year end. **Flag fiscal-year
  misalignment** (e.g. AAPL Sep vs MSFT Jun): comps are "latest fiscal
  year, NOT calendarized" unless you build LTM from 10-Qs.

### Step 2: pull the raw layer (per company)
For each company's latest 10-K accession:
- `financial_statements(acc, "income")`, `("balance")`, `("cashflow")`
- `analyst_flags(acc)` ← the adjustment engine
- `compare_companies(a, b)` for pairwise sanity checks of your numbers.

### Step 3: apply the adjustment policy
Build ADJUSTED EBIT per company from reported operating income:

| adjustment | direction | when |
|---|---|---|
| stock-based compensation | none — KEEP it as an expense | always; it is a real recurring cost. Instead, REVERSE it out of any company-favored "adjusted" figure you quote |
| restructuring | add back ONLY if non-recurring | `recurring: false` in analyst_flags; if it appears ≥2 of 3 periods, it stays as a cost |
| impairments (goodwill/intangible/asset) | add back to run-rate EBIT | but report it in the capital-allocation note |
| one-time gains (asset/business sales, debt extinguishment, litigation) | REMOVE gains, add back losses | only genuinely one-time; check placement = "above the tax line" |
| amortization of acquired intangibles | add back ONLY for serial-acquirer comparability | and say you did; never silently |
| capitalized costs (software, interest) | no EBIT change | flag growth vs revenue growth as an earnings-quality note |

Tax-effect any pre-tax adjustment when bridging to adjusted net income /
EPS: use the company's own effective tax rate from
`analyst_flags.diagnostics.effective_tax_rate` unless it is distorted
(<12% or >30%) — then use 21% and say so.

### Step 4: the comps table
One row per company. Columns (all from tagged facts):

- Revenue, revenue growth %, gross margin %
- EBIT margin % (reported) | EBIT margin % (adjusted) | delta
- SBC % of revenue, SBC % of pre-tax income
- Cash conversion (CFO/NI), accruals % of revenue
- ETR % (+ swing flag), diluted share count change %
- EPS growth decomposed: earnings pts vs buyback pts
- Net debt = debt tags − cash tags (from balance sheet), and
  net debt / adjusted EBIT

Then: **the adjustment ledger** — every item you adjusted, per company:
category, tag, amount, % of pre-tax, recurring?, placement, accession.

### Step 5: findings
3–6 bullets, only things the adjustments *change*: "B's margin advantage
disappears adjusted", "A's EPS growth is 40% buyback", "C's
'restructuring' has run 5 straight years".

## Mode 2 — TIME-SERIES

### Step 1: spine
- `concept_timeseries` for each core concept (revenue, operating income,
  net income, CFO, diluted shares, SBC via
  `us-gaap:ShareBasedCompensation`) — this gives EVERY year the company
  ever reported, with accession provenance, no re-parsing. Default 8–10
  years or what the user asks.
- `statement_history(company, "income", n_filings=4–5)` for the aligned
  statement view (concepts matched across label changes).

### Step 2: adjustments per year
Run `analyst_flags` on each of the last 4–5 10-K accessions (older years'
one-timers are visible inside each filing's 3 comparative periods, so
~5 filings covers ~7 years). Build the per-year adjustment ledger.

### Step 3: the time-series table
Rows = years. Columns:
- Revenue, growth %
- EBIT reported | EBIT adjusted | margin both ways
- SBC % of revenue **(trend — SBC creep is a headline finding)**
- Cash conversion, accruals %
- ETR (flag one-time tax years)
- Diluted shares (cumulative buyback effect), EPS reported vs adjusted
- Impairments/restructuring by year (the "one-time items every year" test)

### Step 4: findings
What the adjusted series shows that the reported one hides: margin trend
divergence, SBC creep, earnings driven by tax/buybacks, recurring
"one-timers", receivables outrunning revenue in specific years.

## Pitfalls (check every run)

- **Near-zero denominators**: % of pre-tax explodes when pre-tax ≈ 0
  (e.g. Intel) — quote absolute $ alongside %.
- **IFRS filers (20-F)** tag under `ifrs-full`, so the us-gaap watchlist
  in analyst_flags misses them — fall back to `search_facts` +
  `explain_number` manually and say coverage is partial.
- **Banks/insurers** have different income structure (no
  OperatingIncomeLoss) — margins and EBIT adjustments don't apply; use
  pre-tax pre-provision framing and say so.
- **Revenue tag varies**: try RevenueFromContractWithCustomerExcludingAssessedTax,
  then Revenues, then SalesRevenueNet.
- **Non-GAAP reconciliation tables live in EX-99 press releases**, not
  XBRL — for the company's OWN adjusted-EPS bridge, `filing_contents` on
  the earnings 8-K → `read_document` the EX-99.1, and compare THEIR
  add-backs to yours. Divergence is a finding.
- Fiscal year ends differ across peers — always state the period each
  column covers.

## Deliverable

Markdown in-chat; if >2 companies or >5 years, ALSO write a CSV per table
plus `adjustment_ledger.csv` to the working directory. End with the
provenance appendix (accession list). If asked to re-run later, the CSVs +
accessions make it exactly reproducible.
