"""Multi-domain integration: routing, isolation, reuse, actor approvals.

Behavior only - numeric contract assertions live in the lead-authored
calculation tests.
"""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]

LOGISTICS_INTENT = {
    "product_ids": ["DEMO-L-COLD"],
    "market_ids": ["DE"],
    "metric_ids": ["DEMO-DELIVERED", "DEMO-ON-TIME-PCT", "DEMO-LEAD-DAYS"],
    "months": ["2026-01-01", "2026-02-01", "2026-03-01"],
    "grain": "month",
}
SALES_INTENT = {
    "product_ids": ["DEMO-P-NUB"],
    "market_ids": ["DE"],
    "metric_ids": ["DEMO-NET-SALES"],
    "months": ["2026-01-01", "2026-02-01", "2026-03-01"],
    "grain": "month",
}


class MultiDomainTests(unittest.TestCase):
    def setUp(self):
        from smart_librarian.api.app import create_app

        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(
            demo_dir=ROOT / "data" / "demo_v1",
            runtime_db=Path(self.temp.name) / "runtime.sqlite",
        ))

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def session(self, user="DEMO-USER-GLOBAL", domain="sales"):
        response = self.client.post(
            "/api/sessions", json={"user_id": user, "domain_id": domain}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["session_id"]

    def confirm(self, sid, user, intent):
        response = self.client.post(
            f"/api/sessions/{sid}/intent",
            json={"user_id": user, "intent": intent},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def approve(self, sid, user, proposal, actor="DEMO-APPROVER"):
        return self.client.post(
            f"/api/sessions/{sid}/approval",
            json={
                "user_id": user,
                "proposal_id": proposal["proposal_id"],
                "spec_hash": proposal["spec_hash"],
                "decision": "approve",
                "actor_user_id": actor,
            },
        )

    def render(self, sid, user):
        return self.client.get(
            f"/api/sessions/{sid}/report", params={"user_id": user}
        )

    def assets(self, user="DEMO-USER-GLOBAL", domain="sales"):
        response = self.client.get(
            "/api/assets", params={"user_id": user, "domain_id": domain}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["assets"]

    def publish_logistics(self):
        sid = self.session(domain="logistics")
        state = self.confirm(sid, "DEMO-USER-GLOBAL", LOGISTICS_INTENT)
        self.assertEqual(state["outcome"], "PROPOSE_BUILD")
        response = self.approve(sid, "DEMO-USER-GLOBAL", state["proposal"])
        self.assertEqual(response.status_code, 200, response.text)
        result = self.render(sid, "DEMO-USER-GLOBAL")
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_domains_endpoint(self):
        response = self.client.get("/api/domains")
        self.assertEqual(response.status_code, 200, response.text)
        domains = {d["domain_id"]: d for d in response.json()["domains"]}
        self.assertEqual(
            set(domains), {"sales", "logistics", "quality"}
        )
        self.assertEqual(
            domains["sales"]["dimension_labels"]["products"], "Products"
        )
        self.assertEqual(
            domains["logistics"]["dimension_labels"]["products"],
            "Distribution lanes",
        )

    def test_per_domain_catalog_metrics(self):
        response = self.client.get(
            "/api/catalog",
            params={"user_id": "DEMO-USER-GLOBAL", "domain_id": "logistics"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        metric_ids = [
            m["metric_id"] for m in response.json()["choices"]["metrics"]
        ]
        self.assertIn("DEMO-DELIVERED", metric_ids)
        self.assertNotIn("DEMO-NET-SALES", metric_ids)
        self.assertEqual(response.json()["choices"]["domain_id"], "logistics")

    def test_session_routing_uses_stored_domain(self):
        sid = self.session(domain="quality")
        state = self.client.get(
            f"/api/sessions/{sid}", params={"user_id": "DEMO-USER-GLOBAL"}
        ).json()
        self.assertEqual(state.get("domain_id"), "quality")
        # No domain is supplied on session-bound calls; routing is stored.
        confirmed = self.confirm(sid, "DEMO-USER-GLOBAL", {
            "product_ids": ["DEMO-Q-TAB"], "market_ids": ["DE"],
            "metric_ids": ["DEMO-INSPECTED"],
            "months": ["2026-01-01"], "grain": "month",
        })
        self.assertEqual(confirmed["outcome"], "PROPOSE_BUILD")
        self.assertEqual(
            confirmed["proposal"]["spec"]["domain_id"], "quality"
        )

    def test_operational_build_render_register_reuse(self):
        published = self.publish_logistics()
        asset_id = published["registered_asset_id"]
        self.assertTrue(asset_id.startswith("GEN-"))
        self.assertEqual(published["asset"]["domain_id"], "logistics")
        self.assertEqual(
            published["asset"]["destination"]["kind"], "local_asset"
        )
        self.assertTrue(published["asset"]["destination"]["implemented"])
        # Next session in the same domain resolves to REUSE.
        sid = self.session(domain="logistics")
        state = self.confirm(sid, "DEMO-USER-GLOBAL", LOGISTICS_INTENT)
        self.assertEqual(state["outcome"], "REUSE")
        self.assertEqual(
            state["proposal"]["spec"]["source_asset_id"], asset_id
        )

    def test_cross_domain_assets_invisible(self):
        published = self.publish_logistics()
        asset_id = published["registered_asset_id"]
        sales_ids = [a["asset_id"] for a in self.assets(domain="sales")]
        self.assertNotIn(asset_id, sales_ids)
        detail = self.client.get(
            f"/api/assets/{asset_id}",
            params={"user_id": "DEMO-USER-GLOBAL", "domain_id": "sales"},
        )
        self.assertEqual(detail.status_code, 404)
        quality_ids = [a["asset_id"] for a in self.assets(domain="quality")]
        self.assertNotIn(asset_id, quality_ids)

    def test_cross_domain_metrics_needs_review(self):
        # Sales metric inside a logistics intent is unknown there.
        intent = {**LOGISTICS_INTENT, "metric_ids": ["DEMO-NET-SALES"]}
        sid = self.session(domain="logistics")
        state = self.confirm(sid, "DEMO-USER-GLOBAL", intent)
        self.assertEqual(state["outcome"], "NEEDS_REVIEW")
        self.assertIsNone(state.get("proposal"))

    def test_sales_domain_unchanged(self):
        sid = self.session()
        state = self.confirm(sid, "DEMO-USER-GLOBAL", SALES_INTENT)
        self.assertEqual(state["outcome"], "REUSE")
        self.assertEqual(
            state["proposal"]["spec"]["source_asset_id"],
            "DEMO-REPORT-NUB-DE",
        )
        result = self.render(sid, "DEMO-USER-GLOBAL")
        self.assertEqual(result.status_code, 200, result.text)

    def test_fi_market_restriction_in_operational_domain(self):
        published = self.publish_logistics()
        asset_id = published["registered_asset_id"]
        response = self.client.get(
            f"/api/assets/{asset_id}",
            params={"user_id": "DEMO-USER-FI", "domain_id": "logistics"},
        )
        self.assertEqual(response.status_code, 404)
        # FI-only intent is allowed and produces its own proposal.
        intent = {**LOGISTICS_INTENT, "market_ids": ["FI"]}
        sid = self.session(user="DEMO-USER-FI", domain="logistics")
        state = self.confirm(sid, "DEMO-USER-FI", intent)
        self.assertEqual(state["outcome"], "PROPOSE_BUILD")


class GovernanceActorTests(unittest.TestCase):
    def setUp(self):
        from smart_librarian.api.app import create_app

        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(
            demo_dir=ROOT / "data" / "demo_v1",
            runtime_db=Path(self.temp.name) / "runtime.sqlite",
        ))
        self.sid = self.client.post(
            "/api/sessions",
            json={"user_id": "DEMO-USER-GLOBAL", "domain_id": "sales"},
        ).json()["session_id"]
        intent = {
            "product_ids": ["DEMO-P-NUB"], "market_ids": ["DE"],
            "metric_ids": ["DEMO-NET-SALES", "DEMO-FORECAST"],
            "months": ["2026-01-01"], "grain": "month",
        }
        self.state = self.client.post(
            f"/api/sessions/{self.sid}/intent",
            json={"user_id": "DEMO-USER-GLOBAL", "intent": intent},
        ).json()
        self.proposal = self.state["proposal"]

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def approve_with(self, actor):
        return self.client.post(
            f"/api/sessions/{self.sid}/approval",
            json={
                "user_id": "DEMO-USER-GLOBAL",
                "proposal_id": self.proposal["proposal_id"],
                "spec_hash": self.proposal["spec_hash"],
                "decision": "approve",
                "actor_user_id": actor,
            },
        )

    def test_governance_actors_endpoint(self):
        response = self.client.get("/api/governance-actors")
        self.assertEqual(response.status_code, 200, response.text)
        actors = {a["actor_id"]: a for a in response.json()["actors"]}
        self.assertIn("approver", actors["DEMO-APPROVER"]["roles"])
        self.assertIn("steward", actors["DEMO-STEWARD"]["roles"])

    def test_unknown_actor_forbidden(self):
        self.assertEqual(self.approve_with("NOPE").status_code, 403)

    def test_requester_identity_as_actor_forbidden(self):
        self.assertEqual(
            self.approve_with("DEMO-USER-GLOBAL").status_code, 403
        )

    def test_steward_only_actor_forbidden(self):
        self.assertEqual(self.approve_with("DEMO-STEWARD").status_code, 403)

    def test_approver_succeeds_and_audit_binds_actor(self):
        response = self.approve_with("DEMO-APPROVER")
        self.assertEqual(response.status_code, 200, response.text)
        audit = self.client.get(
            f"/api/sessions/{self.sid}/audit",
            params={"user_id": "DEMO-USER-GLOBAL"},
        ).json()["events"]
        approval = [e for e in audit if e["event_type"] == "approval_approve"]
        self.assertEqual(len(approval), 1)
        self.assertEqual(approval[0]["user_id"], "DEMO-APPROVER")
        self.assertEqual(
            approval[0]["detail"]["requester_user_id"], "DEMO-USER-GLOBAL"
        )
        self.assertEqual(approval[0]["detail"]["actor_roles"], ["approver"])

    def test_repeat_approval_still_enforces_actor_scope(self):
        self.assertEqual(self.approve_with("DEMO-APPROVER").status_code, 200)
        # A steward replaying the same decision is still rejected.
        self.assertEqual(self.approve_with("DEMO-STEWARD").status_code, 403)
        # The proper approver gets an idempotent 200 with no second audit.
        self.assertEqual(self.approve_with("DEMO-APPROVER").status_code, 200)
        audit = self.client.get(
            f"/api/sessions/{self.sid}/audit",
            params={"user_id": "DEMO-USER-GLOBAL"},
        ).json()["events"]
        approval = [e for e in audit if e["event_type"] == "approval_approve"]
        self.assertEqual(len(approval), 1)


if __name__ == "__main__":
    unittest.main()
