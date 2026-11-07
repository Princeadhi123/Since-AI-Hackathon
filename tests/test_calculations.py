"""Check the numerical contract independently of workflow and language models."""

import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from smart_librarian.reporting.calculations import compute_monthly

ROOT = Path(__file__).resolve().parents[1]


class CalculationTests(unittest.TestCase):
    def test_fixture_monthly_values_and_aggregate_ratio(self):
        path = ROOT / "data" / "demo_v1" / "demo.sqlite"
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        result = compute_monthly(
            path,
            product_ids=["DEMO-P-NUB"],
            market_ids=["DE"],
            months=["2026-01-01", "2026-02-01", "2026-03-01"],
            metric_ids=["DEMO-NET-SALES", "DEMO-FORECAST", "DEMO-VARIANCE-PCT"],
        )
        self.assertEqual(
            [r["DEMO-NET-SALES"] for r in result["rows"]], [107000, 109000, 111000]
        )
        self.assertEqual(
            [r["DEMO-FORECAST"] for r in result["rows"]], [111000, 112000, 113000]
        )
        self.assertEqual(result["totals"]["DEMO-NET-SALES"], 327000)
        self.assertEqual(result["totals"]["DEMO-FORECAST"], 336000)
        self.assertAlmostEqual(
            result["totals"]["DEMO-VARIANCE-PCT"], -9000 / 336000 * 100
        )
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_multi_scope_preserves_product_market_grain(self):
        result = compute_monthly(
            ROOT / "data" / "demo_v1" / "demo.sqlite",
            product_ids=["DEMO-P-NUB", "DEMO-P-KER"],
            market_ids=["DE", "FI"],
            months=["2026-01-01"],
            metric_ids=["DEMO-NET-SALES"],
        )
        self.assertEqual(len(result["rows"]), 4)
        self.assertEqual(result["source_row_count"], 4)
        self.assertEqual(
            result["totals"]["DEMO-NET-SALES"], 107000 + 116500 + 207500 + 217000
        )
        self.assertEqual(
            {r["product_id"] for r in result["rows"]}, {"DEMO-P-NUB", "DEMO-P-KER"}
        )
        self.assertEqual({r["market_id"] for r in result["rows"]}, {"DE", "FI"})

    def test_invalid_scope_and_metrics_fail_closed(self):
        arguments = {
            "product_ids": ["DEMO-P-NUB"], "market_ids": ["DE"],
            "months": ["2026-01-01"], "metric_ids": ["DEMO-NET-SALES"],
        }
        for replacement in [
            {"months": []},
            {"months": ["2026-01-02"]},
            {"months": ["2026-13-01"]},
            {"months": ["2026-12-01"]},
            {"months": ["2026-01-01", "2026-01-01"]},
            {"metric_ids": ["DEMO-GROSS-SALES"]},
            {"product_ids": ["' OR 1=1 --"]},
        ]:
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                compute_monthly(
                    ROOT / "data" / "demo_v1" / "demo.sqlite", **{
                        **arguments, **replacement
                    }
                )

    def test_zero_denominator_weighted_variance_and_duplicate_grain(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite"
            with closing(sqlite3.connect(path)) as connection:
                connection.executescript("""
                    CREATE TABLE products (product_id TEXT, product_name TEXT);
                    CREATE TABLE markets (market_id TEXT, market_name TEXT);
                    CREATE TABLE sales_monthly (
                        month TEXT, product_id TEXT, market_id TEXT,
                        net_sales_eur INTEGER, forecast_eur INTEGER, value_type TEXT
                    );
                    INSERT INTO products VALUES ('P', 'Synthetic');
                    INSERT INTO markets VALUES ('DE', 'Germany');
                    INSERT INTO sales_monthly VALUES
                        ('2026-01-01', 'P', 'DE', 100, 100, 'synthetic_actual'),
                        ('2026-02-01', 'P', 'DE', 300, 600, 'synthetic_actual'),
                        ('2026-03-01', 'P', 'DE', 50, 0, 'synthetic_actual'),
                        ('2026-01-01', 'P', 'DE', 99999, 1, 'synthetic_forecast');
                """)
                connection.commit()
            common = {"product_ids": ["P"], "market_ids": ["DE"],
                      "metric_ids": ["DEMO-VARIANCE-PCT"]}
            result = compute_monthly(
                path, months=["2026-01-01", "2026-02-01"], **common
            )
            self.assertAlmostEqual(result["totals"]["DEMO-VARIANCE-PCT"], -300 / 700 * 100)
            self.assertNotEqual(result["totals"]["DEMO-VARIANCE-PCT"], -25)
            zero = compute_monthly(path, months=["2026-03-01"], **common)
            self.assertIsNone(zero["rows"][0]["DEMO-VARIANCE-PCT"])
            self.assertIsNone(zero["totals"]["DEMO-VARIANCE-PCT"])
            with closing(sqlite3.connect(path)) as connection:
                connection.execute(
                    "INSERT INTO sales_monthly VALUES (?, ?, ?, ?, ?, ?)",
                    ("2026-01-01", "P", "DE", 1, 1, "synthetic_actual"),
                )
                connection.commit()
            with self.assertRaises(ValueError):
                compute_monthly(path, months=["2026-01-01"], **common)


if __name__ == "__main__":
    unittest.main()
