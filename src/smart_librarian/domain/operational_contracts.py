"""Fixed, fictional operational contracts, not executable catalog expressions."""

MONTHS = ["2026-01-01", "2026-02-01", "2026-03-01"]
DIMENSION_SCHEMA = {
    "products": {"product_id": "TEXT", "product_name": "TEXT"},
    "markets": {"market_id": "TEXT", "market_name": "TEXT", "currency": "TEXT"},
    "calendar": {"month": "TEXT", "year": "INTEGER", "month_number": "INTEGER"},
}

CONTRACTS = {
    "logistics": {
        "model_id": "DEMO-MODEL-LOGISTICS",
        "name": "Synthetic Distribution Performance",
        "owner_id": "DEMO-OWNER-LOGISTICS",
        "owner_name": "Synthetic Distribution Steward",
        "fact_table": "logistics_monthly",
        "entity_label": "Distribution lanes",
        "region_label": "Destination markets",
        "products": [("DEMO-L-COLD", "Cold Chain"), ("DEMO-L-STD", "Standard Freight")],
        "columns": ["delivered_orders", "on_time_orders", "lead_time_total_days"],
        "metrics": [
            {
                "metric_id": "DEMO-DELIVERED", "name": "Delivered Orders",
                "aliases": ["delivered orders", "deliveries"],
                "unit": "orders", "operator": "sum", "column": "delivered_orders",
                "definition": "SUM(delivered_orders)",
            },
            {
                "metric_id": "DEMO-ON-TIME-PCT", "name": "On Time Delivery %",
                "aliases": ["on time delivery", "on time delivery percent", "otd"],
                "unit": "percent", "operator": "ratio_of_sums",
                "numerator": "on_time_orders", "denominator": "delivered_orders",
                "factor": 100, "zero_denominator": "null",
                "definition": "100 * SUM(on_time_orders) / SUM(delivered_orders)",
            },
            {
                "metric_id": "DEMO-LEAD-DAYS", "name": "Average Lead Time",
                "aliases": ["average lead time", "lead time"],
                "unit": "days", "operator": "ratio_of_sums",
                "numerator": "lead_time_total_days", "denominator": "delivered_orders",
                "factor": 1, "zero_denominator": "null",
                "definition": "SUM(lead_time_total_days) / SUM(delivered_orders)",
            },
        ],
    },
    "quality": {
        "model_id": "DEMO-MODEL-QUALITY",
        "name": "Synthetic Manufacturing Quality",
        "owner_id": "DEMO-OWNER-QUALITY",
        "owner_name": "Synthetic Quality Steward",
        "fact_table": "quality_monthly",
        "entity_label": "Production lines",
        "region_label": "Plant regions",
        "products": [("DEMO-Q-TAB", "Tablet Line A"), ("DEMO-Q-PACK", "Packaging Line B")],
        "columns": ["inspected_units", "rejected_units", "batches"],
        "metrics": [
            {
                "metric_id": "DEMO-INSPECTED", "name": "Inspected Units",
                "aliases": ["inspected units", "inspections"],
                "unit": "units", "operator": "sum", "column": "inspected_units",
                "definition": "SUM(inspected_units)",
            },
            {
                "metric_id": "DEMO-REJECTED", "name": "Rejected Units",
                "aliases": ["rejected units", "rejects"],
                "unit": "units", "operator": "sum", "column": "rejected_units",
                "definition": "SUM(rejected_units)",
            },
            {
                "metric_id": "DEMO-REJECT-PCT", "name": "Rejection Rate %",
                "aliases": ["rejection rate", "defect rate", "rejection rate percent"],
                "unit": "percent", "operator": "ratio_of_sums",
                "numerator": "rejected_units", "denominator": "inspected_units",
                "factor": 100, "zero_denominator": "null",
                "definition": "100 * SUM(rejected_units) / SUM(inspected_units)",
            },
            {
                "metric_id": "DEMO-BATCHES", "name": "Batches Inspected",
                "aliases": ["batches inspected", "batches"],
                "unit": "batches", "operator": "sum", "column": "batches",
                "definition": "SUM(batches)",
            },
        ],
    },
}


def operational_schema(contract: dict) -> dict:
    return {
        **DIMENSION_SCHEMA,
        contract["fact_table"]: {
            "product_id": "TEXT", "market_id": "TEXT", "month": "TEXT",
            **{column: "INTEGER" for column in contract["columns"]},
            "value_type": "TEXT",
        },
    }


def operational_contract_gaps(catalog, domain_id: str) -> list[str]:
    """Match metadata exactly to a reviewed allowlisted implementation."""
    contract = CONTRACTS[domain_id]
    model = catalog.model()
    expected = {
        "model_id": contract["model_id"],
        "contract_version": "1.0.0",
        "fact_table": contract["fact_table"],
        "time_column": "month",
        "required_row_filter": {"value_type": "synthetic_actual"},
        "grain": ["product_id", "market_id", "month"],
        "schema": operational_schema(contract),
    }
    gaps = []
    if any(model.get(key) != value for key, value in expected.items()):
        gaps.append("model_contract_not_executable")
    expected_relations = {
        (contract["fact_table"], column, table, column, "many_to_one")
        for column, table in (
            ("product_id", "products"), ("market_id", "markets"), ("month", "calendar")
        )
    }
    relations = {
        tuple(edge.get(key) for key in (
            "from_table", "from_column", "to_table", "to_column", "cardinality"
        ))
        for edge in model.get("relationships", [])
    }
    if relations != expected_relations:
        gaps.append("model_relationships_not_executable")
    for expected_metric in contract["metrics"]:
        actual = catalog.metric(expected_metric["metric_id"]) or {}
        executable_keys = (
            "unit", "operator", "column", "numerator", "denominator", "factor",
            "zero_denominator", "definition",
        )
        if any(actual.get(key) != expected_metric.get(key) for key in executable_keys):
            gaps.append("metric_contract_not_executable:" + expected_metric["metric_id"])
    return gaps
