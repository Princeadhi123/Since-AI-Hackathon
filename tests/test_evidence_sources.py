import csv
import hashlib
import json
import unittest
from html import escape
from pathlib import Path

from openpyxl import load_workbook

from prepare_evidence import EXPECTED_SALES, PRODUCTS, SHEETS, public_evidence, scalar

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data" / "evidence"


def source_table(year="2025", duplicate=False, changed=False):
    header = [
        "€ million", "", "Q4 2024", "", "Q4 2025", "", "Reported", "",
        "Fx & p adj.", "", "2024", "", year, "", "Reported", "", "Fx & p adj.",
    ]
    rows = [header]
    for name in PRODUCTS:
        cells = [""] * 17
        cells[0] = name + "™"
        cells[10] = str(EXPECTED_SALES[name, 2024])
        cells[12] = str(EXPECTED_SALES[name, 2025] + int(changed))
        rows.append(cells)
    if duplicate:
        rows.append(rows[1])
    return (
        "<table>" + "".join(
            "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>"
            for row in rows
        ) + "</table>"
    ).encode("utf-8")


class EvidenceSourceTests(unittest.TestCase):
    def test_frozen_public_values_and_csv_match_reviewed_source(self):
        data = json.loads((EVIDENCE / "public_financials.json").read_text(encoding="utf-8"))
        self.assertEqual(data["data_classification"], "public_reported_actual")
        self.assertEqual(data["unit"], "EUR million")
        self.assertEqual(len(data["rows"]), 8)
        self.assertEqual(
            {(r["product_name"], r["year"]): r["sales_eur_million"] for r in data["rows"]},
            EXPECTED_SALES,
        )
        with (EVIDENCE / "public_financials.csv").open(encoding="utf-8", newline="") as f:
            records = list(csv.DictReader(f))
        self.assertEqual(records, [
            {key: str(value) for key, value in row.items()} for row in data["rows"]
        ])

    def test_public_parser_preserves_values(self):
        result = public_evidence(source_table(), "test-timestamp")
        self.assertEqual(
            {(r["product_name"], r["year"]): r["sales_eur_million"] for r in result["rows"]},
            EXPECTED_SALES,
        )

    def test_public_parser_rejects_changed_source(self):
        for raw in (
            source_table(year="2026"),
            source_table(duplicate=True),
            source_table(changed=True),
            source_table().replace("€ million".encode(), b"USD million"),
            b"<html>No sales table</html>",
        ):
            with self.subTest(raw=raw[:50]), self.assertRaises(ValueError):
                public_evidence(raw, "test-timestamp")

    def test_official_estate_is_an_unrepaired_row_preserving_snapshot(self):
        data = json.loads((EVIDENCE / "challenge_estate.json").read_text(encoding="utf-8"))
        self.assertEqual(data["data_classification"], "official_synthetic_challenge")
        source = ROOT / "data" / data["source_file"]
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), data["source_sha256"])
        workbook = load_workbook(source, read_only=True, data_only=False)
        try:
            self.assertEqual(set(data["tables"]), set(SHEETS))
            for name in SHEETS:
                rows = iter(workbook[name].values)
                headers = next(rows)
                expected = [
                    {"_source_row": i, **{
                        k: scalar(v) for k, v in zip(headers, row, strict=True)
                    }}
                    for i, row in enumerate(rows, 2) if any(v is not None for v in row)
                ]
                self.assertEqual(data["tables"][name], expected, name)
        finally:
            workbook.close()

    def test_local_publisher_snapshot_matches_provenance(self):
        data = json.loads((EVIDENCE / "public_financials.json").read_text(encoding="utf-8"))
        snapshot = EVIDENCE / data["source_snapshot"]
        if not snapshot.exists():
            self.skipTest("Publisher HTML is local-only, not redistributed")
        raw = snapshot.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), data["source_sha256"])
        self.assertEqual(public_evidence(raw, data["retrieved_at_utc"])["rows"], data["rows"])
