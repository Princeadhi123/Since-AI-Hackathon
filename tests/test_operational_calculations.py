"""Independent numeric expectations for the lead-authored operational contracts."""

import importlib.util
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from smart_librarian.catalog.store import DemoCatalog
from smart_librarian.domain.operational_contracts import operational_contract_gaps
from smart_librarian.reporting.operational import compute_operational

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("operational_fixture_builder",
                                            ROOT / "create_operational_data.py")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class OperationalCalculationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for domain in ("logistics", "quality"):
            BUILDER.create_fixture(domain, self.root / domain)

    def tearDown(self):
        self.temp.cleanup()

    def calculate(self, domain, products=None, markets=None, months=None, metrics=None):
        defaults = {
            "logistics": (["DEMO-L-COLD"], [
                "DEMO-DELIVERED", "DEMO-ON-TIME-PCT", "DEMO-LEAD-DAYS"
            ]),
            "quality": (["DEMO-Q-TAB"], [
                "DEMO-INSPECTED", "DEMO-REJECTED", "DEMO-REJECT-PCT", "DEMO-BATCHES"
            ]),
        }
        return compute_operational(
            self.root / domain / "demo.sqlite", domain_id=domain,
            product_ids=products if products is not None else defaults[domain][0],
            market_ids=markets if markets is not None else ["DE"],
            months=months if months is not None else [
                "2026-01-01", "2026-02-01", "2026-03-01"
            ],
            metric_ids=metrics if metrics is not None else defaults[domain][1],
        )

    def mutate(self, domain, sql):
        with closing(sqlite3.connect(self.root / domain / "demo.sqlite")) as connection:
            connection.execute(sql)
            connection.commit()

    def test_logistics_counts_weighted_rate_and_lead_time(self):
        report = self.calculate("logistics")
        self.assertEqual(report["totals"]["DEMO-DELIVERED"], 300)
        self.assertAlmostEqual(report["totals"]["DEMO-ON-TIME-PCT"], 28000 / 300)
        self.assertAlmostEqual(report["totals"]["DEMO-LEAD-DAYS"], 800 / 300)
        self.assertEqual([row["DEMO-DELIVERED"] for row in report["rows"]], [100, 200, 0])
        self.assertEqual(report["rows"][0]["DEMO-ON-TIME-PCT"], 90)
        self.assertEqual(report["rows"][1]["DEMO-ON-TIME-PCT"], 95)
        self.assertIsNone(report["rows"][2]["DEMO-ON-TIME-PCT"])
        self.assertIsNone(report["rows"][2]["DEMO-LEAD-DAYS"])
        self.assertEqual(report["units"]["DEMO-LEAD-DAYS"], "days")
        self.assertEqual(report["source_row_count"], 3)

    def test_quality_counts_and_weighted_rejection_rate(self):
        report = self.calculate("quality")
        self.assertEqual(report["totals"]["DEMO-INSPECTED"], 4000)
        self.assertEqual(report["totals"]["DEMO-REJECTED"], 50)
        self.assertEqual(report["totals"]["DEMO-BATCHES"], 35)
        self.assertEqual(report["totals"]["DEMO-REJECT-PCT"], 1.25)
        self.assertEqual([row["DEMO-REJECT-PCT"] for row in report["rows"]],
                         [2.0, 1.0, None])

    def test_combined_scope_sums_counts_not_rates(self):
        logistics = self.calculate(
            "logistics", products=["DEMO-L-COLD", "DEMO-L-STD"], markets=["DE", "FI"]
        )
        self.assertEqual(logistics["source_row_count"], 12)
        self.assertEqual(logistics["totals"]["DEMO-DELIVERED"], 2340)
        self.assertAlmostEqual(logistics["totals"]["DEMO-ON-TIME-PCT"], 221300 / 2340)
        self.assertAlmostEqual(logistics["totals"]["DEMO-LEAD-DAYS"], 9630 / 2340)
        quality = self.calculate(
            "quality", products=["DEMO-Q-TAB", "DEMO-Q-PACK"], markets=["DE", "FI"]
        )
        self.assertEqual(quality["source_row_count"], 12)
        self.assertEqual(quality["totals"]["DEMO-INSPECTED"], 22000)
        self.assertEqual(quality["totals"]["DEMO-REJECTED"], 350)
        self.assertEqual(quality["totals"]["DEMO-BATCHES"], 215)
        self.assertAlmostEqual(quality["totals"]["DEMO-REJECT-PCT"], 35000 / 22000)

    def test_zero_denominator_total_is_null_not_zero(self):
        for domain, metric in (("logistics", "DEMO-ON-TIME-PCT"),
                               ("quality", "DEMO-REJECT-PCT")):
            with self.subTest(domain=domain):
                report = self.calculate(domain, months=["2026-03-01"])
                self.assertIsNone(report["totals"][metric])

    def test_unknown_duplicate_incomplete_scope_refused(self):
        for kwargs in (
            {"products": []}, {"markets": ["DE", "DE"]},
            {"products": ["UNKNOWN"]}, {"months": ["2026-04-01"]},
            {"months": ["2026-01-02"]}, {"metrics": ["DEMO-NET-SALES"]},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.calculate("logistics", **kwargs)
        self.mutate("quality", "DELETE FROM quality_monthly WHERE month='2026-02-01'")
        with self.assertRaisesRegex(ValueError, "Incomplete coverage"):
            self.calculate("quality")

    def test_invalid_facts_refused(self):
        self.mutate("logistics", "UPDATE logistics_monthly SET on_time_orders=9999")
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            self.calculate("logistics")
        self.mutate("quality", "UPDATE quality_monthly SET rejected_units=-1")
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            self.calculate("quality")

    def test_contract_drift_refused(self):
        for domain in ("logistics", "quality"):
            catalog = DemoCatalog(self.root / domain)
            self.assertEqual(operational_contract_gaps(catalog, domain), [])
            catalog.catalog["metrics"][0]["column"] = "invented_column"
            self.assertTrue(operational_contract_gaps(catalog, domain))


if __name__ == "__main__":
    unittest.main()
