"""Lead-authored acceptance contract for the local synthetic vertical slice."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads(
    (ROOT / "tests" / "fixtures" / "demo_scenarios.json").read_text(encoding="utf-8")
)["cases"]


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        from smart_librarian.api.app import create_app

        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.demo = self.directory / "demo"
        shutil.copytree(ROOT / "data" / "demo_v1", self.demo)
        self.client = TestClient(create_app(
            demo_dir=self.demo, runtime_db=self.directory / "runtime.sqlite"
        ))

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def session(self, user="DEMO-USER-GLOBAL"):
        response = self.client.post("/api/sessions", json={"user_id": user})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["session_id"]

    def submit(self, case):
        user = case["user_id"]
        session_id = self.session(user)
        response = self.client.post(
            f"/api/sessions/{session_id}/intent",
            json={"user_id": user, "intent": case["confirmed_intent"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return session_id, response.json()

    def approve(self, session_id, user, proposal):
        return self.client.post(f"/api/sessions/{session_id}/approval", json={
            "user_id": user, "proposal_id": proposal["proposal_id"],
            "spec_hash": proposal["spec_hash"], "decision": "approve",
        })

    def report(self, session_id, user):
        return self.client.get(
            f"/api/sessions/{session_id}/report", params={"user_id": user}
        )

    def test_six_business_paths(self):
        for case in CASES:
            with self.subTest(case=case["case_id"]):
                if case["confirmed_intent"] is None:
                    sid = self.session(case["user_id"])
                    response = self.client.post(f"/api/sessions/{sid}/messages", json={
                        "user_id": case["user_id"], "text": case["request_text"],
                        "use_llm": False,
                    })
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["outcome"], "CLARIFY")
                    self.assertIsNone(response.json().get("proposal"))
                    continue
                sid, state = self.submit(case)
                expected = case["expected"]
                self.assertEqual(state["outcome"], expected["outcome"])
                if expected.get("must_not_generate_report"):
                    self.assertIsNone(state.get("proposal"))
                    self.assertEqual(self.report(sid, case["user_id"]).status_code, 409)
                    if case["case_id"] == "access_denied":
                        self.assertNotIn("Nubeqa Germany Monthly Net Sales", json.dumps(state))
                        self.assertNotIn("107000", json.dumps(state))
                    continue
                proposal = state["proposal"]
                self.assertEqual(len(proposal["spec_hash"]), 64)
                self.assertTrue(state["evidence"])
                if "asset_id" in expected:
                    self.assertEqual(proposal["spec"]["source_asset_id"], expected["asset_id"])
                if expected.get("requires_approval"):
                    self.assertEqual(self.report(sid, case["user_id"]).status_code, 409)
                    approved = self.approve(sid, case["user_id"], proposal)
                    self.assertEqual(approved.status_code, 200, approved.text)
                response = self.report(sid, case["user_id"])
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                for metric, key in [
                    ("DEMO-NET-SALES", "net_sales_eur"),
                    ("DEMO-FORECAST", "forecast_eur"),
                ]:
                    if key in expected:
                        self.assertEqual([r[metric] for r in result["rows"]], expected[key])
                    if "total_" + key in expected:
                        self.assertEqual(result["totals"][metric], expected["total_" + key])

    def test_approval_tampering_and_cross_session_identity(self):
        case = next(c for c in CASES if c["case_id"] == "build")
        sid, state = self.submit(case)
        bad = {**state["proposal"], "spec_hash": "0" * 64}
        self.assertEqual(self.approve(sid, case["user_id"], bad).status_code, 409)
        self.assertEqual(self.report(sid, "DEMO-USER-GLOBAL").status_code, 403)
        response = self.client.get(
            f"/api/sessions/{sid}", params={"user_id": "DEMO-USER-GLOBAL"}
        )
        self.assertEqual(response.status_code, 403)

    def test_changed_request_invalidates_old_approval(self):
        case = next(c for c in CASES if c["case_id"] == "build")
        sid, state = self.submit(case)
        old = state["proposal"]
        self.assertEqual(self.approve(sid, case["user_id"], old).status_code, 200)
        changed = {**case["confirmed_intent"], "months": ["2026-01-01"]}
        response = self.client.post(f"/api/sessions/{sid}/intent", json={
            "user_id": case["user_id"], "intent": changed,
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.report(sid, case["user_id"]).status_code, 409)
        self.assertEqual(self.approve(sid, case["user_id"], old).status_code, 409)

    def test_rejection_and_audit(self):
        case = next(c for c in CASES if c["case_id"] == "build")
        sid, state = self.submit(case)
        proposal = state["proposal"]
        response = self.client.post(f"/api/sessions/{sid}/approval", json={
            "user_id": case["user_id"], "proposal_id": proposal["proposal_id"],
            "spec_hash": proposal["spec_hash"], "decision": "reject",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.report(sid, case["user_id"]).status_code, 409)
        audit = self.client.get(
            f"/api/sessions/{sid}/audit", params={"user_id": case["user_id"]}
        )
        self.assertEqual(audit.status_code, 200, audit.text)
        self.assertIn("reject", json.dumps(audit.json()).lower())

    def test_catalog_change_invalidates_approved_report(self):
        case = next(c for c in CASES if c["case_id"] == "build")
        sid, state = self.submit(case)
        self.assertEqual(self.approve(sid, case["user_id"], state["proposal"]).status_code, 200)
        path = self.demo / "catalog.json"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertEqual(self.report(sid, case["user_id"]).status_code, 409)

    def test_unsupported_scope_never_silently_clamped(self):
        case = next(c for c in CASES if c["case_id"] == "reuse")
        for replacement in [
            {"months": ["2026-01-01", "2026-12-01"]},
            {"product_ids": ["UNKNOWN-PRODUCT"]},
            {"grain": "week"},
            {"metric_ids": ["DEMO-NET-SALES", "UNKNOWN-MARGIN"]},
        ]:
            with self.subTest(replacement=replacement):
                altered = {**case, "confirmed_intent": {
                    **case["confirmed_intent"], **replacement
                }}
                sid, state = self.submit(altered)
                self.assertEqual(state["outcome"], "NEEDS_REVIEW")
                self.assertIsNone(state.get("proposal"))
                self.assertEqual(self.report(sid, case["user_id"]).status_code, 409)

    def test_multi_market_access_is_all_or_nothing(self):
        case = next(c for c in CASES if c["case_id"] == "build")
        altered = {**case, "confirmed_intent": {
            **case["confirmed_intent"], "market_ids": ["FI", "DE"],
        }}
        _, state = self.submit(altered)
        self.assertEqual(state["outcome"], "ACCESS_DENIED")
        self.assertIsNone(state.get("proposal"))


if __name__ == "__main__":
    unittest.main()
