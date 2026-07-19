"""UK Companies House — the first non-US fundamentals source.

Bring-your-own-key: reads COMPANIES_HOUSE_API_KEY from the environment.
A free key is issued at https://developer.company-information.service.gov.uk
(create an application, use the REST API key). Auth is HTTP Basic with the
key as username and an empty password — nothing is stored in the repo.

Coverage (v1, honest): company discovery, profiles, filing history, officers,
and persons with significant control (PSC — who *actually* owns/controls the
company, the register the shell-company hunters care about). Parsed iXBRL
accounts are NOT here yet; the filing-history entries link the account
documents for retrieval.
"""

from __future__ import annotations

import os

import httpx

BASE = "https://api.company-information.service.gov.uk"


class CompaniesHouseKeyMissingError(RuntimeError):
    pass


def _key() -> str:
    key = os.environ.get("COMPANIES_HOUSE_API_KEY", "").strip()
    if not key:
        raise CompaniesHouseKeyMissingError(
            "COMPANIES_HOUSE_API_KEY is not set. Get a free key at "
            "https://developer.company-information.service.gov.uk (create an "
            "application → REST API key) and export it — nothing is stored "
            "in the repo."
        )
    return key


def _get(path: str, params: dict | None = None) -> dict:
    resp = httpx.get(f"{BASE}{path}", params=params, auth=(_key(), ""),
                     timeout=30)
    resp.raise_for_status()
    return resp.json()


def find_company(query: str, limit: int = 10) -> dict:
    """Search UK companies by name or number."""
    data = _get("/search/companies", {"q": query, "items_per_page": limit})
    items = [
        {
            "company_number": i.get("company_number"),
            "title": i.get("title"),
            "status": i.get("company_status"),
            "type": i.get("company_type"),
            "incorporated": i.get("date_of_creation"),
            "address": (i.get("address") or {}).get("snippet")
            or ", ".join(
                str(v) for v in (i.get("address") or {}).values() if v
            ) or None,
        }
        for i in data.get("items", [])
    ]
    return {"query": query, "count": len(items), "companies": items}


def profile(company_number: str) -> dict:
    """Company profile + officers + persons with significant control (PSC).

    PSC is the UK's beneficial-ownership register — for a shell/holding
    structure this is where the actual controllers surface (or conspicuously
    don't: 'no PSC' statements on an active trading company are themselves a
    flag)."""
    n = company_number.strip()
    prof = _get(f"/company/{n}")
    out = {
        "company_number": n,
        "name": prof.get("company_name"),
        "status": prof.get("company_status"),
        "type": prof.get("type"),
        "incorporated": prof.get("date_of_creation"),
        "sic_codes": prof.get("sic_codes"),
        "registered_office": prof.get("registered_office_address"),
        "accounts": {
            "last_made_up_to": (prof.get("accounts") or {})
            .get("last_accounts", {}).get("made_up_to"),
            "type": (prof.get("accounts") or {})
            .get("last_accounts", {}).get("type"),
            "next_due": (prof.get("accounts") or {}).get("next_due"),
            "overdue": (prof.get("accounts") or {}).get("overdue"),
        },
        "jurisdiction": prof.get("jurisdiction"),
        "has_charges": prof.get("has_charges"),
        "has_insolvency_history": prof.get("has_insolvency_history"),
    }
    try:
        off = _get(f"/company/{n}/officers", {"items_per_page": 20})
        out["officers"] = [
            {
                "name": o.get("name"),
                "role": o.get("officer_role"),
                "appointed": o.get("appointed_on"),
                "resigned": o.get("resigned_on"),
                "nationality": o.get("nationality"),
                "occupation": o.get("occupation"),
            }
            for o in off.get("items", [])
        ]
    except httpx.HTTPStatusError:
        out["officers"] = None
    try:
        psc = _get(
            f"/company/{n}/persons-with-significant-control",
            {"items_per_page": 20},
        )
        out["persons_with_significant_control"] = [
            {
                "name": p.get("name"),
                "kind": p.get("kind"),
                "natures_of_control": p.get("natures_of_control"),
                "notified_on": p.get("notified_on"),
                "ceased_on": p.get("ceased_on"),
                "country_of_residence": p.get("country_of_residence"),
            }
            for p in psc.get("items", [])
        ]
    except httpx.HTTPStatusError:
        out["persons_with_significant_control"] = None
    return out


def filings(company_number: str, category: str | None = None,
            limit: int = 25) -> dict:
    """Filing history for a UK company. category e.g. 'accounts',
    'confirmation-statement', 'incorporation', 'mortgage' (charges)."""
    n = company_number.strip()
    params: dict = {"items_per_page": limit}
    if category:
        params["category"] = category
    data = _get(f"/company/{n}/filing-history", params)
    items = [
        {
            "date": i.get("date"),
            "category": i.get("category"),
            "type": i.get("type"),
            "description": i.get("description"),
            "document_id": (i.get("links") or {})
            .get("document_metadata", "").rsplit("/", 1)[-1] or None,
        }
        for i in data.get("items", [])
    ]
    return {
        "company_number": n,
        "total_count": data.get("total_count"),
        "returned": len(items),
        "filings": items,
    }
