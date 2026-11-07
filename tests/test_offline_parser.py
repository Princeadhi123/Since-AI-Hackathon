"""Ordinary unit tests for the offline parser and metadata store.

These cover extraction mechanics only - no business numbers, no scenario
expected outcomes.
"""

import unittest
from pathlib import Path

from smart_librarian.catalog.store import DemoCatalog
from smart_librarian.domain import parser

ROOT = Path(__file__).resolve().parents[1]


class ParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = DemoCatalog(ROOT / "data" / "demo_v1")
        cls.choices = cls.catalog.choices()

    def parse(self, text):
        return parser.parse_message(text, self.choices, self.catalog)

    def test_complete_request_extracts_all_fields(self):
        result = self.parse(
            "Nubeqa Germany Net Sales January through March 2026"
        )
        self.assertEqual(result["product_ids"], ["DEMO-P-NUB"])
        self.assertEqual(result["market_ids"], ["DE"])
        self.assertEqual(result["metric_ids"], ["DEMO-NET-SALES"])
        self.assertEqual(
            result["months"], ["2026-01-01", "2026-02-01", "2026-03-01"]
        )
        self.assertEqual(result["grain"], "month")
        self.assertEqual(result["unresolved"], [])
        self.assertEqual(result["unsupported"], [])

    def test_vague_request_marks_everything_unresolved(self):
        result = self.parse("Show sales performance.")
        for field in ("product_ids", "market_ids", "metric_ids", "months"):
            self.assertIn(field, result["unresolved"])

    def test_draft_metric_is_flagged_not_selected(self):
        result = self.parse("Nubeqa Gross Sales Germany January 2026")
        self.assertNotIn("DEMO-GROSS-SALES", result["metric_ids"])
        self.assertTrue(result["unsupported"])

    def test_weekly_grain_is_flagged_not_pretended_monthly(self):
        result = self.parse("Weekly Nubeqa Net Sales Germany January 2026")
        self.assertTrue(any("weekly" in item for item in result["unsupported"]))
        # "Weekly" must not be silently treated as monthly grain.
        self.assertIsNone(result["grain"])

    def test_month_without_year_is_unresolved(self):
        result = self.parse("Nubeqa Germany Net Sales January")
        self.assertIn("months", result["unresolved"])
        self.assertEqual(result["months"], [])

    def test_quarter_expands_with_explicit_year(self):
        result = self.parse("Kerendia Finland Sales Forecast Q1 2026")
        self.assertEqual(
            result["months"], ["2026-01-01", "2026-02-01", "2026-03-01"]
        )

    def test_merge_retains_confirmed_fields(self):
        partial = {"product_ids": ["DEMO-P-NUB"], "market_ids": ["DE"]}
        merged = parser.merge_partial(
            partial, {"metric_ids": ["DEMO-NET-SALES"], "months": ["2026-01-01"]}
        )
        self.assertEqual(merged["product_ids"], ["DEMO-P-NUB"])
        self.assertEqual(merged["metric_ids"], ["DEMO-NET-SALES"])
        self.assertEqual(parser.missing_fields(merged), ["grain"])


class CatalogStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = DemoCatalog(ROOT / "data" / "demo_v1")

    def test_fingerprint_is_stable_sha256(self):
        fingerprint = self.catalog.fingerprint()
        self.assertEqual(len(fingerprint), 64)
        self.assertEqual(fingerprint, self.catalog.fingerprint())

    def test_choices_contain_no_business_values(self):
        text = str(self.catalog.choices())
        for banned in ("net_sales_eur", "107000", "sales_monthly"):
            self.assertNotIn(banned, text)

    def test_allowed_reports_filter_by_markets(self):
        fi_user = self.catalog.user("DEMO-USER-FI")
        global_user = self.catalog.user("DEMO-USER-GLOBAL")
        self.assertEqual(self.catalog.allowed_reports(fi_user), [])
        self.assertEqual(len(self.catalog.allowed_reports(global_user)), 1)


if __name__ == "__main__":
    unittest.main()
