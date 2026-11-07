"""Create two independent fictional fixtures; never overwrite existing data."""

import csv
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from smart_librarian.domain.operational_contracts import (  # noqa: E402
    CONTRACTS,
    MONTHS,
    operational_schema,
)

# Rows: entity index, region code, month index, then the three contract facts.
# Unequal denominators intentionally make averages of percentages incorrect.
FACTS = {
    "logistics": [
        (0, "DE", 0, 100, 90, 300), (0, "DE", 1, 200, 190, 500),
        (0, "DE", 2, 0, 0, 0), (0, "FI", 0, 80, 72, 320),
        (0, "FI", 1, 120, 114, 420), (0, "FI", 2, 100, 98, 300),
        (1, "DE", 0, 300, 270, 1500), (1, "DE", 1, 400, 380, 1600),
        (1, "DE", 2, 500, 490, 1750), (1, "FI", 0, 150, 135, 900),
        (1, "FI", 1, 180, 171, 990), (1, "FI", 2, 210, 203, 1050),
    ],
    "quality": [
        (0, "DE", 0, 1000, 20, 10), (0, "DE", 1, 3000, 30, 25),
        (0, "DE", 2, 0, 0, 0), (0, "FI", 0, 1200, 24, 12),
        (0, "FI", 1, 1500, 15, 15), (0, "FI", 2, 1800, 9, 18),
        (1, "DE", 0, 2000, 60, 20), (1, "DE", 1, 2500, 50, 25),
        (1, "DE", 2, 3000, 30, 30), (1, "FI", 0, 1600, 48, 16),
        (1, "FI", 1, 2000, 40, 20), (1, "FI", 2, 2400, 24, 24),
    ],
}


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


def create_fixture(domain_id: str, directory: Path):
    contract = CONTRACTS[domain_id]
    directory.mkdir(parents=True, exist_ok=False)
    products = contract["products"]
    markets = [("DE", "Germany", "N/A"), ("FI", "Finland", "N/A")]
    calendar = [(month, 2026, index + 1) for index, month in enumerate(MONTHS)]
    write_csv(directory / "products.csv", ["product_id", "product_name"], products)
    write_csv(directory / "markets.csv", ["market_id", "market_name", "currency"], markets)
    write_csv(directory / "calendar.csv", ["month", "year", "month_number"], calendar)
    schema = operational_schema(contract)
    connection = sqlite3.connect(directory / "demo.sqlite")
    try:
        for table, columns in schema.items():
            definitions = ", ".join(f"{name} {kind} NOT NULL" for name, kind in columns.items())
            key = (
                "product_id, market_id, month" if table == contract["fact_table"]
                else next(iter(columns))
            )
            connection.execute(f"CREATE TABLE {table} ({definitions}, PRIMARY KEY ({key}))")
        connection.executemany("INSERT INTO products VALUES (?, ?)", products)
        connection.executemany("INSERT INTO markets VALUES (?, ?, ?)", markets)
        connection.executemany("INSERT INTO calendar VALUES (?, ?, ?)", calendar)
        facts = [
            (products[entity][0], market, MONTHS[month], *amounts, "synthetic_actual")
            for entity, market, month, *amounts in FACTS[domain_id]
        ]
        connection.executemany(
            f"INSERT INTO {contract['fact_table']} VALUES (?, ?, ?, ?, ?, ?, ?)", facts
        )
        connection.commit()
    finally:
        connection.close()
    owner_id = contract["owner_id"]
    model = {
        "model_id": contract["model_id"], "name": contract["name"],
        "contract_version": "1.0.0", "domain_id": domain_id, "owner_id": owner_id,
        "endorsement": "certified", "certification_is_simulated": True,
        "schema": schema, "grain": ["product_id", "market_id", "month"],
        "fact_table": contract["fact_table"], "time_column": "month",
        "supported_grains": ["month"],
        "required_row_filter": {"value_type": "synthetic_actual"},
        "coverage": {
            "product_ids": [item[0] for item in products],
            "market_ids": ["DE", "FI"], "months": MONTHS,
        },
        "supported_metric_ids": [m["metric_id"] for m in contract["metrics"]],
        "relationships": [
            {
                "from_table": contract["fact_table"], "from_column": column,
                "to_table": table, "to_column": column, "cardinality": "many_to_one",
            }
            for column, table in (
                ("product_id", "products"), ("market_id", "markets"), ("month", "calendar")
            )
        ],
        "snapshot_as_of": "2026-11-06T00:00:00Z", "refresh_status": "healthy",
        "refresh_is_simulated": True,
    }
    catalog = {
        "dataset_id": f"smart-librarian-{domain_id}-v1", "domain_id": domain_id,
        "synthetic_record": True,
        "dimension_labels": {
            "products": contract["entity_label"], "markets": contract["region_label"]
        },
        "owners": [{"owner_id": owner_id, "name": contract["owner_name"], "status": "active"}],
        "users": [
            {"user_id": "DEMO-USER-GLOBAL", "name": "Synthetic Global Analyst",
             "allowed_market_ids": ["DE", "FI"]},
            {"user_id": "DEMO-USER-FI", "name": "Synthetic Finland Analyst",
             "allowed_market_ids": ["FI"]},
        ],
        "metrics": [
            {**metric, "owner_id": owner_id, "approval_status": "approved",
             "synthetic_record": True} for metric in contract["metrics"]
        ],
        "models": [model], "reports": [], "lineage": [],
    }
    (directory / "catalog.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    (directory / "provenance.json").write_text(json.dumps({
        "synthetic_record": True,
        "source": "Explicit fictional rows in create_operational_data.py; no Bayer values.",
        "grain": ["product_id", "market_id", "month"],
        "rows": len(FACTS[domain_id]),
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    for identifier in CONTRACTS:
        target = ROOT / "data" / f"demo_{identifier}_v1"
        if target.exists():
            print(f"Preserving existing fixture: {target}")
        else:
            create_fixture(identifier, target)
            print(f"Created fictional fixture: {target}")
