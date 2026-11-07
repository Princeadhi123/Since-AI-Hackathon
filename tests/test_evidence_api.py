"""Evidence endpoint tests: classification contract and fail-safe 503s."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from smart_librarian.api.app import create_app
from smart_librarian import evidence


class EvidenceApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "runtime.sqlite"
        self.client = TestClient(create_app(runtime_db=db, include_synthetic=True))

    def tearDown(self):
        self._tmp.cleanup()

    def test_challenge_classification_and_tables(self):
        response = self.client.get("/api/evidence/challenge")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["data_classification"], "official_synthetic_challenge"
        )
        for table in (
            "Analytics_Assets", "Semantic_Models", "Owners", "KPI_Catalog",
            "Asset_KPI_Map", "Asset_Usage", "Lineage_Edges",
            "Governance_Signals", "Migration_Backlog", "Data_Quality",
            "Governance_Rules",
        ):
            self.assertIn(table, payload["tables"])
        self.assertTrue(payload["disclaimer"])
        self.assertTrue(payload["source_sha256"])

    def test_public_classification_and_rows(self):
        response = self.client.get("/api/evidence/public")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["data_classification"], "public_reported_actual"
        )
        self.assertTrue(payload["rows"])
        for row in payload["rows"]:
            self.assertIn("product_name", row)
            self.assertIn("year", row)
            self.assertIn("sales_eur_million", row)
        self.assertEqual(payload["unit"], "EUR million")

    def test_unknown_kind_rejected(self):
        self.assertEqual(
            self.client.get("/api/evidence/unknown").status_code, 422
        )

    def test_missing_file_returns_503(self):
        with tempfile.TemporaryDirectory() as empty:
            with mock.patch.object(evidence, "EVIDENCE_DIR", Path(empty)):
                response = self.client.get("/api/evidence/challenge")
        self.assertEqual(response.status_code, 503)
        self.assertIn("detail", response.json())

    def test_invalid_file_returns_503(self):
        for body in (
            "not json",
            json.dumps({"data_classification": "public_reported_actual",
                        "rows": []}),
            json.dumps({"data_classification": "official_synthetic_challenge"}),
            json.dumps({"data_classification": "something_else",
                        "tables": {},
                        "disclaimer": "x", "source_sha256": "y",
                        "retrieved_at_utc": "z"}),
        ):
            with self.subTest(body=body[:60]):
                with tempfile.TemporaryDirectory() as tmp:
                    Path(tmp, "challenge_estate.json").write_text(
                        body, encoding="utf-8"
                    )
                    with mock.patch.object(
                        evidence, "EVIDENCE_DIR", Path(tmp)
                    ):
                        response = self.client.get("/api/evidence/challenge")
                self.assertEqual(response.status_code, 503)

    def test_public_wrong_classification_returns_503(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "public_financials.json").write_text(
                json.dumps({
                    "data_classification": "official_synthetic_challenge",
                    "rows": [], "disclaimer": "x", "source_sha256": "y",
                    "retrieved_at_utc": "z",
                }),
                encoding="utf-8",
            )
            with mock.patch.object(evidence, "EVIDENCE_DIR", Path(tmp)):
                response = self.client.get("/api/evidence/public")
        self.assertEqual(response.status_code, 503)


def _public_payload(**overrides):
    payload = {
        "source_url": "https://reports.bayer.com/example",
        "source_title": "title",
        "source_snapshot": "snapshot.html",
        "source_sha256": "ab" * 32,
        "retrieved_at_utc": "2026-11-07T00:00:00+00:00",
        "data_classification": "public_reported_actual",
        "disclaimer": "x",
        "unit": "EUR million",
        "grain": "product x fiscal_year",
        "rows": [
            {"product_name": "Nubeqa", "year": 2024,
             "sales_eur_million": 1523, "source_table": "t",
             "source_row_label": "Nubeqa"},
        ],
    }
    payload.update(overrides)
    return payload


def _challenge_payload(**table_overrides):
    tables = {
        name: [{"asset_id": "X"}] for name in (
            "Analytics_Assets", "Semantic_Models", "Owners", "KPI_Catalog",
            "Asset_KPI_Map", "Asset_Usage", "Lineage_Edges",
            "Governance_Signals", "Migration_Backlog", "Data_Quality",
            "Governance_Rules",
        )
    }
    tables.update(table_overrides)
    return {
        "source_file": "pack.xlsx",
        "source_sha256": "cd" * 32,
        "retrieved_at_utc": "2026-11-07T00:00:00+00:00",
        "data_classification": "official_synthetic_challenge",
        "disclaimer": "x",
        "tables": tables,
    }


class EvidenceNestedValidationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "runtime.sqlite"
        self.client = TestClient(create_app(runtime_db=db, include_synthetic=True))
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)

    def tearDown(self):
        self._tmp.cleanup()

    def _serve(self, filename, payload):
        Path(self._dir.name, filename).write_text(
            json.dumps(payload), encoding="utf-8"
        )
        with mock.patch.object(
            evidence, "EVIDENCE_DIR", Path(self._dir.name)
        ):
            return self.client.get(
                "/api/evidence/" + ("public" if "public" in filename
                                    else "challenge")
            )

    def test_valid_minimal_payloads_pass(self):
        self.assertEqual(
            self._serve("public_financials.json", _public_payload())
            .status_code, 200,
        )
        self.assertEqual(
            self._serve("challenge_estate.json", _challenge_payload())
            .status_code, 200,
        )

    def test_challenge_missing_table_503(self):
        payload = _challenge_payload()
        del payload["tables"]["Data_Quality"]
        self.assertEqual(
            self._serve("challenge_estate.json", payload).status_code, 503
        )

    def test_challenge_row_not_record_503(self):
        payload = _challenge_payload(Analytics_Assets=[None])
        self.assertEqual(
            self._serve("challenge_estate.json", payload).status_code, 503
        )

    def test_public_row_not_record_503(self):
        payload = _public_payload(rows=[None])
        self.assertEqual(
            self._serve("public_financials.json", payload).status_code, 503
        )

    def test_public_missing_column_503(self):
        row = {"product_name": "Nubeqa", "year": 2024,
               "sales_eur_million": 1523, "source_table": "t"}
        payload = _public_payload(rows=[row])
        self.assertEqual(
            self._serve("public_financials.json", payload).status_code, 503
        )

    def test_public_nan_sales_503(self):
        payload = _public_payload(rows=[
            {"product_name": "Nubeqa", "year": 2024,
             "sales_eur_million": float("nan"), "source_table": "t",
             "source_row_label": "Nubeqa"},
        ])
        self.assertEqual(
            self._serve("public_financials.json", payload).status_code, 503
        )

    def test_public_duplicate_product_year_503(self):
        row = {"product_name": "Nubeqa", "year": 2024,
               "sales_eur_million": 1, "source_table": "t",
               "source_row_label": "Nubeqa"}
        payload = _public_payload(rows=[row, dict(row)])
        self.assertEqual(
            self._serve("public_financials.json", payload).status_code, 503
        )

    def test_public_bool_year_and_sales_503(self):
        row = {"product_name": "Nubeqa", "year": True,
               "sales_eur_million": 1, "source_table": "t",
               "source_row_label": "Nubeqa"}
        self.assertEqual(
            self._serve(
                "public_financials.json", _public_payload(rows=[row])
            ).status_code, 503,
        )
        row["year"] = 2024
        row["sales_eur_million"] = False
        self.assertEqual(
            self._serve(
                "public_financials.json", _public_payload(rows=[row])
            ).status_code, 503,
        )

    def test_public_non_bayer_url_503(self):
        payload = _public_payload(source_url="https://example.com/x")
        self.assertEqual(
            self._serve("public_financials.json", payload).status_code, 503
        )
        payload = _public_payload(source_url="http://reports.bayer.com/x")
        self.assertEqual(
            self._serve("public_financials.json", payload).status_code, 503
        )

    def test_bad_sha_503(self):
        for bad in ("xyz", "ab" * 31, "AB" * 32, 123):
            with self.subTest(bad=bad):
                payload = _public_payload(source_sha256=bad)
                self.assertEqual(
                    self._serve("public_financials.json", payload)
                    .status_code, 503,
                )


if __name__ == "__main__":
    unittest.main()
