import re

from smart_librarian.reporting.public_financials import (
    METRIC_CONTRACT,
    METRIC_ID,
    MODEL_CONTRACT,
    PRODUCT_IDS,
    source_provenance,
)


def financial_contract_gaps(catalog):
    gaps = []
    if any(catalog.model().get(key) != value for key, value in MODEL_CONTRACT.items()):
        gaps.append("public_financial_model_contract_not_executable")
    metric = catalog.metric(METRIC_ID) or {}
    if any(metric.get(key) != value for key, value in METRIC_CONTRACT.items()):
        gaps.append("public_financial_metric_contract_not_executable")
    if catalog.catalog.get("data_classification") != "public_reported_actual":
        gaps.append("public_source_classification_invalid")
    return gaps


def financial_scope_gaps(model, intent):
    coverage = model.get("coverage") or {}
    kinds = coverage.get("period_kinds") or {}
    reasons = []
    grain = intent.get("grain")
    if grain not in MODEL_CONTRACT["supported_grains"]:
        reasons.append("unsupported_grain")
    for field, reason in (
        ("product_ids", "unknown_product_id"),
        ("market_ids", "unknown_market_id"),
        ("months", "reporting_period_out_of_coverage"),
    ):
        if not set(intent.get(field) or []).issubset(coverage.get(field) or []):
            reasons.append(reason)
    if any(kinds.get(period) != grain for period in intent.get("months") or []):
        reasons.append("incompatible_reporting_period_types")
    return sorted(set(reasons))


def financial_spec_metadata(catalog):
    return {
        "synthetic_record": False, "data_classification": "public_reported_actual",
        "time_column": "period", "time_label": "Reporting period",
        "period_field_semantics": (
            "intent.months holds explicit published reporting-period labels. "
            "They are not calendar months; annual, quarterly and half-year types cannot mix."
        ),
        "source_provenance": source_provenance(catalog.public_evidence),
        "status_note": (
            "Actual published Bayer sales from frozen official disclosures. Source report "
            "versions and restatements are retained. Identities, ownership, endorsement, "
            "approvals and the report registry are simulated local demonstration metadata."
        ),
    }


def financial_evidence_items(catalog, model, candidate, metrics):
    items = [{
        "evidence_id": f"EV-{index:02d}", "kind": "public_source",
        "ref_path": source["source_url"], "record_id": source["source_id"],
        "detail": f"{source['source_title']}. {source['notes']}",
        "status": f"Frozen reported actuals; SHA-256 {source['source_sha256']}",
    } for index, source in enumerate(catalog.public_evidence["sources"], 1)]
    items.extend([
        {
            "evidence_id": "EV-SCOPE", "kind": "coverage",
            "ref_path": "public-financials-v2", "record_id": model["model_id"],
            "detail": (
                "15 published products/product families; Global reported sales in EUR "
                "million. Explicit annual, quarter or half-year periods only; no mixed "
                "grains, period aggregation, inferred quarters, country data or forecasts."
            ), "status": "Fixed source-backed executable contract",
        },
        {
            "evidence_id": "EV-GOVERNANCE", "kind": "demo_governance",
            "ref_path": "local-demo", "record_id": model["owner_id"],
            "detail": "Public figures are real; local steward and approvals are simulated.",
            "status": "Not Bayer certification or authenticated enterprise permissions",
        },
    ])
    if candidate:
        items.append({
            "evidence_id": "EV-REUSE", "kind": "candidate_report",
            "ref_path": "runtime.sqlite#/generated_reports",
            "record_id": candidate["asset_id"],
            "detail": "Existing local report covers the confirmed source snapshot and scope.",
            "status": "Local registry, not Power BI service publication",
        })
    return items


def parse_financial_message(text, choices, catalog):
    from smart_librarian.domain.parser import _find_phrases, _product_aliases

    lowered = text.lower().replace("™", "")
    aliases = _product_aliases(choices)
    aliases.update({
        "mirena": "PUBLIC-MIRENA-FAMILY", "kyleena": "PUBLIC-MIRENA-FAMILY",
        "jaydess": "PUBLIC-MIRENA-FAMILY", "yaz": "PUBLIC-YAZ-FAMILY",
        "yasmin": "PUBLIC-YAZ-FAMILY", "yasminelle": "PUBLIC-YAZ-FAMILY",
        "kovaltry": "PUBLIC-KOVALTRY-JIVI", "jivi": "PUBLIC-KOVALTRY-JIVI",
        "gadovist": "PUBLIC-GADOVIST-FAMILY",
    })
    products, remaining = _find_phrases(lowered, aliases)
    if re.search(r"\ball (?:15 |published |available )?products\b", lowered):
        products = sorted(PRODUCT_IDS.values())
    markets = ["GLOBAL"] if re.search(r"\b(global|worldwide|world wide)\b", remaining) else []
    metrics = [METRIC_ID] if re.search(r"\b(sales|revenue)\b", remaining) else []
    unsupported, invalidated = [], []
    if re.search(r"\b(forecasts?|budget|variance|profit|margin|units|growth|adjusted)\b", remaining):
        unsupported.append(
            "Only published Reported Sales is implemented; no forecast, profit, "
            "unit, variance or adjusted-growth metric."
        )
    if re.search(
        r"\b(months?|monthly|daily|weekly|january|february|march|april|may|june|july|"
        r"august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|"
        r"sep|oct|nov|dec)\b", remaining,
    ):
        unsupported.append("Monthly, weekly and daily figures are not published in this snapshot.")
    if re.search(
        r"\b(country|countries|regional?|germany|german|finland|finnish|france|french|"
        r"china|japan|brazil|india|canada|italy|spain|sweden|norway|denmark|"
        r"united states|united kingdom|usa|us|uk|europe|asia|america|de|fi|fr)\b",
        remaining,
    ):
        unsupported.append("Product figures have Global scope only, not country or regional scope.")
    years = sorted(set(re.findall(r"\b(?:19|20)\d{2}\b", remaining)))
    year_range = re.search(r"\b((?:19|20)\d{2})\s*(?:through|to|[-–])\s*((?:19|20)\d{2})\b",
                           remaining)
    if year_range:
        first, last = map(int, year_range.groups())
        if 0 <= last - first < 20:
            years = [str(year) for year in range(first, last + 1)]
        else:
            years = []
            unsupported.append("Invalid or too-wide year range; select explicit reporting periods.")
            invalidated.append("months")
    quarters = sorted(set(re.findall(r"\bq([1-4])\b", remaining)))
    halves = sorted(set(re.findall(r"\bh([12])\b", remaining)))
    if re.search(r"\bfirst half\b", remaining):
        halves = sorted(set(halves + ["1"]))
    quarter_range = re.search(r"\bq([1-4])\s*(?:through|to|[-–])\s*q([1-4])\b", remaining)
    if quarter_range:
        first, last = map(int, quarter_range.groups())
        if first <= last:
            quarters = [str(value) for value in range(first, last + 1)]
        else:
            unsupported.append("Invalid quarter range.")
    if quarters and halves:
        grain, periods = "", []
        unsupported.append("Quarter and half-year selections cannot be combined in one report.")
        invalidated.extend(["months", "grain"])
    elif quarters:
        grain = "quarter"
        explicit = re.findall(r"\b(20\d{2})[- ]q([1-4])\b|\bq([1-4])\s+(20\d{2})\b", remaining)
        periods = sorted({f"{y1 or y2}-Q{q1 or q2}" for y1, q1, q2, y2 in explicit})
        if len(quarters) == 1 or len(years) == 1 or quarter_range:
            periods = sorted(f"{year}-Q{q}" for year in years for q in quarters)
        elif len(periods) != max(len(years), len(quarters)):
            unsupported.append("Ambiguous quarter/year pairing; select explicit periods.")
            invalidated.append("months")
    elif halves:
        grain = "half_year"
        periods = sorted(f"{year}-H{half}" for year in years for half in halves)
    elif re.search(r"\b(quarterly|quarters?|half[- ]year|half[- ]yearly)\b", remaining):
        grain, periods = "", []
        unsupported.append("Specify an explicit quarter (Q1/Q2/Q4) or half-year (H1) and year.")
        invalidated.extend(["months", "grain"])
    else:
        grain, periods = "year", years
    if quarters and re.search(r"\b(annual|fiscal year|full[- ]year)\b", remaining):
        unsupported.append("Annual and quarterly requirements cannot mix; select one period type.")
    if grain == "half_year" and len(halves) > 1:
        unsupported.append("Specify one half-year at a time; H2 is not available.")
    if periods and any(p not in choices["months"] for p in periods):
        unsupported.append("Some requested periods are outside published snapshot coverage.")
    unresolved = [field for field, values in (
        ("product_ids", products), ("market_ids", markets), ("metric_ids", metrics),
        ("months", periods), ("grain", grain),
    ) if not values]
    return {
        "product_ids": products, "market_ids": markets, "metric_ids": metrics,
        "months": periods, "grain": grain, "unresolved": unresolved,
        "invalidated": sorted(set(invalidated)), "unsupported": unsupported,
        "mode": "offline", "limitations": (
            "Source-backed keyword extraction only. Review exact products/product families, "
            "Global scope and reporting periods before confirming. Product-family sales "
            "cannot be split into individual brands. No missing period is inferred."
        ),
    }
