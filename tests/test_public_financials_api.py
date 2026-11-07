"""Real-data-only API transport tests (no numeric gold answers).

Verifies the default create_app mode: only the governed public financials
domain mounts, domain defaults resolve, synthetic routes fail closed and the
public snapshot endpoint serves the frozen payload.
"""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from smart_librarian.api.app import ConfigurationError, create_app
from smart_librarian.settings import REPO_ROOT


class RealOnlyApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "runtime.sqlite"
        self.client = TestClient(create_app(runtime_db=db))

    def tearDown(self):
        self._tmp.cleanup()

    def test_domains_real_data_only_public_only(self):
        payload = self.client.get("/api/domains").json()
        self.assertTrue(payload["real_data_only"])
        self.assertTrue(payload["simulated"])
        domains = payload["domains"]
        self.assertEqual([d["domain_id"] for d in domains], ["public_sales"])
        self.assertEqual(
            domains[0]["data_classification"], "public_reported_actual"
        )

    def test_health_default_domain(self):
        payload = self.client.get("/api/health").json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["domains"], ["public_sales"])
        self.assertTrue(payload["real_data_only"])
        self.assertTrue(payload["dataset_id"])

    def test_default_users_and_catalog(self):
        users = self.client.get("/api/demo-users").json()["users"]
        self.assertIn(
            "DEMO-USER-GLOBAL", {u["user_id"] for u in users}
        )
        catalog = self.client.get(
            "/api/catalog", params={"user_id": "DEMO-USER-GLOBAL"}
        ).json()
        choices = catalog["choices"]
        self.assertEqual(choices["period_label"], "Reporting periods")
        self.assertEqual(choices["time_column"], "period")
        self.assertFalse(choices["synthetic_record"])
        self.assertEqual(
            choices["data_classification"], "public_reported_actual"
        )
        self.assertEqual(len(choices["periods"]), 10)
        self.assertEqual(
            len(choices["months"]), len(choices["periods"])
        )
        kinds = {p["period_kind"] for p in choices["periods"]}
        self.assertEqual(kinds, {"year", "quarter", "half_year"})

    def test_session_create_default_domain(self):
        response = self.client.post(
            "/api/sessions", json={"user_id": "DEMO-USER-GLOBAL"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        session_id = response.json()["session_id"]
        state = self.client.get(
            f"/api/sessions/{session_id}",
            params={"user_id": "DEMO-USER-GLOBAL"},
        )
        self.assertEqual(state.status_code, 200, state.text)
        self.assertEqual(state.json()["domain_id"], "public_sales")

    def test_synthetic_domains_fail_closed(self):
        for domain_id in ("sales", "logistics", "quality"):
            with self.subTest(domain_id=domain_id):
                response = self.client.post(
                    "/api/sessions",
                    json={"user_id": "DEMO-USER-GLOBAL",
                          "domain_id": domain_id},
                )
                self.assertEqual(response.status_code, 404)
                response = self.client.get(
                    "/api/assets",
                    params={"user_id": "DEMO-USER-GLOBAL",
                            "domain_id": domain_id},
                )
                self.assertEqual(response.status_code, 404)

    def test_challenge_evidence_404_public_legacy_still_served(self):
        self.assertEqual(
            self.client.get("/api/evidence/challenge").status_code, 404
        )
        response = self.client.get("/api/evidence/public")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data_classification"],
            "public_reported_actual",
        )

    def test_governance_actors_public_only(self):
        actors = self.client.get("/api/governance-actors").json()["actors"]
        self.assertEqual(
            {a["actor_id"] for a in actors}, {"DEMO-PUBLIC-APPROVER"}
        )

    def test_public_financials_snapshot_endpoint(self):
        response = self.client.get("/api/public-financials")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(
            payload["data_classification"], "public_reported_actual"
        )
        self.assertEqual(len(payload["rows"]), 150)
        self.assertEqual(len(payload["periods"]), 10)
        self.assertTrue(payload["sources"])
        for source in payload["sources"]:
            self.assertTrue(source["source_url"].startswith("https://"))
            self.assertTrue(source["source_sha256"])
        for field in ("unit", "grain", "disclaimer"):
            self.assertTrue(payload.get(field))

    def test_stale_synthetic_session_rejected(self):
        legacy = TestClient(
            create_app(runtime_db=self._tmp.name + "/runtime.sqlite",
                       include_synthetic=True)
        )
        sid = legacy.post(
            "/api/sessions",
            json={"user_id": "DEMO-USER-GLOBAL", "domain_id": "sales"},
        ).json()["session_id"]
        response = self.client.get(
            f"/api/sessions/{sid}", params={"user_id": "DEMO-USER-GLOBAL"}
        )
        self.assertEqual(response.status_code, 404)

    def test_runtime_db_guard_covers_dataset_dir(self):
        with self.assertRaises(ConfigurationError):
            create_app(
                runtime_db=(
                    REPO_ROOT / "data" / "public_financials_v2"
                    / "runtime.sqlite"
                )
            )
        with self.assertRaises(ConfigurationError):
            create_app(
                runtime_db=(REPO_ROOT / "data" / "evidence" / "x.sqlite")
            )

    def test_legacy_mode_defaults_to_sales(self):
        legacy = TestClient(
            create_app(runtime_db=self._tmp.name + "/legacy.sqlite",
                       include_synthetic=True)
        )
        sid = legacy.post(
            "/api/sessions", json={"user_id": "DEMO-USER-GLOBAL"}
        ).json()["session_id"]
        state = legacy.get(
            f"/api/sessions/{sid}", params={"user_id": "DEMO-USER-GLOBAL"}
        ).json()
        self.assertEqual(state["domain_id"], "sales")
        catalog = legacy.get(
            "/api/catalog", params={"user_id": "DEMO-USER-GLOBAL"}
        ).json()
        self.assertEqual(catalog["choices"]["domain_id"], "sales")
        domains = legacy.get("/api/domains").json()["domains"]
        self.assertEqual(domains[0]["domain_id"], "public_sales")

    def test_confirm_approve_render_roundtrip(self):
        catalog = self.client.get(
            "/api/catalog", params={"user_id": "DEMO-USER-GLOBAL"}
        ).json()["choices"]
        product_id = catalog["products"][0]["product_id"]
        sid = self.client.post(
            "/api/sessions", json={"user_id": "DEMO-USER-GLOBAL"}
        ).json()["session_id"]
        confirmed = self.client.post(
            f"/api/sessions/{sid}/intent",
            json={
                "user_id": "DEMO-USER-GLOBAL",
                "intent": {
                    "product_ids": [product_id],
                    "market_ids": ["GLOBAL"],
                    "metric_ids": ["PUBLIC-REPORTED-SALES"],
                    "months": ["2025"],
                    "grain": "year",
                },
            },
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        state = confirmed.json()
        self.assertEqual(state["outcome"], "PROPOSE_BUILD")
        proposal = state["proposal"]
        self.assertEqual(proposal["approval_status"], "pending")
        spec = proposal["spec"]
        self.assertEqual(spec["model_id"], "PUBLIC-MODEL-FINANCIALS")
        self.assertFalse(spec["synthetic_record"])
        decided = self.client.post(
            f"/api/sessions/{sid}/approval",
            json={
                "user_id": "DEMO-USER-GLOBAL",
                "proposal_id": proposal["proposal_id"],
                "spec_hash": proposal["spec_hash"],
                "decision": "approve",
                "actor_user_id": "DEMO-PUBLIC-APPROVER",
            },
        )
        self.assertEqual(decided.status_code, 200, decided.text)
        report = self.client.get(
            f"/api/sessions/{sid}/report",
            params={"user_id": "DEMO-USER-GLOBAL"},
        )
        self.assertEqual(report.status_code, 200, report.text)
        payload = report.json()
        self.assertEqual(payload["time_column"], "period")
        self.assertEqual(
            payload["data_classification"], "public_reported_actual"
        )
        self.assertFalse(payload["synthetic_record"])
        for row in payload["rows"]:
            self.assertIn("period", row)
            self.assertIn("source_id", row)
        self.assertTrue(payload["registered_asset_id"])


if __name__ == "__main__":
    unittest.main()
