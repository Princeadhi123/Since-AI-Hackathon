"""Export artifact tests: escaping, bundle contents, verbatim values only."""

import copy
import io
import json
import unittest
import zipfile

from smart_librarian.reporting.exports import (
    build_report_bundle,
    export_report_html,
)

REPORT = {
    "rows": [
        {
            "product_id": "DEMO-P-NUB",
            "product_name": "<b>Nubeqa</b> & <script>alert(1)</script>",
            "market_id": "DE",
            "market_name": 'Germany"><img src=x>',
            "month": "2026-01-01",
            "DEMO-NET-SALES": 107000,
            "DEMO-FORECAST": 100000,
            "DEMO-VARIANCE-PCT": 7.0,
        },
        {
            "product_id": "DEMO-P-NUB",
            "product_name": "<b>Nubeqa</b> & <script>alert(1)</script>",
            "market_id": "DE",
            "market_name": "Germany",
            "month": "2026-02-01",
            "DEMO-NET-SALES": 110000,
            "DEMO-FORECAST": 105000,
            "DEMO-VARIANCE-PCT": 4.76,
        },
    ],
    "totals": {
        "DEMO-NET-SALES": 217000,
        "DEMO-FORECAST": 205000,
        "DEMO-VARIANCE-PCT": 5.85,
    },
    "units": {
        "DEMO-NET-SALES": "EUR",
        "DEMO-FORECAST": "EUR",
        "DEMO-VARIANCE-PCT": "percent",
    },
    "proposal_id": "prop-1",
    "spec_hash": "ab" * 32,
    "approval_status": "approved",
    "outcome": "PROPOSE_BUILD",
    "source_asset_id": None,
    "registered_asset_id": "GEN-ABCDEF0123456789",
    "asset": {
        "asset_id": "GEN-ABCDEF0123456789",
        "name": "Generated <img> report",
        "owner_id": "DEMO-OWNER-001",
        "owner_name": "Synthetic <Steward>",
        "endorsement": "promoted",
        "lifecycle_status": "active",
    },
    "spec": {
        "spec_version": "1.0.0",
        "user_id": "DEMO-USER-GLOBAL",
        "dataset_id": "DEMO-DATASET",
        "model_id": "DEMO-MODEL-SALES",
        "dataset_fingerprint": "ff" * 32,
        "intent": {
            "product_ids": ["DEMO-P-NUB"],
            "market_ids": ["DE"],
            "metric_ids": ["DEMO-NET-SALES"],
            "months": ["2026-01-01"],
            "grain": "month",
        },
        "requested_metrics": [
            {"metric_id": "DEMO-NET-SALES", "name": "Net Sales", "unit": "EUR"}
        ],
    },
}


class ExportHtmlTests(unittest.TestCase):
    def setUp(self):
        self.page = export_report_html(REPORT)

    def test_source_strings_are_escaped(self):
        self.assertNotIn("<script>alert(1)</script>", self.page)
        self.assertNotIn("<b>Nubeqa</b>", self.page)
        self.assertNotIn('Germany"><img src=x>', self.page)
        self.assertNotIn("Synthetic <Steward>", self.page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", self.page)
        self.assertIn("&lt;b&gt;Nubeqa&lt;/b&gt;", self.page)

    def test_totals_and_values_rendered_verbatim(self):
        self.assertIn("217,000 EUR", self.page)
        self.assertIn("5.85%", self.page)
        self.assertIn("107,000 EUR", self.page)

    def test_no_external_resources(self):
        for needle in ("http://", "https://", 'src="', "src='",
                       "@import", "<script"):
            self.assertNotIn(needle, self.page.replace(
                "xmlns=\"http://www.w3.org/2000/svg\"", ""
            ).replace("&lt;img src=x&gt;", ""))
        self.assertIn("<svg", self.page)
        self.assertIn("@media print", self.page)

    def test_null_values_are_chart_gaps(self):
        report = copy.deepcopy(REPORT)
        report["rows"] = [
            {**REPORT["rows"][0], "month": "2026-01-01",
             "DEMO-ON-TIME-PCT": 90.0},
            {**REPORT["rows"][0], "month": "2026-02-01",
             "DEMO-ON-TIME-PCT": None},
            {**REPORT["rows"][0], "month": "2026-03-01",
             "DEMO-ON-TIME-PCT": 95.0},
        ]
        report["totals"] = {"DEMO-ON-TIME-PCT": 92.5}
        report["units"] = {"DEMO-ON-TIME-PCT": "percent"}
        report["spec"]["requested_metrics"] = [
            {"metric_id": "DEMO-ON-TIME-PCT", "name": "On Time %"}
        ]
        page = export_report_html(report)
        # Jan->Feb and Feb->Mar must not be connected: the single series
        # produces at most two one-point "segments", i.e. no polyline at all.
        self.assertNotIn("<polyline", page)
        # A finite-Jan, null-Feb, finite-Mar, finite-Apr chain draws exactly
        # one segment across the defined neighbours only.
        report["rows"].append(
            {**REPORT["rows"][0], "month": "2026-04-01",
             "DEMO-ON-TIME-PCT": 97.0}
        )
        page = export_report_html(report)
        self.assertEqual(page.count("<polyline"), 1)
        self.assertIn("95.00%", page)

    def test_unit_aware_labels_and_names(self):
        report = copy.deepcopy(REPORT)
        report["totals"] = {"DEMO-DELIVERED": 1234, "DEMO-LEAD-DAYS": 3.14159}
        report["units"] = {"DEMO-DELIVERED": "orders", "DEMO-LEAD-DAYS": "days"}
        report["spec"]["requested_metrics"] = [
            {"metric_id": "DEMO-DELIVERED", "name": "Delivered Orders"},
            {"metric_id": "DEMO-LEAD-DAYS", "name": "Average Lead Time"},
        ]
        page = export_report_html(report)
        self.assertIn("1,234 orders", page)
        self.assertIn("3.14 days", page)
        self.assertIn("Delivered Orders", page)
        self.assertIn("Average Lead Time", page)

    def test_provenance_present(self):
        self.assertIn("GEN-ABCDEF0123456789", self.page)
        self.assertIn("ab" * 32, self.page)
        self.assertIn("promoted", self.page)
        self.assertIn("DEMO-MODEL-SALES", self.page)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.bundle = zipfile.ZipFile(io.BytesIO(build_report_bundle(REPORT)))

    def test_fixed_contents(self):
        self.assertEqual(
            sorted(self.bundle.namelist()),
            ["README.txt", "report.csv", "report.html", "specification.json"],
        )

    def test_csv_values_verbatim(self):
        text = self.bundle.read("report.csv").decode("utf-8")
        self.assertIn("107000", text)
        self.assertIn("product_name", text.splitlines()[0])
        # CSV carries source strings as data; no HTML markup executed there.
        self.assertIn("107000", text)

    def test_specification_json(self):
        spec = json.loads(self.bundle.read("specification.json"))
        self.assertEqual(spec["spec_hash"], "ab" * 32)
        self.assertEqual(
            spec["registered_asset_id"], "GEN-ABCDEF0123456789"
        )
        self.assertEqual(spec["spec"]["model_id"], "DEMO-MODEL-SALES")

    def test_readme_is_honest(self):
        text = self.bundle.read("README.txt").decode("utf-8")
        self.assertIn("Power BI", text)
        self.assertIn("no .pbip/.pbix", text.lower().replace("  ", " "))
        self.assertIn("synthetic", text.lower())

    def test_readme_monthly_date_instruction_unchanged(self):
        text = self.bundle.read("README.txt").decode("utf-8")
        self.assertIn("mark 'month' as a date column", text)
        self.assertNotIn("whole-number", text)


class PeriodBundleTests(unittest.TestCase):
    def _report(self):
        report = copy.deepcopy(REPORT)
        report["data_classification"] = "public_reported_actual"
        report["synthetic_record"] = False
        report["time_column"] = "period"
        report["time_label"] = "Reporting period"
        for row in report["rows"]:
            row["period"] = row.pop("month")
            row["source_id"] = "SRC-1"
            row["source_table"] = "t"
            row["source_row_label"] = "Nubeqa"
            row["source_column"] = "2025"
            row["source_row"] = "r1"
        report["totals"] = {}
        report["units"] = {"PUBLIC-REPORTED-SALES": "EUR million"}
        report["rows"] = [
            {k: v for k, v in row.items() if not k.startswith("DEMO-")}
            | {"PUBLIC-REPORTED-SALES": 2385}
            for row in report["rows"]
        ]
        return report

    def test_period_csv_carries_source_refs(self):
        bundle = zipfile.ZipFile(
            io.BytesIO(build_report_bundle(self._report()))
        )
        text = bundle.read("report.csv").decode("utf-8")
        header = text.splitlines()[0]
        for field in ("source_id", "source_table", "source_row_label",
                      "source_column", "source_row"):
            self.assertIn(field, header)
        self.assertIn("SRC-1", text)

    def test_period_readme_no_date_or_cross_year(self):
        bundle = zipfile.ZipFile(
            io.BytesIO(build_report_bundle(self._report()))
        )
        text = bundle.read("README.txt").decode("utf-8")
        self.assertIn("text period label", text)
        self.assertNotIn("as a date column", text)
        self.assertIn("cross-period", text)
        self.assertNotIn("cross-year", text)


if __name__ == "__main__":
    unittest.main()
