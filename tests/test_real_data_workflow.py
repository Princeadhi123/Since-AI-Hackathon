import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from smart_librarian.api.app import create_app
from smart_librarian.reporting.exports import build_report_bundle, export_report_html
from smart_librarian.reporting.powerbi import build_powerbi_import_bundle
from smart_librarian.reporting.public_annual import METRIC_ID, PRODUCT_IDS


class RealDataWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(
            runtime_db=Path(self.temp.name) / "runtime.sqlite",
            include_synthetic=True,
        ))
        self.user = "DEMO-USER-GLOBAL"
        self.intent = {
            "product_ids": ["PUBLIC-NUBEQA"], "market_ids": ["GLOBAL"],
            "months": ["2025"], "metric_ids": [METRIC_ID], "grain": "year",
        }

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def session(self, user=None):
        response = self.client.post("/api/sessions", json={
            "user_id": user or self.user, "domain_id": "public_sales",
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["session_id"]

    def confirm(self, sid, intent=None, user=None):
        response = self.client.post(f"/api/sessions/{sid}/intent", json={
            "user_id": user or self.user, "intent": intent or self.intent,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def report(self, sid):
        return self.client.get(f"/api/sessions/{sid}/report", params={"user_id": self.user})

    def approve(self, sid, proposal):
        response = self.client.post(f"/api/sessions/{sid}/approval", json={
            "user_id": self.user, "actor_user_id": "DEMO-PUBLIC-APPROVER",
            "proposal_id": proposal["proposal_id"], "spec_hash": proposal["spec_hash"],
            "decision": "approve",
        })
        self.assertEqual(response.status_code, 200, response.text)

    def test_real_request_evidence_approval_report_and_cross_session_reuse(self):
        sid = self.session()
        response = self.client.post(f"/api/sessions/{sid}/messages", json={
            "user_id": self.user, "use_llm": False,
            "text": "Show global reported sales for Nubeqa in 2025",
        })
        self.assertEqual(response.status_code, 200, response.text)
        extracted = response.json()
        self.assertEqual(extracted["outcome"], "CONFIRM_INTENT")
        self.assertEqual(extracted["partial_intent"], self.intent)
        state = self.confirm(sid)
        self.assertEqual(state["outcome"], "PROPOSE_BUILD")
        self.assertEqual(self.report(sid).status_code, 409)
        spec = state["proposal"]["spec"]
        self.assertFalse(spec["synthetic_record"])
        self.assertEqual(spec["data_classification"], "public_reported_actual")
        self.assertEqual(spec["time_column"], "fiscal_year")
        self.assertTrue(any(e["kind"] == "public_source" for e in state["evidence"]))
        self.approve(sid, state["proposal"])
        response = self.report(sid)
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        self.assertEqual(report["totals"], {METRIC_ID: 2385})
        self.assertEqual(report["rows"][0]["fiscal_year"], 2025)
        self.assertNotIn("month", report["rows"][0])
        self.assertEqual(report["units"][METRIC_ID], "EUR million")
        self.assertEqual(
            report["source_provenance"]["source_sha256"],
            "d4339d4e56a76cd9d0f081b0ad5bce1d2124bb035ba7d504c0d33199425b0d24",
        )
        reused = self.confirm(self.session())
        self.assertEqual(reused["outcome"], "REUSE")
        self.assertEqual(reused["proposal"]["approval_status"], "not_required")
        self.assertEqual(
            reused["proposal"]["spec"]["source_asset_id"], report["registered_asset_id"]
        )

    def test_real_multi_year_report_and_exports_preserve_all_eight_source_values(self):
        intent = {
            **self.intent, "product_ids": list(PRODUCT_IDS.values()), "months": ["2024", "2025"],
        }
        sid = self.session()
        state = self.confirm(sid, intent)
        self.approve(sid, state["proposal"])
        response = self.report(sid)
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        expected = {
            ("Nubeqa", 2024): 1523, ("Nubeqa", 2025): 2385,
            ("Kerendia", 2024): 463, ("Kerendia", 2025): 829,
            ("Eylea", 2024): 3306, ("Eylea", 2025): 3110,
            ("Xarelto", 2024): 3480, ("Xarelto", 2025): 2344,
        }
        self.assertEqual(report["totals"], {})
        self.assertEqual(
            {(row["product_name"], row["fiscal_year"]): row[METRIC_ID] for row in report["rows"]},
            expected,
        )
        for builder, filename in (
            (build_report_bundle, "report.csv"), (build_powerbi_import_bundle, "report.csv"),
        ):
            with zipfile.ZipFile(io.BytesIO(builder(report))) as archive:
                rows = list(csv.DictReader(io.StringIO(archive.read(filename).decode("utf-8"))))
                self.assertEqual(len(rows), 8)
                self.assertEqual(
                    {(r["product_name"], int(r["fiscal_year"])): int(r[METRIC_ID]) for r in rows},
                    expected,
                )
                self.assertNotIn("month", rows[0])
        page = export_report_html(report)
        self.assertIn("EUR million", page)
        self.assertIn("2385".replace("2385", "2,385"), page)
        self.assertNotIn("Synthetic demo data - not real business figures.", page)

    def test_unavailable_requirements_are_not_replaced_by_real_looking_values(self):
        for override, expected in (
            ({"grain": "month"}, "NEEDS_REVIEW"),
            ({"months": ["2026"]}, "NEEDS_REVIEW"),
            ({"metric_ids": ["DEMO-FORECAST"]}, "NEEDS_REVIEW"),
            ({"market_ids": ["DE"]}, "ACCESS_DENIED"),
        ):
            sid = self.session()
            state = self.confirm(sid, {**self.intent, **override})
            self.assertEqual(state["outcome"], expected)
            self.assertIsNone(state["proposal"])
            self.assertEqual(self.report(sid).status_code, 409)

    def test_country_limited_demo_identity_cannot_read_global_public_workflow(self):
        sid = self.session("DEMO-USER-FI")
        state = self.confirm(sid, user="DEMO-USER-FI")
        self.assertEqual(state["outcome"], "ACCESS_DENIED")
        self.assertEqual(state["evidence"], [])


if __name__ == "__main__":
    unittest.main()
