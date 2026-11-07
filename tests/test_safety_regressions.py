"""Acceptance regressions for snapshot coherence and multi-turn confirmation."""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from smart_librarian.catalog.store import DemoCatalog
from smart_librarian.domain import decision
from smart_librarian.domain.executable_contract import calculation_contract_gaps

ROOT = Path(__file__).resolve().parents[1]
INTENT = {
    "product_ids": ["DEMO-P-NUB"], "market_ids": ["DE"],
    "metric_ids": ["DEMO-NET-SALES"], "months": ["2026-01-01"], "grain": "month",
}


class SafetyRegressionTests(unittest.TestCase):
    def setUp(self):
        from smart_librarian.api.app import create_app

        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.demo = self.path / "demo"
        shutil.copytree(ROOT / "data" / "demo_v1", self.demo)
        self.client = TestClient(create_app(
            demo_dir=self.demo, runtime_db=self.path / "runtime.sqlite"
        ))
        response = self.client.post("/api/sessions", json={"user_id": "DEMO-USER-GLOBAL"})
        self.sid = response.json()["session_id"]

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def message(self, text):
        response = self.client.post(f"/api/sessions/{self.sid}/messages", json={
            "user_id": "DEMO-USER-GLOBAL", "text": text, "use_llm": False,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_followup_completes_retained_intent(self):
        first = self.message("Nubeqa Germany Net Sales")
        self.assertEqual(first["outcome"], "CLARIFY")
        second = self.message("January through March 2026")
        self.assertEqual(second["outcome"], "CONFIRM_INTENT")
        self.assertEqual(second["partial_intent"]["product_ids"], ["DEMO-P-NUB"])
        self.assertEqual(second["partial_intent"]["market_ids"], ["DE"])
        self.assertEqual(len(second["partial_intent"]["months"]), 3)
        self.assertIsNone(second.get("proposal"))

    def test_catalog_drift_before_new_proposal_is_not_blessed(self):
        catalog_path = self.demo / "catalog.json"
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        data["models"][0]["refresh_status"] = "failed"
        catalog_path.write_text(json.dumps(data), encoding="utf-8")
        response = self.client.post(f"/api/sessions/{self.sid}/intent", json={
            "user_id": "DEMO-USER-GLOBAL", "intent": INTENT,
        })
        self.assertEqual(response.status_code, 409, response.text)

    def test_reusable_candidate_beats_lexically_earlier_extension(self):
        catalog = DemoCatalog(self.demo)
        report = catalog.catalog["reports"][0]
        report["metric_ids"] = ["DEMO-FORECAST"]
        exact = copy.deepcopy(report)
        exact["asset_id"] = "ZZZ-EXACT-REPORT"
        exact["metric_ids"] = ["DEMO-NET-SALES"]
        catalog.catalog["reports"].append(exact)
        catalog.catalog["lineage"].append({
            "source_id": "DEMO-MODEL-SALES", "target_id": exact["asset_id"],
            "relationship": "model_to_report",
        })
        result = decision.evaluate(
            catalog, catalog.user("DEMO-USER-GLOBAL"), INTENT, catalog.fingerprint()
        )
        self.assertEqual(result["outcome"], "REUSE")
        self.assertEqual(result["proposal"]["spec"]["source_asset_id"], exact["asset_id"])

    def test_fixed_engine_rejects_changed_semantic_contract(self):
        catalog = DemoCatalog(self.demo)
        self.assertEqual(calculation_contract_gaps(catalog), [])
        catalog.metric("DEMO-NET-SALES")["operator"] = "average"
        self.assertIn(
            "metric_contract_not_executable:DEMO-NET-SALES",
            calculation_contract_gaps(catalog),
        )
        result = decision.evaluate(
            catalog, catalog.user("DEMO-USER-GLOBAL"), INTENT, catalog.fingerprint()
        )
        self.assertEqual(result["outcome"], "NEEDS_REVIEW")
        self.assertIsNone(result.get("proposal"))

    def test_new_chat_clears_reusable_proposal(self):
        response = self.client.post(f"/api/sessions/{self.sid}/intent", json={
            "user_id": "DEMO-USER-GLOBAL", "intent": INTENT,
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["outcome"], "REUSE")
        updated = self.message("Actually I need a different report.")
        self.assertIsNone(updated.get("proposal"))
        report = self.client.get(
            f"/api/sessions/{self.sid}/report", params={"user_id": "DEMO-USER-GLOBAL"}
        )
        self.assertEqual(report.status_code, 409)


if __name__ == "__main__":
    unittest.main()
