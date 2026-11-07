"""Dashboard PBIP packaging tests: lead-authored helper integration only.

Reads byte-for-byte frozen captures from tests/fixtures (synthetic test
evidence); never re-derives source values.
"""

import base64
import copy
import io
import json
import unittest
import zipfile
from pathlib import Path

from smart_librarian.challenge import stable_hash
from smart_librarian.reporting.challenge_pbip import (
    build_challenge_pbip_bundle,
    build_challenge_pbip_files,
)
from smart_librarian.reporting.challenge_pbip_dashboard import (
    EVENT_MARKER,
    ROW_LABEL,
    ROW_SCOPE,
    metric_measure_name,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
DOMAINS = ["commercial", "market_access", "supply", "launch"]



def _report(domain):
    return json.loads(
        (FIXTURES / f"challenge_frozen_{domain}.json").read_text())


def _pages(files):
    return {
        n.split("/pages/")[1].split("/")[0]
        for n in files if "/pages/" in n and n.endswith("page.json")
    }


def _measure(files, name):
    model = json.loads(files["GovernedReport.SemanticModel/model.bim"])
    table = model["model"]["tables"][0]
    for measure in table.get("measures", []):
        if measure["name"] == name:
            return measure
    return None


def _visual_queries(files):
    queries = []
    for name, raw in files.items():
        if name.endswith("visual.json"):
            visual = json.loads(raw)
            query = visual.get("visual", {}).get("query") or {}
            queries.append((name, visual, query))
    return queries


class DashboardPackagingTests(unittest.TestCase):
    def test_all_domains_have_dashboard_pages(self):
        for domain in DOMAINS:
            files = build_challenge_pbip_files(_report(domain))
            pages = _pages(files)
            self.assertIn("Overview", pages, domain)
            self.assertIn("Evidence", pages, domain)
            self.assertIn("Governance", pages, domain)
            version = json.loads(
                files["GovernedReport.Report/definition/version.json"])
            self.assertEqual(version["version"], "2.0.0")
            meta = json.loads(
                files["GovernedReport.Report/definition/pages/pages.json"])
            self.assertEqual(meta["activePageName"], "Overview")
            self.assertIn("GovernedReport.pbip", files)
            self.assertIn("GovernedReport.SemanticModel/model.bim", files)
            self.assertIn("governance/desktop_handoff.json", files)

    def test_measure_shape_and_no_aggregation(self):
        for domain in DOMAINS:
            report = _report(domain)
            files = build_challenge_pbip_files(report)
            spec = report["spec"]
            selected = set(spec["intent"]["metric_ids"])
            field_map = {f["metric_id"]: f for f in spec.get("fields", [])}
            numeric = [
                m for m in selected
                if field_map[m]["unit"] not in ("category", "identifier")
                and any(m in row and isinstance(row[m], (int, float))
                        and not isinstance(row[m], bool)
                        for row in report["rows"])
            ]
            for metric in numeric:
                measure = _measure(files, metric_measure_name(metric))
                self.assertIsNotNone(measure, f"{domain}:{metric}")
                expected = (
                    "IF(COUNTROWS('FrozenReport') = 1, "
                    f"SELECTEDVALUE('FrozenReport'[{metric}]), BLANK())"
                )
                self.assertEqual(measure["expression"], expected)
                self.assertNotIn("SUM(", measure["expression"])
                self.assertNotIn("AVERAGE(", measure["expression"])
                if field_map[metric]["unit"] == "%":
                    self.assertEqual(
                        measure.get("formatString"), '0.0" %"')
            model = json.loads(
                files["GovernedReport.SemanticModel/model.bim"])
            measure_names = {
                m["name"]
                for m in model["model"]["tables"][0].get("measures", [])
            }
            for field_id in selected - set(numeric):
                self.assertNotIn(metric_measure_name(field_id), measure_names)
            for column in model["model"]["tables"][0]["columns"]:
                self.assertEqual(column["summarizeBy"], "none")

    def test_chart_axes_per_domain(self):
        for domain in DOMAINS:
            files = build_challenge_pbip_files(_report(domain))
            grain = _report(domain)["spec"]["intent"]["grain"]
            charts = [
                (n, v, q) for n, v, q in _visual_queries(files)
                if n.split("visuals/")[-1].startswith("Metric")
            ]
            self.assertTrue(charts, domain)
            for name, visual, query in charts:
                cats = query["queryState"]["Category"]["projections"]
                y = query["queryState"]["Y"]["projections"]
                for proj in y:
                    self.assertIn("Measure", proj["field"])
                cat_prop = cats[0]["field"]["Column"]["Property"]
                if domain == "launch":
                    self.assertEqual(cat_prop, "milestone_date")
                    self.assertEqual(
                        y[0]["field"]["Measure"]["Property"], EVENT_MARKER)
                    self.assertIn(
                        "not a kpi",
                        (_measure(files, EVENT_MARKER) or {})
                        .get("description", "").lower())
                    series = query["queryState"]["Series"]["projections"]
                    self.assertEqual(
                        series[0]["field"]["Column"]["Property"], ROW_LABEL)
                elif grain == "month":
                    self.assertEqual(cat_prop, "month")
                    series = query["queryState"]["Series"]["projections"]
                    self.assertEqual(
                        series[0]["field"]["Column"]["Property"], ROW_SCOPE)
                else:
                    self.assertEqual(cat_prop, ROW_LABEL)

    def test_embedded_rows_and_source_identity(self):
        for domain in DOMAINS:
            report = _report(domain)
            files = build_challenge_pbip_files(report)
            model = json.loads(
                files["GovernedReport.SemanticModel/model.bim"])
            expr = "\n".join(
                model["model"]["tables"][0]["partitions"][0]["source"]
                ["expression"])
            blob = expr.split('BinaryEncoding.Base64')[0].split('"')[1]
            self.assertEqual(
                json.loads(base64.b64decode(blob)), report["rows"])
            self.assertIn("_source_row", report["rows"][0])
            for row in report["rows"]:
                self.assertEqual(
                    row["_source_sheet"], report["spec"]["source_sheet"])

    def test_calculated_columns_source_only(self):
        for domain in DOMAINS:
            files = build_challenge_pbip_files(_report(domain))
            model = json.loads(
                files["GovernedReport.SemanticModel/model.bim"])
            calc = [
                c for c in model["model"]["tables"][0]["columns"]
                if c.get("type") == "calculated"
            ]
            self.assertEqual(
                {c["name"] for c in calc}, {ROW_SCOPE, ROW_LABEL})
            for column in calc:
                for ref in ("product_name", "market_name", "_source_row"):
                    if ref in column["expression"]:
                        self.assertIn(f"[{ref}]", column["expression"])

    def test_category_only_selection_no_invented_chart(self):
        report = _report("market_access")
        fields = report["spec"].get("fields", [])
        categorical = [
            f["metric_id"] for f in fields
            if f["unit"] in ("category", "identifier")
        ]
        self.assertTrue(categorical)
        report = copy.deepcopy(report)
        report["spec"] = dict(report["spec"])
        report["spec"]["intent"] = dict(report["spec"]["intent"])
        report["spec"]["intent"]["metric_ids"] = categorical
        report["spec"]["fields"] = [
            f for f in report["spec"].get("fields", [])
            if f["metric_id"] in categorical]
        report["spec_hash"] = stable_hash(report["spec"])
        files = build_challenge_pbip_files(report)
        model = json.loads(files["GovernedReport.SemanticModel/model.bim"])
        self.assertFalse(
            model["model"]["tables"][0].get("measures"))
        tables = [
            n for n in files
            if n.endswith("visual.json") and "SourceRows" in n
        ]
        self.assertTrue(tables)
        self.assertFalse(
            [n for n in files if "Metric" in n and n.endswith("visual.json")])

    def test_multi_scope_and_reversed_rows_deterministic(self):
        report = _report("commercial")
        files = build_challenge_pbip_files(report)
        multi = copy.deepcopy(report)
        multi["spec"] = dict(multi["spec"])
        multi["spec"]["intent"] = dict(multi["spec"]["intent"])
        multi["spec"]["intent"]["product_ids"] = ["P-NUB", "P-KER"]
        multi["spec"]["intent"]["market_ids"] = ["DE", "FI"]
        multi["spec_hash"] = stable_hash(multi["spec"])
        multi["rows"] = [
            dict(r, product_id="P-KER", product_name="Kerendia",
                 market_id="FI", market_name="Finland",
                 _source_row=9000 + i)
            for i, r in enumerate(multi["rows"])
        ] + multi["rows"]
        m_files = build_challenge_pbip_files(multi)
        self.assertTrue(_pages(m_files) >= {"Overview", "Evidence"})
        reversed_rows = copy.deepcopy(report)
        reversed_rows["rows"] = list(reversed(reversed_rows["rows"]))
        self.assertEqual(
            build_challenge_pbip_bundle(reversed_rows),
            build_challenge_pbip_bundle(reversed_rows))
        r_files = build_challenge_pbip_files(reversed_rows)
        self.assertTrue(_pages(r_files))

    def test_duplicate_source_identity_refusal(self):
        report = _report("commercial")
        bad = copy.deepcopy(report)
        bad["rows"][0]["_source_sheet"] = "Wrong_Sheet"
        with self.assertRaises(ValueError):
            build_challenge_pbip_files(bad)
        mixed = copy.deepcopy(report)
        mixed["rows"].append({
            **mixed["rows"][0], "_source_row": 999,
            "net_sales_m_eur_syn": "mixed",
        })
        with self.assertRaises(ValueError):
            build_challenge_pbip_files(mixed)
        dupe = copy.deepcopy(report)
        dupe["rows"].append(dict(dupe["rows"][0]))
        with self.assertRaises(ValueError):
            build_challenge_pbip_files(dupe)


if __name__ == "__main__":
    unittest.main()
