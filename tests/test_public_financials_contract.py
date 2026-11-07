import copy
import json
import tempfile
import unittest
from pathlib import Path

from smart_librarian.catalog.public_financials import PublicFinancialCatalog
from smart_librarian.catalog.store import CatalogError, SnapshotDrift
from smart_librarian.domain.public_financials import (
    financial_contract_gaps,
    financial_scope_gaps,
    parse_financial_message,
)
from smart_librarian.reporting.public_financials import (
    METRIC_ID,
    PERIOD_KINDS,
    PRODUCT_IDS,
    compute_public_financials,
    validate_snapshot,
)


class PublicFinancialContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = PublicFinancialCatalog()
        cls.snapshot = cls.catalog.financial_snapshot()

    def compute(self, source=None, **changes):
        selection = {
            "product_ids": ["PUBLIC-NUBEQA"], "market_ids": ["GLOBAL"],
            "months": ["2025"], "metric_ids": [METRIC_ID], "grain": "year",
        } | changes
        return compute_public_financials(
            self.snapshot if source is None else source, **selection
        )

    def test_reviewed_source_coverage_is_complete_and_unique(self):
        self.assertEqual(len(self.snapshot["rows"]), 150)
        self.assertEqual(len(self.snapshot["sources"]), 3)
        self.assertEqual(
            {(r["product_id"], r["period"]) for r in self.snapshot["rows"]},
            {(p, t) for p in PRODUCT_IDS.values() for t in PERIOD_KINDS},
        )
        validate_snapshot(self.snapshot)

    def test_published_values_copied_without_rescaling_or_period_derivation(self):
        expected = {
            ("PUBLIC-NUBEQA", "2024"): 1523,
            ("PUBLIC-NUBEQA", "2025"): 2385,
            ("PUBLIC-NUBEQA", "2024-Q4"): 443,
            ("PUBLIC-NUBEQA", "2025-Q4"): 702,
            ("PUBLIC-NUBEQA", "2025-Q1"): 515,
            ("PUBLIC-NUBEQA", "2026-Q1"): 749,
            ("PUBLIC-NUBEQA", "2025-Q2"): 546,
            ("PUBLIC-NUBEQA", "2026-Q2"): 880,
            ("PUBLIC-NUBEQA", "2025-H1"): 1061,
            ("PUBLIC-NUBEQA", "2026-H1"): 1629,
            ("PUBLIC-KERENDIA", "2026-Q1"): 274,
            ("PUBLIC-KERENDIA", "2026-Q2"): 329,
            ("PUBLIC-KERENDIA", "2026-H1"): 603,
            ("PUBLIC-ULTRAVIST", "2025-Q1"): 132,
            ("PUBLIC-ULTRAVIST", "2025-Q2"): 144,
            ("PUBLIC-ULTRAVIST", "2025-H1"): 278,
        }
        for (product, period), amount in expected.items():
            with self.subTest(product=product, period=period):
                report = self.compute(
                    product_ids=[product], months=[period], grain=PERIOD_KINDS[period]
                )
                self.assertEqual(report["totals"], {METRIC_ID: amount})
                self.assertEqual(report["rows"][0][METRIC_ID], amount)
                self.assertEqual(report["rows"][0]["period"], period)
                self.assertEqual(report["time_column"], "period")
                self.assertEqual(report["units"], {METRIC_ID: "EUR million"})
                self.assertFalse(report["synthetic_record"])

    def test_multi_period_comparisons_never_produce_combined_totals(self):
        for periods, grain in (
            (["2024", "2025"], "year"),
            (["2025-Q2", "2026-Q2"], "quarter"),
            (["2026-Q1", "2026-Q2"], "quarter"),
            (["2025-H1", "2026-H1"], "half_year"),
        ):
            with self.subTest(periods=periods):
                report = self.compute(months=periods, grain=grain)
                self.assertEqual(report["totals"], {})
                self.assertEqual(len(report["rows"]), len(periods))
                self.assertIn("restatements", report["aggregation_note"])

    def test_single_period_totals_sum_selected_products_not_whole_division(self):
        report = self.compute(
            product_ids=["PUBLIC-NUBEQA", "PUBLIC-KERENDIA"], months=["2026-Q2"],
            grain="quarter",
        )
        self.assertEqual(report["totals"], {METRIC_ID: 1209})
        self.assertIn("not the whole", report["aggregation_note"])

    def test_unavailable_scope_and_mixed_period_types_fail_closed(self):
        for change in (
            {"months": ["2025", "2025-Q4"]},
            {"months": ["2026-Q1", "2026-H1"], "grain": "quarter"},
            {"months": ["2026-Q3"], "grain": "quarter"},
            {"months": ["2026"], "grain": "year"},
            {"months": ["2025-01-01"], "grain": "month"},
            {"months": []}, {"months": ["2025", "2025"]},
            {"product_ids": ["PUBLIC-UNKNOWN"]},
            {"market_ids": ["DE"]}, {"metric_ids": ["FORECAST"]},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.compute(**change)

    def test_invalid_source_facts_are_not_coerced_repaired_or_dropped(self):
        for field, value in (
            (METRIC_ID, True), (METRIC_ID, 1.5), (METRIC_ID, "1523"),
            (METRIC_ID, -1), ("market_id", "DE"), ("source_id", "BAYER-Q12026"),
            ("source_column", "Q4 2025"), ("source_row", False),
            ("source_row_label", ""), ("period_kind", "month"),
        ):
            bad = copy.deepcopy(self.snapshot)
            bad["rows"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.compute(source=bad)
        for mutation in ("missing", "duplicate"):
            bad = copy.deepcopy(self.snapshot)
            if mutation == "missing":
                bad["rows"].pop()
            else:
                bad["rows"].append(copy.deepcopy(bad["rows"][0]))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.compute(source=bad)

    def test_zero_is_not_missing_and_inputs_are_not_mutated(self):
        source = copy.deepcopy(self.snapshot)
        for row in source["rows"]:
            if row["product_id"] == "PUBLIC-NUBEQA" and row["period"] == "2025":
                row[METRIC_ID] = 0
        before = copy.deepcopy(source)
        report = self.compute(source=source)
        self.assertEqual(report["totals"], {METRIC_ID: 0})
        report["rows"][0][METRIC_ID] = 42
        self.assertEqual(source, before)

    def test_wrong_report_provenance_or_period_boundaries_fail_closed(self):
        for field, value in (
            ("source_url", self.snapshot["sources"][1]["source_url"]),
            ("download_url", self.snapshot["sources"][1]["download_url"]),
            ("source_snapshot", "../dataset.json"),
            ("html_snapshot", "sources/wrong.html"),
            ("source_sha256", "not a hash"),
            ("retrieved_at_utc", "2026-11-07"),
        ):
            bad = copy.deepcopy(self.snapshot)
            bad["sources"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_snapshot(bad)
        bad = copy.deepcopy(self.snapshot)
        bad["periods"][0]["end_date"] = "2024-06-30"
        with self.assertRaises(ValueError):
            validate_snapshot(bad)

    def test_report_provenance_keeps_used_source_and_restatement_notes(self):
        report = self.compute(months=["2025-Q1"], grain="quarter")
        sources = report["source_provenance"]["sources"]
        self.assertEqual([s["source_id"] for s in sources], ["BAYER-Q12026"])
        self.assertIn("restated", sources[0]["notes"])
        row = report["rows"][0]
        self.assertEqual(row["source_column"], "Q1 2025")
        self.assertEqual(row["source_id"], sources[0]["source_id"])
        self.assertIsInstance(row["source_row"], int)

    def test_catalog_choices_contain_period_metadata_not_business_figures(self):
        choices = self.catalog.choices()
        self.assertEqual(len(choices["products"]), 15)
        self.assertEqual(len(choices["periods"]), 10)
        self.assertEqual(choices["grain_options"], ["year", "quarter", "half_year"])
        self.assertFalse(choices["synthetic_record"])
        self.assertNotIn('"rows"', json.dumps(choices))
        self.assertEqual(financial_contract_gaps(self.catalog), [])
        self.assertEqual(financial_scope_gaps(self.catalog.model(), {
            "product_ids": ["PUBLIC-NUBEQA"], "market_ids": ["GLOBAL"],
            "months": ["2026-Q2"], "grain": "quarter",
        }), [])
        self.assertIn("incompatible_reporting_period_types", financial_scope_gaps(
            self.catalog.model(), {
                "product_ids": ["PUBLIC-NUBEQA"], "market_ids": ["GLOBAL"],
                "months": ["2026-Q2", "2026-H1"], "grain": "quarter",
            }
        ))

    def test_catalog_refuses_invalid_source_and_detects_snapshot_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dataset.json"
            path.write_text(json.dumps(self.snapshot), encoding="utf-8")
            catalog = PublicFinancialCatalog(path)
            bad = copy.deepcopy(self.snapshot)
            bad["unit"] = "EUR"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(SnapshotDrift):
                catalog.assert_current()
            with self.assertRaises(CatalogError):
                PublicFinancialCatalog(path)

    def test_parser_retains_explicit_annual_quarter_and_half_year_scope(self):
        for text, periods, grain in (
            ("Global Nubeqa sales 2024 and 2025", ["2024", "2025"], "year"),
            ("Global Nubeqa sales Q2 2025 and 2026", ["2025-Q2", "2026-Q2"], "quarter"),
            ("Global Nubeqa sales 2025-Q4 and 2026-Q1", ["2025-Q4", "2026-Q1"], "quarter"),
            ("Global Nubeqa sales H1 2025 and 2026", ["2025-H1", "2026-H1"], "half_year"),
        ):
            with self.subTest(text=text):
                parsed = parse_financial_message(text, self.catalog.choices(), self.catalog)
                self.assertEqual(parsed["months"], periods)
                self.assertEqual(parsed["grain"], grain)
                self.assertEqual(parsed["unsupported"], [])

    def test_parser_never_silently_trims_unavailable_quarters(self):
        parsed = parse_financial_message(
            "All products global sales Q1 through Q4 2026",
            self.catalog.choices(), self.catalog,
        )
        self.assertEqual(parsed["months"], ["2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"])
        self.assertTrue(parsed["unsupported"])
        self.assertEqual(len(parsed["product_ids"]), 15)
        incomplete = parse_financial_message("Nubeqa sales", self.catalog.choices(), self.catalog)
        self.assertEqual(incomplete["months"], [])
        self.assertEqual(incomplete["market_ids"], [])


if __name__ == "__main__":
    unittest.main()
