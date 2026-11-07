"""Ensure catalog claims match the fixed executable calculation implementation."""

from smart_librarian.domain.operational_contracts import (
    operational_contract_gaps,
)

_OPERATIONAL_DOMAINS = {
    "DEMO-MODEL-LOGISTICS": "logistics",
    "DEMO-MODEL-QUALITY": "quality",
}

_AMOUNTS = {
    "DEMO-NET-SALES": "net_sales_eur",
    "DEMO-FORECAST": "forecast_eur",
}
_SCHEMA = {
    "products": {"product_id": "TEXT", "product_name": "TEXT"},
    "markets": {"market_id": "TEXT", "market_name": "TEXT", "currency": "TEXT"},
    "calendar": {"month": "TEXT", "year": "INTEGER", "month_number": "INTEGER"},
    "sales_monthly": {
        "product_id": "TEXT", "market_id": "TEXT", "month": "TEXT",
        "net_sales_eur": "INTEGER", "forecast_eur": "INTEGER", "value_type": "TEXT",
    },
}


def calculation_contract_gaps(catalog) -> list[str]:
    """Fail closed when a new catalog needs a different executable adapter."""
    model = catalog.model()
    if model.get("model_id") == "PUBLIC-MODEL-FINANCIALS":
        from smart_librarian.domain.public_financials import (
            financial_contract_gaps,
        )
        return financial_contract_gaps(catalog)
    if model.get("model_id") == "PUBLIC-MODEL-ANNUAL":
        from smart_librarian.domain.public_annual import (
            public_contract_gaps,
        )
        return public_contract_gaps(catalog)
    domain_id = _OPERATIONAL_DOMAINS.get(model.get("model_id"))
    if domain_id is not None:
        return operational_contract_gaps(catalog, domain_id)
    gaps = []
    if (
        model.get("model_id") != "DEMO-MODEL-SALES"
        or model.get("contract_version") != "1.0.0"
        or model.get("fact_table") != "sales_monthly"
        or model.get("time_column") != "month"
        or model.get("required_row_filter") != {"value_type": "synthetic_actual"}
        or model.get("grain") != ["product_id", "market_id", "month"]
        or model.get("schema") != _SCHEMA
    ):
        gaps.append("model_contract_not_executable")
    expected_relations = {
        ("sales_monthly", "product_id", "products", "product_id", "many_to_one"),
        ("sales_monthly", "market_id", "markets", "market_id", "many_to_one"),
        ("sales_monthly", "month", "calendar", "month", "many_to_one"),
    }
    relations = {
        tuple(edge.get(key) for key in (
            "from_table", "from_column", "to_table", "to_column", "cardinality"
        ))
        for edge in model.get("relationships", [])
    }
    if relations != expected_relations:
        gaps.append("model_relationships_not_executable")
    for metric_id, column in _AMOUNTS.items():
        metric = catalog.metric(metric_id) or {}
        if (
            metric.get("operator") != "sum"
            or metric.get("column") != column
            or metric.get("unit") != "EUR"
        ):
            gaps.append(f"metric_contract_not_executable:{metric_id}")
    variance = catalog.metric("DEMO-VARIANCE-PCT") or {}
    if (
        variance.get("operator") != "percent_difference_of_aggregates"
        or variance.get("actual_metric_id") != "DEMO-NET-SALES"
        or variance.get("baseline_metric_id") != "DEMO-FORECAST"
        or variance.get("unit") != "percent"
        or variance.get("zero_denominator") != "null"
        or variance.get("definition") != (
            "100 * (SUM(net_sales_eur) - SUM(forecast_eur)) / SUM(forecast_eur)"
        )
    ):
        gaps.append("metric_contract_not_executable:DEMO-VARIANCE-PCT")
    return gaps
