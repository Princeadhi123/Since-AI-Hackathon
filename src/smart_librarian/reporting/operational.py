"""Allowlisted calculations for fictional distribution and quality facts."""

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from smart_librarian.domain.operational_contracts import CONTRACTS
from smart_librarian.reporting.calculations import _selection


def _metric_values(domain_id, amounts, metric_ids):
    # Definitions come from reviewed code, never from catalog or LLM expressions.
    contract = CONTRACTS[domain_id]
    values = {}
    for metric in contract["metrics"]:
        identifier = metric["metric_id"]
        if identifier not in metric_ids:
            continue
        if metric["operator"] == "sum":
            values[identifier] = amounts[metric["column"]]
        else:
            denominator = amounts[metric["denominator"]]
            values[identifier] = (
                metric["factor"] * amounts[metric["numerator"]] / denominator
                if denominator else None
            )
    return values


def compute_operational(database_path: Path, *, domain_id: str, product_ids: list[str],
                        market_ids: list[str], months: list[str],
                        metric_ids: list[str]) -> dict:
    if domain_id not in CONTRACTS:
        raise ValueError("Unknown operational calculation contract.")
    contract = CONTRACTS[domain_id]
    products = _selection(product_ids, "product_ids")
    markets = _selection(market_ids, "market_ids")
    periods = _selection(months, "months")
    metrics = _selection(metric_ids, "metric_ids")
    if not set(metrics).issubset(m["metric_id"] for m in contract["metrics"]):
        raise ValueError("Unsupported calculation requested.")
    for month in periods:
        try:
            parsed = date.fromisoformat(month)
            if parsed.day != 1 or parsed.isoformat() != month:
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("Months must be ISO calendar-month starts.") from None
    placeholders = lambda values: ", ".join("?" for _ in values)
    columns = contract["columns"]
    selections = ", ".join(f"SUM(s.{column}) AS {column}" for column in columns)
    # Identifiers are hardcoded above; every scope value remains parameterized.
    query = f"""
        SELECT s.month, s.product_id, p.product_name, s.market_id, m.market_name,
               {selections}, COUNT(*) AS source_rows
        FROM {contract["fact_table"]} AS s
        JOIN products AS p ON p.product_id = s.product_id
        JOIN markets AS m ON m.market_id = s.market_id
        WHERE s.value_type = ?
          AND s.product_id IN ({placeholders(products)})
          AND s.market_id IN ({placeholders(markets)})
          AND s.month IN ({placeholders(periods)})
        GROUP BY s.month, s.product_id, p.product_name, s.market_id, m.market_name
        ORDER BY s.month, s.product_id, s.market_id
    """
    uri = Path(database_path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.execute("PRAGMA query_only = ON")
        connection.row_factory = sqlite3.Row
        records = connection.execute(
            query, ["synthetic_actual", *products, *markets, *periods]
        ).fetchall()
    expected = {(month, product, market)
                for month in periods for product in products for market in markets}
    actual = {(r["month"], r["product_id"], r["market_id"]) for r in records}
    if expected != actual or any(row["source_rows"] != 1 for row in records):
        raise ValueError("Incomplete coverage or duplicate facts: cannot render this scope.")
    for record in records:
        if any(not isinstance(record[column], int) or record[column] < 0 for column in columns):
            raise ValueError("Operational contract requires nonnegative integer facts.")
        if domain_id == "logistics":
            if record["on_time_orders"] > record["delivered_orders"]:
                raise ValueError("On-time orders cannot exceed delivered orders.")
            if record["delivered_orders"] == 0 and record["lead_time_total_days"] != 0:
                raise ValueError("Lead time requires delivered orders.")
        elif record["rejected_units"] > record["inspected_units"]:
            raise ValueError("Rejected units cannot exceed inspected units.")
    rows = []
    for record in records:
        row = {key: record[key] for key in (
            "month", "product_id", "product_name", "market_id", "market_name"
        )}
        row.update(_metric_values(domain_id, record, metrics))
        rows.append(row)
    aggregate = {column: sum(record[column] for record in records) for column in columns}
    return {
        "rows": rows, "totals": _metric_values(domain_id, aggregate, metrics),
        "units": {m["metric_id"]: m["unit"] for m in contract["metrics"]
                  if m["metric_id"] in metrics},
        "grain": ["month", "product_id", "market_id"],
        "source_row_count": len(records), "synthetic_record": True,
        "calculation_version": f"demo-{domain_id}-monthly-v1",
        "aggregation_note": (
            "Counts sum across the confirmed scope. Rates and average lead time "
            "use ratios of aggregate counts, never averages of row rates. "
            "A zero denominator yields null. Entirely fictional demonstration data."
        ),
    }
