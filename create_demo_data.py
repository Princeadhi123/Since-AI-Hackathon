"""Create an independent, explicitly synthetic executable demo fixture."""

import csv
import hashlib
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "data" / "demo_v1"
MODEL_ID = "DEMO-MODEL-SALES"
MONTHS = [f"2026-{month:02d}-01" for month in range(1, 10)]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main():
    # Fail rather than replace a fixture someone may already be using.
    OUTPUT.mkdir(exist_ok=False)
    products = [
        {"product_id": "DEMO-P-NUB", "product_name": "Nubeqa"},
        {"product_id": "DEMO-P-KER", "product_name": "Kerendia"},
    ]
    markets = [
        {"market_id": "DE", "market_name": "Germany", "currency": "EUR"},
        {"market_id": "FI", "market_name": "Finland", "currency": "EUR"},
        {"market_id": "FR", "market_name": "France", "currency": "EUR"},
    ]
    calendar = [{"month": month, "year": 2026, "month_number": i}
                for i, month in enumerate(MONTHS, 1)]
    facts = []
    for pi, product in enumerate(products, 1):
        for mi, market in enumerate(markets, 1):
            for month_number, month in enumerate(MONTHS, 1):
                forecast = 100000 * pi + 10000 * mi + 1000 * month_number
                # Integer EUR, no FX, and one explicitly actual-like row per key.
                variance_eur = (month_number - 5) * 1000 + (pi - mi) * 500
                facts.append({
                    "product_id": product["product_id"],
                    "market_id": market["market_id"],
                    "month": month,
                    "net_sales_eur": forecast + variance_eur,
                    "forecast_eur": forecast,
                    "value_type": "synthetic_actual",
                })
    owners = [{"owner_id": "DEMO-OWNER-001", "name": "Synthetic Sales Steward",
               "email": "sales-steward@synthetic.example", "status": "active"}]
    users = [
        {"user_id": "DEMO-USER-GLOBAL", "name": "Synthetic Global Analyst",
         "allowed_market_ids": ["DE", "FI", "FR"]},
        {"user_id": "DEMO-USER-FI", "name": "Synthetic Finland Analyst",
         "allowed_market_ids": ["FI"]},
    ]
    metrics = [
        {"metric_id": "DEMO-NET-SALES", "name": "Net Sales",
         "aliases": ["net revenue", "net sales"],
         "approval_status": "approved", "unit": "EUR",
         "operator": "sum", "column": "net_sales_eur"},
        {"metric_id": "DEMO-FORECAST", "name": "Sales Forecast",
         "aliases": ["forecast", "sales forecast"],
         "approval_status": "approved", "unit": "EUR",
         "operator": "sum", "column": "forecast_eur"},
        {"metric_id": "DEMO-VARIANCE-PCT", "name": "Sales vs Forecast %",
         "aliases": ["forecast variance", "sales variance percent"],
         "approval_status": "approved", "unit": "percent",
         "operator": "percent_difference_of_aggregates",
         "actual_metric_id": "DEMO-NET-SALES",
         "baseline_metric_id": "DEMO-FORECAST",
         "definition": "100 * (SUM(net_sales_eur) - SUM(forecast_eur)) / SUM(forecast_eur)",
         "zero_denominator": "null"},
        {"metric_id": "DEMO-GROSS-SALES", "name": "Gross Sales",
         "aliases": ["gross sales"], "approval_status": "draft", "unit": "EUR",
         "operator": None, "column": None,
         "unsupported_reason": "No gross-sales source column or approved calculation."},
    ]
    for metric in metrics:
        metric["owner_id"] = "DEMO-OWNER-001"
        metric["synthetic_record"] = True
    schema = {
        "products": {"product_id": "TEXT", "product_name": "TEXT"},
        "markets": {"market_id": "TEXT", "market_name": "TEXT", "currency": "TEXT"},
        "calendar": {"month": "TEXT", "year": "INTEGER", "month_number": "INTEGER"},
        "sales_monthly": {
            "product_id": "TEXT", "market_id": "TEXT", "month": "TEXT",
            "net_sales_eur": "INTEGER", "forecast_eur": "INTEGER", "value_type": "TEXT",
        },
    }
    primary_keys = {
        "products": ["product_id"], "markets": ["market_id"], "calendar": ["month"],
        "sales_monthly": ["product_id", "market_id", "month"],
    }
    relationships = [
        {"from_table": "sales_monthly", "from_column": column,
         "to_table": table, "to_column": column, "cardinality": "many_to_one"}
        for column, table in [("product_id", "products"), ("market_id", "markets"),
                              ("month", "calendar")]
    ]
    model = {
        "model_id": MODEL_ID, "name": "Synthetic Monthly Pharma Sales",
        "contract_version": "1.0.0", "owner_id": "DEMO-OWNER-001",
        "endorsement": "certified", "certification_is_simulated": True,
        "schema": schema, "primary_keys": primary_keys, "relationships": relationships,
        "fact_table": "sales_monthly",
        "grain": ["product_id", "market_id", "month"],
        "supported_grains": ["month"], "time_column": "month",
        "time_semantics": "Calendar month start, no intraday timestamps.",
        "coverage": {"product_ids": [p["product_id"] for p in products],
                     "market_ids": [m["market_id"] for m in markets],
                     "months": MONTHS},
        "supported_metric_ids": ["DEMO-NET-SALES", "DEMO-FORECAST", "DEMO-VARIANCE-PCT"],
        "required_row_filter": {"value_type": "synthetic_actual"},
        "amount_semantics": "Integer EUR; no currency conversion; all values fictional.",
        "forecast_semantics": "One fictional forecast paired with each actual-like row.",
        "snapshot_as_of": "2026-11-06T00:00:00Z",
        "last_successful_refresh_at": "2026-11-05T12:00:00Z",
        "refresh_status": "healthy", "refresh_is_simulated": True,
    }
    reports = [{
        "asset_id": "DEMO-REPORT-NUB-DE", "name": "Nubeqa Germany Monthly Net Sales",
        "model_id": MODEL_ID, "owner_id": "DEMO-OWNER-001",
        "metric_ids": ["DEMO-NET-SALES"],
        "coverage": {"product_ids": ["DEMO-P-NUB"], "market_ids": ["DE"], "months": MONTHS},
        "grain": "month", "endorsement": "certified", "lifecycle_status": "active",
        "monthly_views": 42, "usage_is_simulated": True,
        "destination": {"kind": "local_preview_reference", "route": None,
                        "implemented": False, "mock": True},
    }]
    lineage = [{"source_id": MODEL_ID, "target_id": reports[0]["asset_id"],
                "relationship": "model_to_report", "synthetic_record": True}]
    policy = {
        "scope": "Synthetic demo only; not Bayer policy or production authorization.",
        "default_access": "deny",
        "access_rule": "All requested markets must be listed in the selected user's allowed_market_ids.",
        "metric_rule": "Every requested metric must be approved and supported by the model.",
        "reuse_rule": "Exact metric, product, market, month and grain coverage required.",
        "scope_rule": "Never silently broaden or narrow the confirmed request.",
        "change_rule": "Extension/new-build requires explicit approval bound to specification hash.",
        "uncertainty_rule": "Unresolved intent or missing trust evidence requires clarification/review.",
        "notes": "Contract describes intended application behavior; no authorization engine is implemented.",
    }
    tables = {"products": products, "markets": markets, "calendar": calendar,
              "sales_monthly": facts}
    for name, rows in tables.items():
        with (OUTPUT / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(schema[name]))
            writer.writeheader()
            writer.writerows(rows)
    with sqlite3.connect(OUTPUT / "demo.sqlite") as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for name, columns in schema.items():
            definitions = [f'"{col}" {kind} NOT NULL' for col, kind in columns.items()]
            definitions.append("PRIMARY KEY (" + ", ".join(f'"{k}"' for k in primary_keys[name]) + ")")
            if name == "sales_monthly":
                definitions.extend(
                    f'FOREIGN KEY ("{r["from_column"]}") REFERENCES "{r["to_table"]}" ("{r["to_column"]}")'
                    for r in relationships
                )
            connection.execute(f'CREATE TABLE "{name}" ({", ".join(definitions)})')
            placeholders = ", ".join("?" for _ in columns)
            connection.executemany(
                f'INSERT INTO "{name}" VALUES ({placeholders})',
                [[row[col] for col in columns] for row in tables[name]],
            )
    write_json(OUTPUT / "catalog.json", {
        "dataset_id": "smart-librarian-demo-v1", "synthetic_record": True,
        "owners": owners, "users": users, "metrics": metrics,
        "models": [model], "reports": reports, "lineage": lineage, "policy": policy,
    })
    write_json(OUTPUT / "provenance.json", {
        "classification": "Entirely synthetic, author-created demo extension.",
        "relationship_to_organizer_pack": "Independent fixture; no organizer records modified or reclassified.",
        "product_names": "Public-context names only; every financial and governance value is invented.",
        "generator": "create_demo_data.py", "version": "1.0.0",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "warning": "Not real Bayer sales, permissions, approvals, certification or usage.",
    })
    write_json(OUTPUT / "approval_events.json", [])
    write_json(OUTPUT / "audit_events.json", [])
    write_json(OUTPUT / "manifest.json", {
        "dataset_id": "smart-librarian-demo-v1", "version": "1.0.0",
        "synthetic_record": True,
        "tables": {name: {"rows": len(rows), "columns": schema[name]}
                   for name, rows in tables.items()},
        "files": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in sorted(OUTPUT.iterdir()) if path.is_file()},
    })
    print(f"Created {OUTPUT}")
    print(f"{len(facts)} fictional monthly fact rows; catalog and semantic contracts written.")


if __name__ == "__main__":
    main()
