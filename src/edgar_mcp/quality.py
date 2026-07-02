"""Analyst adjustment flags: the quality-of-earnings layer.

Scans a filing's XBRL facts for the items a fundamental analyst would
flag (SBC, restructuring, impairments, one-time gains/losses, ...),
locates each in the calculation tree (does it hit operating income? is
it above the tax line and therefore in EPS?), sizes it against the
company's own benchmarks, checks recurrence across the periods in the
filing, and writes the implication in analyst terms.
"""

from __future__ import annotations

from .util import fmt_value, norm_concept

# ---------------------------------------------------------------- watchlist

WATCHLIST: dict[str, dict] = {
    "stock_based_compensation": {
        "concepts": [
            "us-gaap_ShareBasedCompensation",
            "us-gaap_AllocatedShareBasedCompensationExpense",
        ],
        "implication": (
            "SBC is a real, recurring, pre-tax expense that is already in GAAP"
            " EPS — any 'adjusted EPS' that adds it back overstates recurring"
            " earnings power. It is also non-cash, so it inflates operating"
            " cash flow relative to true economics, and it dilutes: check"
            " share count trend for the offsetting buyback spend."
        ),
    },
    "restructuring": {
        "concepts": [
            "us-gaap_RestructuringCharges",
            "us-gaap_RestructuringCostsAndAssetImpairmentCharges",
            "us-gaap_RestructuringAndRelatedCostIncurredCost",
            "us-gaap_SeveranceCosts1",
            "us-gaap_BusinessExitCosts1",
        ],
        "implication": (
            "Restructuring is the most abused add-back. If it recurs across"
            " periods it is an operating cost of running this business, not a"
            " one-off — excluding it every year systematically overstates"
            " margins."
        ),
    },
    "impairments": {
        "concepts": [
            "us-gaap_GoodwillImpairmentLoss",
            "us-gaap_ImpairmentOfIntangibleAssetsExcludingGoodwill",
            "us-gaap_ImpairmentOfIntangibleAssetsIndefinitelivedExcludingGoodwill",
            "us-gaap_ImpairmentOfIntangibleAssetsFinitelived",
            "us-gaap_AssetImpairmentCharges",
            "us-gaap_ImpairmentOfLongLivedAssetsHeldForUse",
            "us-gaap_TangibleAssetImpairmentCharges",
        ],
        "implication": (
            "An impairment is an admission that past capital allocation"
            " destroyed value (usually an overpriced acquisition). Non-cash"
            " NOW, but the cash left in the prior deal. Reasonable to exclude"
            " from run-rate earnings; unreasonable to ignore for management"
            " quality."
        ),
    },
    "one_time_gains_losses": {
        "concepts": [
            "us-gaap_GainLossOnSaleOfBusiness",
            "us-gaap_GainsLossesOnSalesOfBusinesses",
            "us-gaap_GainLossOnDispositionOfAssets",
            "us-gaap_GainLossOnDispositionOfAssets1",
            "us-gaap_GainsLossesOnExtinguishmentOfDebt",
            "us-gaap_GainLossOnInvestments",
            "us-gaap_UnrealizedGainLossOnInvestments",
            "us-gaap_LitigationSettlementExpense",
            "us-gaap_GainLossRelatedToLitigationSettlement",
            "us-gaap_InsuranceRecoveries",
            "us-gaap_BusinessCombinationAcquisitionRelatedCosts",
        ],
        "implication": (
            "Genuinely non-recurring items that sit ABOVE the tax line flow"
            " straight through pre-tax income into reported EPS — strip them"
            " (tax-effected) before comparing EPS across periods or"
            " companies. Gains flatter the period; losses make the base look"
            " artificially easy to beat."
        ),
    },
    "amortization_of_intangibles": {
        "concepts": [
            "us-gaap_AmortizationOfIntangibleAssets",
            "us-gaap_FiniteLivedIntangibleAssetsAmortizationExpense",
        ],
        "implication": (
            "Amortization of acquired intangibles is the standard 'adjusted"
            " EPS' add-back. Defensible only if you also charge the company"
            " for the acquisitions (capital deployed); a serial acquirer that"
            " adds this back reports margins as if its acquisitions were"
            " free."
        ),
    },
    "capitalized_costs": {
        "concepts": [
            "us-gaap_CapitalizedComputerSoftwareAdditions",
            "us-gaap_InterestCostsCapitalized",
            "us-gaap_CapitalizedContractCostAmortization",
        ],
        "implication": (
            "Costs capitalized to the balance sheet bypass the income"
            " statement today — rising capitalization can manufacture margin"
            " expansion. Compare growth here vs expensed R&D/opex."
        ),
    },
    "pension_and_other": {
        "concepts": [
            "us-gaap_NetPeriodicDefinedBenefitsExpenseReversalOfExpenseExcludingServiceCostComponent",
            "us-gaap_DefinedBenefitPlanNetPeriodicBenefitCost",
            "us-gaap_OtherNonoperatingIncomeExpense",
        ],
        "implication": (
            "Non-operating income/pension items sit between operating income"
            " and pre-tax income — they are in EPS but not in the operating"
            " story management markets. Large or volatile amounts here mean"
            " operating income and EPS can tell different stories."
        ),
    },
}

# benchmark concepts, first match wins
REVENUE = [
    "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
    "us-gaap_Revenues",
    "us-gaap_RevenueFromContractWithCustomerIncludingAssessedTax",
    "us-gaap_SalesRevenueNet",
]
OPERATING_INCOME = ["us-gaap_OperatingIncomeLoss"]
PRETAX_INCOME = [
    "us-gaap_IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "us-gaap_IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    "us-gaap_IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
]
NET_INCOME = ["us-gaap_NetIncomeLoss", "us-gaap_ProfitLoss"]
TAX = ["us-gaap_IncomeTaxExpenseBenefit"]
CFO = [
    "us-gaap_NetCashProvidedByUsedInOperatingActivities",
    "us-gaap_NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
]
DILUTED_SHARES = ["us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding"]
DILUTED_EPS = ["us-gaap_EarningsPerShareDiluted"]
AR = ["us-gaap_AccountsReceivableNetCurrent", "us-gaap_ReceivablesNetCurrent"]
INVENTORY = ["us-gaap_InventoryNet"]


# ---------------------------------------------------------------- fact maps


def build_fact_maps(x):
    """concept -> {period_key: value} for non-dimensioned facts, plus the
    filing's duration periods (newest first) and instant dates."""
    df = x.facts.query().to_dataframe()
    df = df[~df["is_dimensioned"].fillna(False) & df["numeric_value"].notna()]
    facts: dict[str, dict[str, float]] = {}
    for _, r in df.iterrows():
        facts.setdefault(norm_concept(str(r["concept"])), {})[r["period_key"]] = r[
            "numeric_value"
        ]
    durations = sorted(
        {
            (r["period_key"], r["period_start"], r["period_end"])
            for _, r in df[df["period_type"] == "duration"].iterrows()
        },
        key=lambda t: (t[2], t[1]),
        reverse=True,
    )
    # keep full-year-ish periods (>300 days) if any exist, else all
    import datetime as dt

    def days(t):
        try:
            return (
                dt.date.fromisoformat(str(t[2])) - dt.date.fromisoformat(str(t[1]))
            ).days
        except (ValueError, TypeError):
            return 0

    annual = [t for t in durations if days(t) > 300]
    periods = [t[0] for t in (annual or durations)]
    instants = sorted(
        {r["period_key"] for _, r in df[df["period_type"] == "instant"].iterrows()},
        reverse=True,
    )
    return facts, periods, instants


def first_present(facts, candidates, periods):
    for c in candidates:
        vals = facts.get(c)
        if vals:
            series = [vals.get(p) for p in periods]
            if any(v is not None for v in series):
                return c, series
    return None, [None] * len(periods)


def calc_placement(x, element_id: str) -> str | None:
    """Where does this concept land on the way to EPS? Walk calc ancestors."""
    op = set(OPERATING_INCOME)
    pretax = set(PRETAX_INCOME)
    ni = set(NET_INCOME)
    for _, tree in x.calculation_trees.items():
        nodes = getattr(tree, "all_nodes", {}) or {}
        if element_id not in nodes:
            continue
        chain = []
        cur = nodes[element_id].parent
        seen = set()
        while cur and cur not in seen:
            seen.add(cur)
            chain.append(cur)
            node = nodes.get(cur)
            cur = node.parent if node else None
        chain_set = set(chain)
        if chain_set & op:
            return "inside operating income (and therefore in pre-tax income and EPS)"
        if chain_set & pretax:
            return "below operating income but ABOVE the tax line — flows into pre-tax income and EPS"
        if chain_set & ni:
            return "between pre-tax income and net income (tax-line area) — still in EPS"
        if "us-gaap_NetCashProvidedByUsedInOperatingActivities" in chain_set or (
            chain_set & set(CFO)
        ):
            return "cash flow statement add-back (non-cash expense already inside net income)"
    return None


# ---------------------------------------------------------------- analysis


def pct(x_val, base) -> float | None:
    if x_val is None or not base:
        return None
    return round(100.0 * x_val / base, 1)


def analyze(x) -> dict:
    facts, periods, instants = build_fact_maps(x)
    p0 = periods[0] if periods else None

    bench = {}
    series = {}
    for name, cands in [
        ("revenue", REVENUE),
        ("operating_income", OPERATING_INCOME),
        ("pretax_income", PRETAX_INCOME),
        ("net_income", NET_INCOME),
        ("tax_expense", TAX),
        ("operating_cash_flow", CFO),
        ("diluted_shares", DILUTED_SHARES),
        ("diluted_eps", DILUTED_EPS),
    ]:
        concept, vals = first_present(facts, cands, periods)
        series[name] = vals
        bench[name] = vals[0] if vals else None

    flags = []
    seen_in_category: set[tuple] = set()
    for category, spec in WATCHLIST.items():
        for concept in spec["concepts"]:
            vals = facts.get(concept)
            if not vals:
                continue
            per_period = [vals.get(p) for p in periods]
            if not any(v for v in per_period if v):
                continue
            cur = per_period[0]
            # overlapping tags (e.g. ShareBasedCompensation vs Allocated...)
            # report the same amount — flag the economics once
            if (category, cur) in seen_in_category:
                continue
            seen_in_category.add((category, cur))
            n_present = sum(1 for v in per_period if v)
            el = x.element_catalog.get(concept)
            flags.append(
                {
                    "category": category,
                    "concept": concept.replace("_", ":", 1),
                    "label": next(iter(el.labels.values()), None) if el else None,
                    "values_by_period": {
                        p: fmt_value(v) for p, v in zip(periods, per_period)
                    },
                    "pct_of_revenue": pct(cur, bench["revenue"]),
                    "pct_of_operating_income": pct(cur, bench["operating_income"]),
                    "pct_of_pretax_income": pct(cur, bench["pretax_income"]),
                    "placement": calc_placement(x, concept)
                    or "tagged at disclosure level only — not on a primary"
                    " statement calculation tree; check which line item"
                    " absorbs it via search_facts",
                    "recurring": n_present >= 2,
                    "implication": spec["implication"],
                }
            )

    # ---------------- computed diagnostics
    diag = {}
    ni, cfo = bench["net_income"], bench["operating_cash_flow"]
    if ni and cfo is not None:
        entry = {
            "net_income": fmt_value(ni),
            "operating_cash_flow": fmt_value(cfo),
        }
        if ni > 0:
            ratio = round(cfo / ni, 2)
            entry["operating_cash_flow_over_net_income"] = ratio
            entry["read"] = (
                "healthy: earnings fully backed by cash"
                if ratio >= 1
                else "net income exceeds operating cash flow — earnings carried"
                " by accruals; check receivables, inventory, capitalization"
            )
        else:
            entry["read"] = (
                "net income is negative — compare the absolute figures: positive"
                " operating cash flow alongside GAAP losses usually means heavy"
                " non-cash charges (D&A, impairments, SBC); negative both means"
                " the losses are cash-real"
            )
        diag["cash_conversion"] = entry
        if bench["revenue"]:
            diag["accruals_pct_of_revenue"] = pct(ni - cfo, bench["revenue"])

    tax_s, pre_s = series["tax_expense"], series["pretax_income"]
    etr = [
        round(100 * t / p, 1) if t is not None and p else None
        for t, p in zip(tax_s, pre_s)
    ]
    if any(e is not None for e in etr):
        d = {"by_period": dict(zip(periods, etr))}
        real = [e for e in etr if e is not None]
        if len(real) >= 2 and abs(real[0] - real[1]) > 3:
            d["flag"] = (
                f"effective tax rate moved {real[1]}% -> {real[0]}% — EPS"
                " change is partly a tax-line event, not operations"
            )
        if real and (real[0] < 12 or real[0] > 30):
            d.setdefault("flag", "")
            d["flag"] = (
                d["flag"]
                + f" ETR of {real[0]}% is far from typical statutory rates —"
                " check one-time tax items / valuation allowances"
            ).strip()
        diag["effective_tax_rate"] = d

    eps_s, ni_s, sh_s = series["diluted_eps"], series["net_income"], series["diluted_shares"]
    if len(periods) >= 2 and all(
        v is not None for v in (eps_s[0], eps_s[1], ni_s[0], ni_s[1], sh_s[0], sh_s[1])
    ) and eps_s[1] and ni_s[1] and sh_s[1]:
        eps_g = 100 * (eps_s[0] / eps_s[1] - 1)
        ni_g = 100 * (ni_s[0] / ni_s[1] - 1)
        sh_g = 100 * (sh_s[0] / sh_s[1] - 1)
        diag["eps_decomposition"] = {
            "diluted_eps_growth_pct": round(eps_g, 1),
            "net_income_growth_pct": round(ni_g, 1),
            "diluted_share_count_change_pct": round(sh_g, 1),
            "read": (
                f"of the {eps_g:.1f}% EPS growth, {ni_g:.1f}pts came from"
                f" earnings and roughly {eps_g - ni_g:.1f}pts from the share"
                " count (buybacks/dilution)"
            ),
        }

    # receivables / inventory vs revenue growth (needs 2 instants + 2 durations)
    rev_s = series["revenue"]
    if len(instants) >= 2 and len(rev_s) >= 2 and rev_s[0] and rev_s[1]:
        rev_g = 100 * (rev_s[0] / rev_s[1] - 1)
        for label, cands in [("receivables", AR), ("inventory", INVENTORY)]:
            _, ivals = first_present(facts, cands, instants)
            if ivals[0] and ivals[1]:
                g = 100 * (ivals[0] / ivals[1] - 1)
                entry = {
                    f"{label}_growth_pct": round(g, 1),
                    "revenue_growth_pct": round(rev_g, 1),
                }
                if g - rev_g > 10:
                    entry["flag"] = (
                        f"{label} growing {g - rev_g:.0f}pts faster than revenue"
                        " — classic revenue-quality / demand red flag"
                    )
                diag[f"{label}_vs_revenue"] = entry

    return {
        "entity": x.entity_name,
        "period_of_report": str(x.period_of_report),
        "periods_analyzed": periods,
        "benchmarks": {
            k: fmt_value(v) if k != "diluted_eps" else v for k, v in bench.items()
        },
        "adjustment_flags": sorted(
            flags,
            key=lambda f: abs(f["pct_of_pretax_income"] or 0),
            reverse=True,
        ),
        "diagnostics": diag,
        "note": (
            "flags are drawn from consolidated (non-dimensioned) tagged facts;"
            " company-specific extension tags and untagged narrative items"
            " (e.g. adjustments only described in the non-GAAP reconciliation"
            " table) will not appear — read the earnings-release exhibit for"
            " those"
        ),
    }
