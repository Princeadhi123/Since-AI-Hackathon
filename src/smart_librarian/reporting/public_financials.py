import copy
import re
from datetime import date, datetime
from urllib.parse import urlparse

METRIC_ID = "PUBLIC-REPORTED-SALES"
MODEL_ID = "PUBLIC-MODEL-FINANCIALS"
PRODUCT_IDS = {
    "Eylea": "PUBLIC-EYLEA", "Nubeqa": "PUBLIC-NUBEQA", "Xarelto": "PUBLIC-XARELTO",
    "Mirena / Kyleena / Jaydess": "PUBLIC-MIRENA-FAMILY", "Kerendia": "PUBLIC-KERENDIA",
    "Adempas": "PUBLIC-ADEMPAS", "YAZ / Yasmin / Yasminelle": "PUBLIC-YAZ-FAMILY",
    "Kovaltry / Jivi": "PUBLIC-KOVALTRY-JIVI", "CT Fluid Delivery": "PUBLIC-CT-FLUID",
    "Ultravist": "PUBLIC-ULTRAVIST", "Aspirin Cardio": "PUBLIC-ASPIRIN-CARDIO",
    "Adalat": "PUBLIC-ADALAT", "Gadovist product family": "PUBLIC-GADOVIST-FAMILY",
    "Stivarga": "PUBLIC-STIVARGA", "Glucobay": "PUBLIC-GLUCOBAY",
}
SOURCE_PERIODS = {
    "BAYER-AR2025": {
        "2024": ("year", "2024"), "2025": ("year", "2025"),
        "2024-Q4": ("quarter", "Q4 2024"), "2025-Q4": ("quarter", "Q4 2025"),
    },
    "BAYER-Q12026": {
        "2025-Q1": ("quarter", "Q1 2025"), "2026-Q1": ("quarter", "Q1 2026"),
    },
    "BAYER-H12026": {
        "2025-Q2": ("quarter", "Q2 2025"), "2026-Q2": ("quarter", "Q2 2026"),
        "2025-H1": ("half_year", "H1 2025"), "2026-H1": ("half_year", "H1 2026"),
    },
}
SOURCE_URLS = {
    "BAYER-AR2025": "https://reports.bayer.com/annual-report-2025/en/report-on-economic-position/earnings-asset-and-financial-position/business-development-by-division/pharmaceuticals.html",
    "BAYER-Q12026": "https://reports.bayer.com/quarterly-statement-q1-2026/en/business-development-by-division/pharmaceuticals.html",
    "BAYER-H12026": "https://reports.bayer.com/half-year-financial-report-q2-2026/en/interim-group-management-report/sales-earnings-and-financial-position/business-development-by-division/pharmaceuticals.html",
}
SOURCE_FILES = {
    "BAYER-AR2025": "cmr-best-selling-pharm-products-bayer-ar25.xlsx",
    "BAYER-Q12026": "cmr-best-selling-pharm-products-bayer-ir126.xlsx",
    "BAYER-H12026": "cmr-best-selling-pharm-products-bayer-ir226.xlsx",
}
PERIOD_KINDS = {period: kind for periods in SOURCE_PERIODS.values()
                for period, (kind, _) in periods.items()}
MODEL_CONTRACT = {
    "model_id": MODEL_ID, "contract_version": "public-financials-v2",
    "fact_table": "published_product_sales", "time_column": "period",
    "supported_grains": ["year", "quarter", "half_year"],
    "grain": ["product_id", "market_id", "period"],
    "schema": {"published_product_sales": {
        "product_id": "TEXT", "market_id": "TEXT", "period": "TEXT",
        METRIC_ID: "INTEGER", "source_id": "TEXT", "source_row": "INTEGER",
    }},
    "required_row_filter": {"data_classification": "public_reported_actual"},
    "supported_metric_ids": [METRIC_ID],
}
METRIC_CONTRACT = {
    "metric_id": METRIC_ID, "name": "Reported Sales",
    "aliases": ["reported sales", "sales", "revenue"],
    "approval_status": "approved", "unit": "EUR million",
    "operator": "sum_selected_products_within_one_published_period",
    "column": METRIC_ID, "owner_id": "DEMO-OWNER-PUBLIC", "synthetic_record": False,
}


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def validate_snapshot(evidence):
    if not isinstance(evidence, dict):
        raise ValueError("Public snapshot must be an object.")
    if evidence.get("schema_version") != "public-financials-v2":
        raise ValueError("Unsupported public financial snapshot version.")
    if evidence.get("data_classification") != "public_reported_actual":
        raise ValueError("Only public reported actuals are supported.")
    if evidence.get("unit") != "EUR million":
        raise ValueError("Public source units must remain EUR million.")
    for field in ("retrieved_at_utc", "grain", "disclaimer", "rights_note"):
        if not _text(evidence.get(field)):
            raise ValueError(f"Missing public source metadata: {field}.")
    stamp = datetime.fromisoformat(evidence["retrieved_at_utc"])
    if stamp.tzinfo is None:
        raise ValueError("Source retrieval timestamp must include its time zone.")
    products = evidence.get("products")
    if not isinstance(products, list) or len(products) != len(PRODUCT_IDS):
        raise ValueError("Incomplete published product selection.")
    expected_products = {identifier: name for name, identifier in PRODUCT_IDS.items()}
    if any(not isinstance(item, dict) for item in products):
        raise ValueError("Invalid product metadata.")
    if {item.get("product_id"): item.get("product_name") for item in products} != expected_products:
        raise ValueError("Unreviewed public product metadata.")
    periods = evidence.get("periods")
    if not isinstance(periods, list) or len(periods) != len(PERIOD_KINDS):
        raise ValueError("Incomplete public reporting-period selection.")
    for period in periods:
        if not isinstance(period, dict) or period.get("period_id") not in PERIOD_KINDS:
            raise ValueError("Unreviewed reporting period.")
        identifier = period["period_id"]
        if period.get("period_kind") != PERIOD_KINDS[identifier] or not _text(period.get("label")):
            raise ValueError("Invalid reporting-period metadata.")
        year = identifier[:4]
        start, end = (
            (f"{year}-01-01", f"{year}-12-31") if len(identifier) == 4 else
            (f"{year}-01-01", f"{year}-06-30") if identifier.endswith("H1") else
            (f"{year}-01-01", f"{year}-03-31") if identifier.endswith("Q1") else
            (f"{year}-04-01", f"{year}-06-30") if identifier.endswith("Q2") else
            (f"{year}-10-01", f"{year}-12-31")
        )
        if (period.get("start_date"), period.get("end_date")) != (start, end):
            raise ValueError("Reporting-period boundaries do not match the published label.")
        date.fromisoformat(start)
    if {item["period_id"] for item in periods} != set(PERIOD_KINDS):
        raise ValueError("Duplicate or missing reporting period.")
    sources = evidence.get("sources")
    if not isinstance(sources, list) or len(sources) != len(SOURCE_PERIODS):
        raise ValueError("Missing public report sources.")
    if any(not isinstance(item, dict) for item in sources):
        raise ValueError("Invalid public report source.")
    if {item.get("source_id") for item in sources} != set(SOURCE_PERIODS):
        raise ValueError("Unreviewed public report source.")
    for source in sources:
        for field in ("source_title", "source_snapshot", "html_snapshot", "notes", "retrieved_at_utc"):
            if not _text(source.get(field)):
                raise ValueError(f"Missing public report provenance: {field}.")
        for field in ("source_url", "download_url"):
            parsed = urlparse(source.get(field) or "")
            if parsed.scheme != "https" or parsed.hostname != "reports.bayer.com":
                raise ValueError("Only reviewed official Bayer report URLs are supported.")
        identifier = source["source_id"]
        if source["source_url"] != SOURCE_URLS[identifier]:
            raise ValueError("Public source URL does not match its cited report version.")
        filename = SOURCE_FILES[identifier]
        if not urlparse(source["download_url"]).path.endswith("/" + filename):
            raise ValueError("Public spreadsheet does not match its cited report version.")
        if source["source_snapshot"] != "sources/" + filename:
            raise ValueError("Unexpected local public spreadsheet snapshot path.")
        if source["html_snapshot"] != f"sources/{identifier}.html":
            raise ValueError("Unexpected local public HTML snapshot path.")
        if datetime.fromisoformat(source["retrieved_at_utc"]).tzinfo is None:
            raise ValueError("Source retrieval timestamp must include its time zone.")
        for field in ("source_sha256", "html_sha256"):
            if not isinstance(source.get(field), str) or not re.fullmatch(r"[0-9a-f]{64}", source[field]):
                raise ValueError("Invalid public source SHA-256.")
    rows = evidence.get("rows")
    if not isinstance(rows, list):
        raise ValueError("Public financial rows are missing.")
    expected = {(identifier, period) for identifier in PRODUCT_IDS.values() for period in PERIOD_KINDS}
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Public financial row is not an object.")
        key = row.get("product_id"), row.get("period")
        if key not in expected or key in seen:
            raise ValueError("Duplicate, unreviewed or invalid public product/period fact.")
        seen.add(key)
        if row.get("product_name") != expected_products[key[0]]:
            raise ValueError("Public product name does not match its reviewed identifier.")
        if row.get("market_id") != "GLOBAL" or row.get("market_name") != "Global":
            raise ValueError("Only Global published product sales are available.")
        source_periods = SOURCE_PERIODS.get(row.get("source_id"), {})
        if key[1] not in source_periods:
            raise ValueError("Fact is attributed to the wrong published report.")
        kind, column = source_periods[key[1]]
        if row.get("period_kind") != kind or row.get("source_column") != column:
            raise ValueError("Fact period differs from its cited source column.")
        amount = row.get(METRIC_ID)
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise ValueError("Reported sales must be nonnegative integer EUR million.")
        if row.get("source_table") != "Best-selling Pharmaceuticals products":
            raise ValueError("Unreviewed source table.")
        if not _text(row.get("source_row_label")):
            raise ValueError("Missing source row label.")
        number = row.get("source_row")
        if isinstance(number, bool) or not isinstance(number, int) or not 6 <= number <= 20:
            raise ValueError("Invalid source spreadsheet row reference.")
    if seen != expected:
        raise ValueError("Public financial source selection is incomplete.")


def source_provenance(evidence):
    return copy.deepcopy({
        "schema_version": evidence["schema_version"],
        "data_classification": evidence["data_classification"],
        "retrieved_at_utc": evidence["retrieved_at_utc"], "unit": evidence["unit"],
        "grain": evidence["grain"], "sources": evidence["sources"],
        "rights_note": evidence["rights_note"],
    })


def _selection(values, field):
    if not isinstance(values, list) or not 1 <= len(values) <= 100:
        raise ValueError(f"{field} requires 1 to 100 explicit selections.")
    if any(not _text(value) for value in values) or len(set(values)) != len(values):
        raise ValueError(f"{field} requires unique nonempty string selections.")
    return sorted(values)


def compute_public_financials(
    evidence, *, product_ids, market_ids, months, metric_ids, grain,
):
    validate_snapshot(evidence)
    products = _selection(product_ids, "product_ids")
    markets = _selection(market_ids, "market_ids")
    periods = _selection(months, "reporting_periods")
    metrics = _selection(metric_ids, "metric_ids")
    if not set(products).issubset(PRODUCT_IDS.values()):
        raise ValueError("Product is outside the reviewed published selection.")
    if markets != ["GLOBAL"] or metrics != [METRIC_ID]:
        raise ValueError("Only Global Reported Sales is supported.")
    if grain not in ("year", "quarter", "half_year"):
        raise ValueError("Only annual, quarterly or half-year reporting is supported.")
    if any(PERIOD_KINDS.get(period) != grain for period in periods):
        raise ValueError("Unknown or incompatible reporting periods; never mix period types.")
    rows = [copy.deepcopy(row) for row in evidence["rows"]
            if row["product_id"] in products and row["period"] in periods]
    rows.sort(key=lambda row: (row["period"], row["product_id"]))
    totals = {METRIC_ID: sum(row[METRIC_ID] for row in rows)} if len(periods) == 1 else {}
    used_sources = {row["source_id"] for row in rows}
    provenance = source_provenance(evidence)
    provenance["sources"] = [s for s in provenance["sources"] if s["source_id"] in used_sources]
    return {
        "rows": rows, "totals": totals, "units": {METRIC_ID: "EUR million"},
        "grain": ["period", "product_id", "market_id"], "period_kind": grain,
        "time_column": "period", "time_label": "Reporting period",
        "source_row_count": len(rows), "synthetic_record": False,
        "data_classification": "public_reported_actual",
        "calculation_version": "public-financials-v2", "source_provenance": provenance,
        "aggregation_note": (
            "Published reported sales in EUR million, without rescaling. "
            "A single-period total sums only selected product/product-family rows, not the "
            "whole Pharmaceuticals division; publisher rounding may affect reconciliation. "
            "No combined total across periods, years or overlapping annual/quarter/half-year "
            "figures. Comparative values retain each cited report version and restatements; "
            "no missing periods are inferred. Identity, approval and registry are simulated."
        ),
    }
