import re

from smart_librarian.reporting.public_annual import (
    METRIC_CONTRACT,
    MODEL_CONTRACT,
    MODEL_ID,
    PRODUCT_IDS,
    source_provenance,
)


def public_contract_gaps(catalog) -> list[str]:
    model = catalog.model()
    gaps = []
    if any(model.get(key) != value for key, value in MODEL_CONTRACT.items()):
        gaps.append("public_annual_model_contract_not_executable")
    metric = catalog.metric(METRIC_CONTRACT["metric_id"]) or {}
    if any(metric.get(key) != value for key, value in METRIC_CONTRACT.items()):
        gaps.append("public_annual_metric_contract_not_executable")
    if catalog.catalog.get("data_classification") != "public_reported_actual":
        gaps.append("public_source_classification_invalid")
    return gaps


def public_scope_gaps(model: dict, intent: dict) -> list[str]:
    coverage = model.get("coverage") or {}
    reasons = []
    if intent.get("grain") != "year":
        reasons.append("unsupported_grain")
    for field, reason in (
        ("product_ids", "unknown_product_id"),
        ("market_ids", "unknown_market_id"),
        ("months", "fiscal_year_out_of_coverage"),
    ):
        if not set(intent.get(field) or []).issubset(coverage.get(field) or []):
            reasons.append(reason)
    if any(not re.fullmatch(r"\d{4}", year) for year in intent.get("months") or []):
        reasons.append("invalid_fiscal_year")
    return sorted(set(reasons))


def public_spec_metadata(catalog) -> dict:
    return {
        "synthetic_record": False,
        "data_classification": "public_reported_actual",
        "time_column": "fiscal_year",
        "time_label": "Fiscal year",
        "period_field_semantics": (
            "intent.months is the legacy period-selection key. Its YYYY values are "
            "fiscal years in this domain, not calendar months or dates."
        ),
        "source_provenance": source_provenance(catalog.public_evidence),
        "status_note": (
            "Actual published Bayer annual sales; frozen public-source snapshot. "
            "Local owner, endorsement, identity and approval metadata are simulated, "
            "not Bayer certification or authenticated enterprise permissions."
        ),
    }


def public_evidence_items(catalog, model, candidate, metrics) -> list[dict]:
    source = catalog.public_evidence
    records = [
        (
            "public_source", source["source_url"], source["source_sha256"],
            f"{source['source_title']}; table Best-selling Pharmaceuticals products. "
            "Reported global sales, EUR million, fiscal years 2024 and 2025. "
            "Only four selected products are exposed; no monthly/country/forecast data.",
            "Published actuals; frozen snapshot, not live company systems",
        ),
        (
            "source_snapshot", str(catalog.source_path), catalog.fingerprint(),
            f"Evidence file and reviewed metadata fingerprint bound to this specification; "
            f"source retrieved at {source['retrieved_at_utc']}.",
            "Snapshot drift is checked at approval and render",
        ),
        (
            "metric", "public-annual-v1", METRIC_CONTRACT["metric_id"],
            "Reported Sales copies published integer EUR million values. Totals sum "
            "selected products only within one fiscal year; comparisons never sum years.",
            "Fixed executable calculation; no LLM arithmetic or invented forecast",
        ),
        (
            "coverage", "public-annual-v1", MODEL_ID,
            "Confirmed products, Global scope and fiscal-year labels must exist in the "
            "published selection. Annual grain only; unavailable scope is not substituted.",
            "Deterministic source coverage validation",
        ),
        (
            "demo_governance", "public-annual-v1", model.get("owner_id"),
            "Demo Public-data Steward owns the local generated asset. Endorsement and "
            "approver roles are simulated, not Bayer approval or production authorization.",
            "Explicitly simulated governance over real published figures",
        ),
    ]
    if candidate:
        records.append((
            "candidate_report", "runtime.sqlite#/generated_reports", candidate["asset_id"],
            "An existing active local asset matches the public source fingerprint, "
            "annual scope and requested metric. Recorded model-to-report lineage "
            "supports reuse without generating a duplicate.",
            "Local runtime registry, not Power BI service publication",
        ))
    return [
        {
            "evidence_id": f"EV-{index:02d}", "kind": kind, "ref_path": reference,
            "record_id": identifier, "detail": detail, "status": status,
        }
        for index, (kind, reference, identifier, detail, status) in enumerate(records, 1)
    ]


def parse_public_message(text: str, choices: dict, catalog) -> dict:
    from smart_librarian.domain.parser import (
        _find_phrases,
        _market_aliases,
        _metric_aliases,
        _product_aliases,
    )

    lowered = text.lower()
    normalized = lowered.replace("_", " ")
    products, remaining = _find_phrases(normalized, _product_aliases(choices))
    if re.search(r"\ball (?:four |4 |selected |available )?products\b", lowered):
        products = sorted(PRODUCT_IDS.values())
    markets, remaining = _find_phrases(remaining, _market_aliases(choices))
    if re.search(r"\b(worldwide|world wide)\b", lowered):
        markets = ["GLOBAL"]
    metric_aliases, _ = _metric_aliases(catalog)
    metrics, _ = _find_phrases(remaining, metric_aliases)
    years = sorted(set(re.findall(r"\b(?:19|20)\d{2}\b", lowered)))
    year_range = re.search(
        r"\b((?:19|20)\d{2})\s*(?:through|to|[-–])\s*((?:19|20)\d{2})\b",
        lowered,
    )
    unsupported = []
    if year_range:
        first, last = map(int, year_range.groups())
        if 0 <= last - first < 100:
            years = [str(year) for year in range(first, last + 1)]
        else:
            unsupported.append("The fiscal-year range is invalid or too wide.")
            years = []
    if re.search(r"\b(forecasts?|budget|variance|profit|margin|units|growth)\b", lowered):
        unsupported.append(
            "Only published Reported Sales is available; forecasts, variance, profit, "
            "units and growth metrics are not implemented."
        )
    subannual = re.search(
        r"\b(months?|monthly|quarters?|quarterly|q[1-4]|daily|days?|weekly|weeks?|"
        r"january|february|march|april|may|june|july|august|september|october|november|"
        r"december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b", lowered,
    )
    if subannual:
        unsupported.append("This source is annual only; monthly, quarterly and daily data is absent.")
    if re.search(
        r"\b(country|countries|country-level|germany|german|finland|finnish|france|french|"
        r"china|japan|brazil|india|canada|italy|spain|sweden|norway|denmark|"
        r"united states|united kingdom|usa|us|uk|europe|asia|america|de|fi|fr)\b", lowered,
    ):
        unsupported.append("This source has Global scope only; no country or regional values.")
    unresolved = [
        field for field, values in (
            ("product_ids", products), ("market_ids", markets),
            ("metric_ids", metrics), ("months", years),
        ) if not values
    ]
    return {
        "product_ids": products, "market_ids": markets, "metric_ids": metrics,
        "months": years, "grain": "year", "unresolved": unresolved,
        "invalidated": [field for field in unresolved if (
            (field == "months" and (year_range or subannual))
            or (field == "metric_ids" and unsupported)
        )],
        "unsupported": unsupported,
        "limitations": (
            "Annual public-source parser: review exact products, Global scope and fiscal "
            "years before confirming. The legacy months key holds YYYY fiscal-year labels."
        ),
        "mode": "offline",
    }
