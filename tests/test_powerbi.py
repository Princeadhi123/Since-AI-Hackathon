"""Power BI import kit tests: fixed files, frozen values, M types, safety."""

import copy
import io
import json
import unittest
import zipfile

from smart_librarian.reporting.powerbi import (
    FOLDER_PATH_PLACEHOLDER,
    build_powerbi_import_bundle,
    build_public_financials_bundle,
    serialize_rows_csv,
)

REPORT = {
    "rows": [
        {
            "product_id": "DEMO-P-NUB",
            "product_name": "Nubeqa",
            "market_id": "DE",
            "market_name": "Germany",
            "month": "2026-01-01",
            "DEMO-NET-SALES": 107000,
            "DEMO-ON-TIME-PCT": 92.5,
            "DEMO-LEAD-DAYS": None,
        },
        {
            "product_id": "DEMO-P-NUB",
            "product_name": "=cmd|' /C calc'!A0",
            "market_id": "DE",
            "market_name": "Germany\tEast\nWest",
            "month": "2026-02-01",
            "DEMO-NET-SALES": 110000,
            "DEMO-ON-TIME-PCT": 95.0,
            "DEMO-LEAD-DAYS": 3.5,
        },
    ],
    "totals": {
        "DEMO-NET-SALES": 217000,
        "DEMO-ON-TIME-PCT": 93.75,
        "DEMO-LEAD-DAYS": 3.5,
    },
    "units": {
        "DEMO-NET-SALES": "EUR",
        "DEMO-ON-TIME-PCT": "percent",
        "DEMO-LEAD-DAYS": "days",
    },
    "proposal_id": "prop-1",
    "spec_hash": "ab" * 32,
    "approval_status": "approved",
    "outcome": "PROPOSE_BUILD",
    "source_asset_id": None,
    "registered_asset_id": "GEN-ABCDEF0123456789",
    "asset": {
        "asset_id": "GEN-ABCDEF0123456789",
        "name": "Generated report",
        "owner_id": "DEMO-OWNER-001",
        "owner_name": "Synthetic Steward",
        "endorsement": "promoted",
    },
    "spec": {
        "model_id": "DEMO-MODEL-LOG",
        "dataset_id": "DEMO-DATASET",
        "dataset_fingerprint": "ff" * 32,
        "intent": {"grain": "month"},
        "requested_metrics": [],
    },
}

PUBLIC = {
    "source_url": "https://reports.bayer.com/example",
    "source_title": "Public source",
    "source_sha256": "cd" * 32,
    "source_snapshot": "snapshot.html",
    "retrieved_at_utc": "2026-11-07T00:00:00+00:00",
    "data_classification": "public_reported_actual",
    "disclaimer": "Public reported actuals.",
    "unit": "EUR million",
    "grain": "product x fiscal_year",
    "rows": [
        {"product_name": "Nubeqa", "year": 2024,
         "sales_eur_million": 1523, "source_table": "t",
         "source_row_label": "Nubeqa"},
        {"product_name": "Nubeqa", "year": 2025,
         "sales_eur_million": 2385, "source_table": "t",
         "source_row_label": "Nubeqa"},
    ],
}


class PowerBiBundleTests(unittest.TestCase):
    def setUp(self):
        self.bundle = zipfile.ZipFile(
            io.BytesIO(build_powerbi_import_bundle(REPORT))
        )

    def read(self, name):
        return self.bundle.read(name).decode("utf-8")

    def test_fixed_contents(self):
        self.assertEqual(
            sorted(self.bundle.namelist()),
            [
                "PowerQuery_Report.m", "PowerQuery_Totals.m", "README.txt",
                "provenance.json", "report.csv", "theme.json", "totals.csv",
            ],
        )

    def test_report_csv_frozen_values(self):
        text = self.read("report.csv")
        header = text.splitlines()[0]
        self.assertEqual(
            header,
            "product_id,product_name,market_id,market_name,month,"
            "DEMO-NET-SALES,DEMO-ON-TIME-PCT,DEMO-LEAD-DAYS",
        )
        self.assertIn("107000", text)
        self.assertIn("95.0", text)
        self.assertIn("2026-01-01,107000,92.5,\r\n", text)

    def test_percent_not_rescaled(self):
        text = self.read("report.csv")
        self.assertIn("92.5", text)
        self.assertNotIn("0.925", text)

    def test_csv_formula_injection_mitigated(self):
        text = self.read("report.csv")
        self.assertIn("'=cmd|' /C calc'!A0", text)
        self.assertNotIn("\t", text)
        for line in text.splitlines():
            self.assertFalse(line.lstrip('"').startswith("="))
        self.assertIn(",110000,", text)

    def test_totals_csv_single_row(self):
        lines = self.read("totals.csv").strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(
            lines[0],
            "DEMO-NET-SALES,DEMO-ON-TIME-PCT,DEMO-LEAD-DAYS",
        )
        self.assertEqual(lines[1], "217000,93.75,3.5")

    def test_m_scripts_typed_and_placeholder(self):
        for name in ("PowerQuery_Report.m", "PowerQuery_Totals.m"):
            text = self.read(name)
            self.assertIn(FOLDER_PATH_PLACEHOLDER, text)
            self.assertIn("Csv.Document", text)
            self.assertIn("QuoteStyle.Csv", text)
            self.assertNotIn("QuoteStyle.QuoteStyleCsv", text)
            self.assertIn("Encoding = 65001", text)
            self.assertIn('"en-US"', text)
            for banned in ("List.Sum", "Table.Group", "List.Average", "//"):
                self.assertNotIn(banned, text)
        report_m = self.read("PowerQuery_Report.m")
        self.assertIn('"month", type date', report_m)
        self.assertIn('"product_id", type text', report_m)
        self.assertIn('"DEMO-NET-SALES", type number', report_m)
        totals_m = self.read("PowerQuery_Totals.m")
        self.assertIn('"DEMO-LEAD-DAYS", type number', totals_m)

    def test_m_null_mapping_covers_all_columns(self):
        report_m = self.read("PowerQuery_Report.m")
        null_line = next(
            line for line in report_m.splitlines()
            if "Table.ReplaceValue" in line
        )
        for column in (
            "product_id", "product_name", "market_id", "market_name",
            "month", "DEMO-NET-SALES", "DEMO-ON-TIME-PCT", "DEMO-LEAD-DAYS",
        ):
            self.assertIn(f'"{column}"', null_line)
        self.assertIn("WithNulls", report_m)
        self.assertIn("TransformColumnTypes(WithNulls", report_m)
        totals_m = self.read("PowerQuery_Totals.m")
        totals_null_line = next(
            line for line in totals_m.splitlines()
            if "Table.ReplaceValue" in line
        )
        for column in ("DEMO-NET-SALES", "DEMO-ON-TIME-PCT", "DEMO-LEAD-DAYS"):
            self.assertIn(f'"{column}"', totals_null_line)

    def test_m_string_escaping(self):
        report = copy.deepcopy(REPORT)
        report["totals"] = {'BAD"ID': 1.5, 'EVIL#(x': 2.5}
        report["rows"] = [
            dict(REPORT["rows"][0], **{'BAD"ID': 1.0, 'EVIL#(x': 2.0})
        ]
        bundle = zipfile.ZipFile(
            io.BytesIO(build_powerbi_import_bundle(report))
        )
        totals_m = bundle.read("PowerQuery_Totals.m").decode("utf-8")
        self.assertIn('"BAD""ID"', totals_m)
        self.assertIn('"EVIL#(#)(x"', totals_m)
        self.assertNotIn('#(x', totals_m)

    def test_provenance_json(self):
        prov = json.loads(self.read("provenance.json"))
        self.assertEqual(prov["spec_hash"], "ab" * 32)
        self.assertEqual(prov["dataset_fingerprint"], "ff" * 32)
        self.assertEqual(prov["approval_status"], "approved")
        self.assertEqual(prov["owner"], "Synthetic Steward")
        self.assertEqual(prov["units"]["DEMO-ON-TIME-PCT"], "percent")
        self.assertIn("0-100", prov["data_disclaimer"])

    def test_theme_and_readme(self):
        theme = json.loads(self.read("theme.json"))
        self.assertTrue(theme["dataColors"])
        readme = self.read("README.txt")
        lowered = readme.lower()
        self.assertIn("don't summarize", lowered)
        self.assertIn("totals.csv", lowered)
        self.assertIn("not a .pbip", lowered)
        self.assertIn("0-100", lowered)
        self.assertIn("percent", lowered)
        self.assertIn("days", lowered)


class PeriodReportKitTests(unittest.TestCase):
    def _report(self):
        report = copy.deepcopy(REPORT)
        report["data_classification"] = "public_reported_actual"
        report["synthetic_record"] = False
        report["time_column"] = "period"
        for row in report["rows"]:
            row["period"] = row.pop("month")
            row["source_id"] = "SRC-1"
            row["source_column"] = "2025"
            row["source_row"] = "r1"
            row["source_table"] = "t"
            row["source_row_label"] = "Nubeqa"
        return report

    def _bundle(self, report):
        return zipfile.ZipFile(
            io.BytesIO(build_powerbi_import_bundle(report))
        )

    def test_period_time_column_is_text(self):
        bundle = self._bundle(self._report())
        report_m = bundle.read("PowerQuery_Report.m").decode("utf-8")
        self.assertIn('"period", type text', report_m)
        self.assertNotIn('"period", type date', report_m)
        self.assertNotIn("Int64.Type", report_m)

    def test_period_source_refs_in_csv_and_m(self):
        bundle = self._bundle(self._report())
        header = bundle.read("report.csv").decode("utf-8").splitlines()[0]
        for field in ("source_id", "source_table", "source_row_label",
                      "source_column", "source_row"):
            self.assertIn(field, header)
        report_m = bundle.read("PowerQuery_Report.m").decode("utf-8")
        self.assertIn('"source_id", type text', report_m)
        self.assertIn('"source_column", type text', report_m)

    def test_period_readme_cross_period_wording(self):
        report = self._report()
        report["totals"] = {}
        readme = self._bundle(report).read("README.txt").decode("utf-8")
        self.assertIn("x period", readme)
        self.assertIn("cross-period", readme)
        self.assertNotIn("cross-year", readme)


class PublicFinancialsBundleTests(unittest.TestCase):
    def setUp(self):
        self.bundle = zipfile.ZipFile(
            io.BytesIO(build_public_financials_bundle(PUBLIC))
        )

    def read(self, name):
        return self.bundle.read(name).decode("utf-8")

    def test_fixed_contents(self):
        self.assertEqual(
            sorted(self.bundle.namelist()),
            [
                "PowerQuery_PublicFinancials.m", "README.txt",
                "provenance.json", "public_financials.csv", "theme.json",
            ],
        )

    def test_csv_headers_and_values(self):
        text = self.read("public_financials.csv")
        self.assertEqual(
            text.splitlines()[0],
            "product_name,year,sales_eur_million,source_table,"
            "source_row_label",
        )
        self.assertIn("Nubeqa,2024,1523", text)
        self.assertIn("Nubeqa,2025,2385", text)

    def test_m_typed_columns(self):
        text = self.read("PowerQuery_PublicFinancials.m")
        self.assertIn('"year", Int64.Type', text)
        self.assertIn('"sales_eur_million", type number', text)
        self.assertIn('"product_name", type text', text)
        self.assertIn(FOLDER_PATH_PLACEHOLDER, text)

    def test_no_totals_in_public_kit(self):
        self.assertNotIn("totals.csv", self.bundle.namelist())
        prov = json.loads(self.read("provenance.json"))
        self.assertEqual(prov["source_sha256"], "cd" * 32)
        self.assertEqual(prov["data_classification"],
                         "public_reported_actual")


class CellSafetyTests(unittest.TestCase):
    def test_dangerous_string_prefixes(self):
        csv_text = serialize_rows_csv(
            [{"c": "=1+1"}, {"c": "+SUM(A1)"}, {"c": "-5"},
             {"c": "@mention"}, {"c": "safe"}],
            ["c"],
        )
        lines = csv_text.strip().splitlines()[1:]
        self.assertEqual(
            lines, ["'=1+1", "'+SUM(A1)", "'-5", "'@mention", "safe"]
        )

    def test_whitespace_prefixed_formulas_mitigated(self):
        csv_text = serialize_rows_csv(
            [{"c": "\t=1+1"}, {"c": "\n@cmd"}, {"c": "  -2"},
             {"c": "  plain text"}, {"c": "\tleading tab text"}],
            ["c"],
        )
        lines = csv_text.strip().splitlines()[1:]
        self.assertEqual(
            lines,
            ["' =1+1", "' @cmd", "'  -2", "  plain text",
             " leading tab text"],
        )

    def test_numbers_untouched(self):
        csv_text = serialize_rows_csv(
            [{"n": -5, "x": None, "s": "a\tb\nc"}], ["n", "x", "s"]
        )
        self.assertIn("-5,,a b c", csv_text)


if __name__ == "__main__":
    unittest.main()
