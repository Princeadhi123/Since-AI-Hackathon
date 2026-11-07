import copy
import json
import tempfile
import unittest
from pathlib import Path

from smart_librarian.catalog.public_annual import PublicAnnualCatalog
from smart_librarian.catalog.store import SnapshotDrift
from smart_librarian.domain.public_annual import (
    parse_public_message,
    public_contract_gaps,
    public_scope_gaps,
)
from smart_librarian.reporting.public_annual import (
    METRIC_ID,
    PRODUCT_IDS,
    compute_public_annual,
)

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    ("Nubeqa", 2024): 1523, ("Nubeqa", 2025): 2385,
    ("Kerendia", 2024): 463, ("Kerendia", 2025): 829,
    ("Eylea", 2024): 3306, ("Eylea", 2025): 3110,
    ("Xarelto", 2024): 3480, ("Xarelto", 2025): 2344,
}


class PublicAnnualContractTests(unittest.TestCase):
    def setUp(self):
        self.catalog = PublicAnnualCatalog()
        self.source = self.catalog.public_evidence
        self.intent = {
            "product_ids": ["PUBLIC-NUBEQA"], "market_ids": ["GLOBAL"],
            "months": ["2025"], "metric_ids": [METRIC_ID], "grain": "year",
        }

    def compute(self, source=None, **overrides):
        intent = {**self.intent, **overrides}
        intent.pop("grain")
        return compute_public_annual(source or self.source, **intent)

    def test_each_published_product_year_is_copied_without_rescaling(self):
        for (name, year), amount in EXPECTED.items():
            with self.subTest(product=name, year=year):
                report = self.compute(product_ids=[PRODUCT_IDS[name]], months=[str(year)])
                self.assertEqual(report["rows"][0][METRIC_ID], amount)
                self.assertEqual(report["totals"], {METRIC_ID: amount})
                self.assertEqual(report["units"], {METRIC_ID: "EUR million"})
                self.assertEqual(report["rows"][0]["fiscal_year"], year)
                self.assertNotIn("month", report["rows"][0])
                self.assertFalse(report["synthetic_record"])
                self.assertEqual(report["data_classification"], "public_reported_actual")

    def test_selected_product_totals_only_within_one_year(self):
        for year, expected in (("2024", 8772), ("2025", 8668)):
            report = self.compute(product_ids=list(PRODUCT_IDS.values()), months=[year])
            self.assertEqual(report["totals"], {METRIC_ID: expected})
            self.assertIn("not the full", report["aggregation_note"])

    def test_comparison_never_combines_fiscal_years_into_one_total(self):
        report = self.compute(product_ids=list(PRODUCT_IDS.values()), months=["2024", "2025"])
        self.assertEqual(report["totals"], {})
        self.assertEqual(report["source_row_count"], 8)
        self.assertEqual(
            {(r["product_name"], r["fiscal_year"]): r[METRIC_ID] for r in report["rows"]},
            EXPECTED,
        )
        self.assertEqual(report["time_column"], "fiscal_year")

    def test_invalid_scope_or_metric_is_not_silently_changed(self):
        for override in (
            {"months": ["2025-01-01"]}, {"months": ["2026"]},
            {"months": ["2025", "2025"]}, {"months": []},
            {"market_ids": ["DE"]}, {"market_ids": ["GLOBAL", "DE"]},
            {"metric_ids": ["DEMO-FORECAST"]},
            {"product_ids": ["PUBLIC-UNKNOWN"]},
        ):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.compute(**override)

    def test_duplicate_missing_and_invalid_facts_fail_closed(self):
        variants = []
        duplicate = copy.deepcopy(self.source)
        duplicate["rows"].append(copy.deepcopy(duplicate["rows"][0]))
        variants.append(duplicate)
        missing = copy.deepcopy(self.source)
        missing["rows"].pop()
        variants.append(missing)
        for value in (True, "2385", 2385.5, -1, None):
            invalid = copy.deepcopy(self.source)
            invalid["rows"][0]["sales_eur_million"] = value
            variants.append(invalid)
        for source in variants:
            with self.subTest(rows=len(source["rows"])), self.assertRaises(ValueError):
                self.compute(source=source)

    def test_source_unit_classification_and_references_are_required(self):
        for key, value in (("unit", "EUR"), ("data_classification", "synthetic")):
            invalid = copy.deepcopy(self.source)
            invalid[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.compute(source=invalid)
        invalid = copy.deepcopy(self.source)
        del invalid["rows"][0]["source_table"]
        with self.assertRaises(ValueError):
            self.compute(source=invalid)

    def test_catalog_exposes_real_classification_and_annual_metadata_only(self):
        choices = self.catalog.choices()
        self.assertFalse(choices["synthetic_record"])
        self.assertEqual(choices["months"], ["2024", "2025"])
        self.assertEqual(choices["grain_options"], ["year"])
        self.assertEqual(choices["period_label"], "Fiscal years")
        self.assertNotIn("sales_eur_million", json.dumps(choices))
        self.assertEqual(public_contract_gaps(self.catalog), [])
        self.assertEqual(public_scope_gaps(self.catalog.model(), self.intent), [])
        self.assertFalse(self.catalog.reports())

    def test_source_drift_invalidates_loaded_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "public.json"
            path.write_text(json.dumps(self.source), encoding="utf-8")
            catalog = PublicAnnualCatalog(path)
            changed = copy.deepcopy(self.source)
            changed["rows"][0]["sales_eur_million"] += 1
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(SnapshotDrift):
                catalog.assert_current()

    def test_metric_contract_tampering_is_not_executable(self):
        self.catalog.catalog["metrics"][0]["unit"] = "EUR"
        self.assertIn(
            "public_annual_metric_contract_not_executable", public_contract_gaps(self.catalog)
        )

    def test_explicit_request_extracts_correct_fiscal_year_and_real_metric(self):
        result = parse_public_message(
            "Show global reported sales for Nubeqa in 2025",
            self.catalog.choices(), self.catalog,
        )
        self.assertEqual(result["product_ids"], ["PUBLIC-NUBEQA"])
        self.assertEqual(result["market_ids"], ["GLOBAL"])
        self.assertEqual(result["months"], ["2025"])
        self.assertEqual(result["metric_ids"], [METRIC_ID])
        self.assertEqual(result["grain"], "year")
        self.assertEqual(result["unsupported"], [])
        self.assertEqual(result["unresolved"], [])

    def test_comparison_and_out_of_coverage_years_remain_explicit(self):
        for text, years in (
            ("Compare all four products global sales in 2024 and 2025", ["2024", "2025"]),
            ("All products global sales 2024 through 2026", ["2024", "2025", "2026"]),
        ):
            result = parse_public_message(text, self.catalog.choices(), self.catalog)
            self.assertEqual(result["months"], years)
            self.assertEqual(set(result["product_ids"]), set(PRODUCT_IDS.values()))

    def test_unsupported_subannual_forecast_or_country_is_flagged(self):
        for text in (
            "Global Nubeqa monthly sales January 2025",
            "Global Nubeqa forecast sales 2025",
            "Global Nubeqa Germany sales 2025",
            "Global Nubeqa quarterly sales Q1 2025",
        ):
            with self.subTest(text=text):
                result = parse_public_message(text, self.catalog.choices(), self.catalog)
                self.assertTrue(result["unsupported"])

    def test_absent_scope_and_year_are_not_fabricated(self):
        result = parse_public_message("Nubeqa sales", self.catalog.choices(), self.catalog)
        self.assertEqual(result["market_ids"], [])
        self.assertEqual(result["months"], [])
        self.assertIn("market_ids", result["unresolved"])
        self.assertIn("months", result["unresolved"])


if __name__ == "__main__":
    unittest.main()
