"""Fixed demo calculations. Authorization belongs to the calling workflow."""

import calendar
import sqlite3
from contextlib import closing
from pathlib import Path

SUPPORTED_METRICS = ("DEMO-NET-SALES", "DEMO-FORECAST", "DEMO-VARIANCE-PCT")


def _selection(values, name):
    if not values or len(values) > 100:
        raise ValueError(f"{name} must contain between 1 and 100 unique values.")
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError(f"{name} must contain nonempty strings.")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} contains duplicate selections.")
    return sorted(values)


def _values(actual, forecast, metric_ids):
    available = {
        "DEMO-NET-SALES": actual,
        "DEMO-FORECAST": forecast,
        "DEMO-VARIANCE-PCT": (
            100.0 * (actual - forecast) / forecast if forecast != 0 else None
        ),
    }
    return {metric: available[metric] for metric in metric_ids}


def compute_monthly(
    database_path: Path,
    *,
    product_ids: list[str],
    market_ids: list[str],
    months: list[str],
    metric_ids: list[str],
) -> dict:
    """Return full-grain rows and selection totals, never averaging percentages.

    This is an allowlisted executable implementation of the demo contract, not
    an interpreter for SQL, formula text, or LLM-produced expressions.
    """
    products = _selection(product_ids, "product_ids")
    markets = _selection(market_ids, "market_ids")
    selected_months = _selection(months, "months")
    metrics = _selection(metric_ids, "metric_ids")
    if not set(metrics).issubset(SUPPORTED_METRICS):
        raise ValueError("Unsupported calculation requested.")
    for month in selected_months:
        try:
            year, number, day = map(int, month.split("-"))
            calendar.monthrange(year, number)
            if day != 1 or month != f"{year:04d}-{number:02d}-01":
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("Months must be ISO calendar-month starts.") from None

    def placeholders(values):
        return ", ".join("?" for _ in values)

    query = f"""
        SELECT s.month, s.product_id, p.product_name, s.market_id, m.market_name,
               SUM(s.net_sales_eur) AS actual,
               SUM(s.forecast_eur) AS forecast,
               COUNT(*) AS source_rows
        FROM sales_monthly AS s
        JOIN products AS p ON p.product_id = s.product_id
        JOIN markets AS m ON m.market_id = s.market_id
        WHERE s.value_type = ?
          AND s.product_id IN ({placeholders(products)})
          AND s.market_id IN ({placeholders(markets)})
          AND s.month IN ({placeholders(selected_months)})
        GROUP BY s.month, s.product_id, p.product_name, s.market_id, m.market_name
        ORDER BY s.month, s.product_id, s.market_id
    """
    database_uri = Path(database_path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(database_uri, uri=True)) as connection:
        connection.execute("PRAGMA query_only = ON")
        connection.row_factory = sqlite3.Row
        records = connection.execute(
            query, ["synthetic_actual", *products, *markets, *selected_months]
        ).fetchall()
    expected_keys = {
        (month, product, market)
        for month in selected_months
        for product in products
        for market in markets
    }
    actual_keys = {(r["month"], r["product_id"], r["market_id"]) for r in records}
    if actual_keys != expected_keys or any(r["source_rows"] != 1 for r in records):
        raise ValueError("Incomplete coverage or duplicate facts: cannot render this scope.")
    if any(
        not isinstance(r["actual"], int) or not isinstance(r["forecast"], int)
        for r in records
    ):
        raise ValueError("Demo contract requires integer EUR amounts.")

    rows = []
    for record in records:
        row = {key: record[key] for key in (
            "month", "product_id", "product_name", "market_id", "market_name"
        )}
        row.update(_values(record["actual"], record["forecast"], metrics))
        rows.append(row)
    total_actual = sum(record["actual"] for record in records)
    total_forecast = sum(record["forecast"] for record in records)
    return {
        "rows": rows,
        "totals": _values(total_actual, total_forecast, metrics),
        "units": {metric: "percent" if metric == "DEMO-VARIANCE-PCT" else "EUR"
                  for metric in metrics},
        "grain": ["month", "product_id", "market_id"],
        "source_row_count": len(records),
        "synthetic_record": True,
        "calculation_version": "demo-monthly-v1",
        "aggregation_note": (
            "Amounts sum across the confirmed scope; variance is calculated from "
            "aggregate amounts, not an average of row percentages. Zero forecast yields null."
        ),
    }
