import hashlib
import json

MODEL_ID = "PUBLIC-MODEL-ANNUAL"
METRIC_ID = "PUBLIC-REPORTED-SALES"
PRODUCT_IDS = {
    "Nubeqa": "PUBLIC-NUBEQA",
    "Kerendia": "PUBLIC-KERENDIA",
    "Eylea": "PUBLIC-EYLEA",
    "Xarelto": "PUBLIC-XARELTO",
}
MODEL_CONTRACT = {
    "model_id": MODEL_ID,
    "contract_version": "public-annual-v1",
    "fact_table": "published_product_sales",
    "time_column": "fiscal_year",
    "supported_grains": ["year"],
    "grain": ["product_id", "market_id", "fiscal_year"],
    "schema": {
        "published_product_sales": {
            "product_id": "TEXT", "market_id": "TEXT", "fiscal_year": "INTEGER",
            "sales_eur_million": "INTEGER", "source_table": "TEXT",
            "source_row_label": "TEXT",
        }
    },
    "required_row_filter": {"data_classification": "public_reported_actual"},
    "supported_metric_ids": [METRIC_ID],
}
METRIC_CONTRACT = {
    "metric_id": METRIC_ID,
    "name": "Reported Sales",
    "aliases": ["reported sales", "annual sales", "sales", "revenue"],
    "approval_status": "approved",
    "unit": "EUR million",
    "operator": "sum_within_one_fiscal_year",
    "column": "sales_eur_million",
    "owner_id": "DEMO-OWNER-PUBLIC",
    "synthetic_record": False,
}


def source_provenance(evidence: dict) -> dict:
    return {
        key: evidence[key] for key in (
            "source_url", "source_title", "source_sha256", "source_snapshot",
            "retrieved_at_utc", "unit", "grain",
        )
    } | {
        "data_classification": "public_reported_actual",
        "evidence_sha256": hashlib.sha256(
            json.dumps(evidence, sort_keys=True, ensure_ascii=True).encode("utf-8")
        ).hexdigest(),
    }


def _selection(values, field):
    if not isinstance(values, list) or not 1 <= len(values) <= 100:
        raise ValueError(f"{field} requires 1 to 100 explicit selections.")
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError(f"{field} requires nonempty string selections.")
    if len(values) != len(set(values)):
        raise ValueError(f"{field} contains duplicate selections.")
    return sorted(values)


def compute_public_annual(
    evidence: dict, *, product_ids: list[str], market_ids: list[str],
    months: list[str], metric_ids: list[str],
) -> dict:
    products = _selection(product_ids, "product_ids")
    markets = _selection(market_ids, "market_ids")
    years = _selection(months, "fiscal_years")
    metrics = _selection(metric_ids, "metric_ids")
    if evidence.get("data_classification") != "public_reported_actual":
        raise ValueError("Only reviewed public reported actuals are supported.")
    if evidence.get("unit") != "EUR million":
        raise ValueError("Source must use published EUR million values.")
    if markets != ["GLOBAL"]:
        raise ValueError("Only global figures are published in this source.")
    if metrics != [METRIC_ID]:
        raise ValueError("Only Reported Sales is available; no forecasts or invented metrics.")
    if not set(products).issubset(PRODUCT_IDS.values()):
        raise ValueError("Product is outside the reviewed published selection.")
    if any(year not in ("2024", "2025") for year in years):
        raise ValueError("Only fiscal-year labels 2024 and 2025 are supported, not months.")
    records = {}
    for item in evidence.get("rows") or []:
        name = item.get("product_name")
        year = item.get("year")
        amount = item.get("sales_eur_million")
        if (
            name not in PRODUCT_IDS or isinstance(year, bool)
            or not isinstance(year, int) or year not in (2024, 2025)
        ):
            raise ValueError("Unreviewed source product or fiscal year.")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise ValueError("Published sales must be nonnegative integer EUR million.")
        if not all(isinstance(item.get(key), str) and item[key] for key in (
            "source_table", "source_row_label",
        )):
            raise ValueError("Source row references are missing.")
        key = (PRODUCT_IDS[name], str(year))
        if key in records:
            raise ValueError("Duplicate public product/fiscal-year fact.")
        records[key] = item
    expected = {(product, year) for product in PRODUCT_IDS.values() for year in ("2024", "2025")}
    if set(records) != expected:
        raise ValueError("Public source does not contain the complete reviewed selection.")
    rows = []
    for year in years:
        for product in products:
            item = records[(product, year)]
            rows.append({
                "product_id": product, "product_name": item["product_name"],
                "market_id": "GLOBAL", "market_name": "Global",
                "fiscal_year": int(year), METRIC_ID: item["sales_eur_million"],
                "source_table": item["source_table"],
                "source_row_label": item["source_row_label"],
            })
    totals = {METRIC_ID: sum(row[METRIC_ID] for row in rows)} if len(years) == 1 else {}
    return {
        "rows": rows,
        "totals": totals,
        "units": {METRIC_ID: "EUR million"},
        "grain": ["fiscal_year", "product_id", "market_id"],
        "time_column": "fiscal_year",
        "time_label": "Fiscal year",
        "source_row_count": len(rows),
        "synthetic_record": False,
        "data_classification": "public_reported_actual",
        "calculation_version": "public-annual-v1",
        "source_provenance": source_provenance(evidence),
        "aggregation_note": (
            "Published global reported sales in EUR million. A single-year total covers "
            "only the selected products, not the full Pharmaceuticals division. "
            "No combined total is produced across fiscal years. No forecasts, "
            "currency-adjusted growth, country or monthly figures are inferred. "
            "Governance identities, certification and approvals remain simulated."
        ),
    }
