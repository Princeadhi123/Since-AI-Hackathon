"""Phase 1 governed cross-session asset lifecycle tests.

A successful render of an approved PROPOSE_BUILD/PROPOSE_CHANGE proposal
publishes a deterministic generated asset into the runtime SQLite registry.
Approvals alone, failed renders, rejected proposals and stale sessions never
publish. Later sessions discover the asset via the runtime catalog overlay
and reach it through the normal decision flow (REUSE).
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]

BUILD_INTENT = {
    "product_ids": ["DEMO-P-KER"],
    "market_ids": ["FI"],
    "metric_ids": ["DEMO-NET-SALES", "DEMO-FORECAST"],
    "months": ["2026-01-01", "2026-02-01", "2026-03-01"],
    "grain": "month",
}
DE_ONLY_INTENT = {
    "product_ids": ["DEMO-P-KER"],
    "market_ids": ["DE"],
    "metric_ids": ["DEMO-NET-SALES", "DEMO-FORECAST"],
    "months": ["2026-04-01", "2026-05-01"],
    "grain": "month",
}


class AssetLifecycleTests(unittest.TestCase):
    def setUp(self):
        from smart_librarian.api.app import create_app

        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.demo = self.directory / "demo"
        shutil.copytree(ROOT / "data" / "demo_v1", self.demo)
        self.runtime_db = self.directory / "runtime.sqlite"
        self.create_app = create_app
        self.client = TestClient(create_app(
            demo_dir=self.demo, runtime_db=self.runtime_db
        ))

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    # -- helpers ------------------------------------------------------------

    def session(self, user="DEMO-USER-GLOBAL"):
        response = self.client.post("/api/sessions", json={"user_id": user})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["session_id"]

    def confirm(self, session_id, user, intent):
        response = self.client.post(
            f"/api/sessions/{session_id}/intent",
            json={"user_id": user, "intent": intent},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def approve(self, session_id, user, proposal):
        response = self.client.post(
            f"/api/sessions/{session_id}/approval",
            json={
                "user_id": user,
                "proposal_id": proposal["proposal_id"],
                "spec_hash": proposal["spec_hash"],
                "decision": "approve",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)

    def render(self, session_id, user):
        return self.client.get(
            f"/api/sessions/{session_id}/report", params={"user_id": user}
        )

    def assets(self, user="DEMO-USER-GLOBAL"):
        response = self.client.get("/api/assets", params={"user_id": user})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["assets"]

    def generated_assets(self, user="DEMO-USER-GLOBAL"):
        return [a for a in self.assets(user) if a["asset_id"].startswith("GEN-")]

    def publish(self, intent=BUILD_INTENT, user="DEMO-USER-GLOBAL"):
        sid = self.session(user)
        state = self.confirm(sid, user, intent)
        self.assertIn(state["outcome"], ("PROPOSE_BUILD", "PROPOSE_CHANGE"))
        self.approve(sid, user, state["proposal"])
        response = self.render(sid, user)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    # -- publication ----------------------------------------------------------

    def test_approved_render_publishes_asset(self):
        result = self.publish()
        asset_id = result["registered_asset_id"]
        self.assertTrue(asset_id.startswith("GEN-"), result)
        self.assertEqual(result["asset"]["asset_id"], asset_id)
        self.assertEqual(result["asset"]["lifecycle_status"], "active")
        self.assertEqual(result["asset"]["endorsement"], "promoted")
        self.assertEqual(result["asset"]["owner_id"], "DEMO-OWNER-001")
        assets = self.generated_assets()
        self.assertEqual([a["asset_id"] for a in assets], [asset_id])
        detail = self.client.get(
            f"/api/assets/{asset_id}", params={"user_id": "DEMO-USER-GLOBAL"}
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        # Public metadata must not leak the spec or requester identity.
        for key in ("spec", "spec_hash", "created_by"):
            self.assertNotIn(key, detail.json())
            self.assertNotIn(key, assets[0])

    def test_approval_alone_does_not_publish(self):
        sid = self.session()
        state = self.confirm(sid, "DEMO-USER-GLOBAL", BUILD_INTENT)
        self.approve(sid, "DEMO-USER-GLOBAL", state["proposal"])
        self.assertEqual(self.generated_assets(), [])

    def test_failed_and_rejected_render_do_not_publish(self):
        # Render attempted before approval fails and publishes nothing.
        sid = self.session()
        state = self.confirm(sid, "DEMO-USER-GLOBAL", BUILD_INTENT)
        self.assertEqual(self.render(sid, "DEMO-USER-GLOBAL").status_code, 409)
        self.assertEqual(self.generated_assets(), [])
        # Rejected proposal can never render or publish.
        sid = self.session()
        state = self.confirm(sid, "DEMO-USER-GLOBAL", BUILD_INTENT)
        rejected = self.client.post(
            f"/api/sessions/{sid}/approval",
            json={
                "user_id": "DEMO-USER-GLOBAL",
                "proposal_id": state["proposal"]["proposal_id"],
                "spec_hash": state["proposal"]["spec_hash"],
                "decision": "reject",
            },
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(self.render(sid, "DEMO-USER-GLOBAL").status_code, 409)
        self.assertEqual(self.generated_assets(), [])

    def test_stale_session_cannot_publish(self):
        sid = self.session()
        state = self.confirm(sid, "DEMO-USER-GLOBAL", BUILD_INTENT)
        self.approve(sid, "DEMO-USER-GLOBAL", state["proposal"])
        # A new confirmed intent invalidates the approved proposal.
        changed = {**BUILD_INTENT, "months": ["2026-01-01"]}
        self.confirm(sid, "DEMO-USER-GLOBAL", changed)
        self.assertEqual(self.render(sid, "DEMO-USER-GLOBAL").status_code, 409)
        self.assertEqual(self.generated_assets(), [])

    def test_same_scope_different_user_dedups(self):
        first = self.publish(user="DEMO-USER-FI")
        # A different user confirming the same scope resolves to the same
        # deterministic asset via REUSE; nothing is republished.
        sid = self.session("DEMO-USER-GLOBAL")
        state = self.confirm(sid, "DEMO-USER-GLOBAL", BUILD_INTENT)
        self.assertEqual(state["outcome"], "REUSE")
        self.assertEqual(
            state["proposal"]["spec"]["source_asset_id"],
            first["registered_asset_id"],
        )
        second = self.render(sid, "DEMO-USER-GLOBAL").json()
        self.assertEqual(
            first["registered_asset_id"], second["registered_asset_id"]
        )
        assets = self.generated_assets()
        self.assertEqual(len(assets), 1)
        # Registration audit event recorded only once.
        audit = self.client.get("/api/assets", params={"user_id": "DEMO-USER-FI"})
        self.assertEqual(audit.status_code, 200)
        fi_assets = [
            a for a in audit.json()["assets"]
            if a["asset_id"].startswith("GEN-")
        ]
        self.assertEqual(len(fi_assets), 1)

    def test_later_session_reuses_generated_asset(self):
        published = self.publish()
        asset_id = published["registered_asset_id"]
        sid = self.session("DEMO-USER-FI")
        state = self.confirm(sid, "DEMO-USER-FI", BUILD_INTENT)
        self.assertEqual(state["outcome"], "REUSE")
        self.assertEqual(
            state["proposal"]["spec"]["source_asset_id"], asset_id
        )
        result = self.render(sid, "DEMO-USER-FI")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["registered_asset_id"], asset_id)
        self.assertEqual(len(self.generated_assets()), 1)

    def test_restart_persists_registry(self):
        published = self.publish()
        asset_id = published["registered_asset_id"]
        self.client.close()
        self.client = TestClient(self.create_app(
            demo_dir=self.demo, runtime_db=self.runtime_db
        ))
        assets = self.generated_assets()
        self.assertEqual([a["asset_id"] for a in assets], [asset_id])
        sid = self.session("DEMO-USER-FI")
        state = self.confirm(sid, "DEMO-USER-FI", BUILD_INTENT)
        self.assertEqual(state["outcome"], "REUSE")

    def test_fingerprint_filters_assets(self):
        published = self.publish()
        asset_id = published["registered_asset_id"]
        other_demo = self.directory / "other_demo"
        shutil.copytree(ROOT / "data" / "demo_v1", other_demo)
        products = other_demo / "products.csv"
        products.write_text(
            products.read_text(encoding="utf-8") + "DEMO-P-X,Extra\n",
            encoding="utf-8",
        )
        other_client = TestClient(self.create_app(
            demo_dir=other_demo, runtime_db=self.runtime_db
        ))
        try:
            response = other_client.get(
                "/api/assets", params={"user_id": "DEMO-USER-GLOBAL"}
            )
            self.assertEqual(response.status_code, 200, response.text)
            ids = [a["asset_id"] for a in response.json()["assets"]]
            self.assertNotIn(asset_id, ids)
            detail = other_client.get(
                f"/api/assets/{asset_id}",
                params={"user_id": "DEMO-USER-GLOBAL"},
            )
            self.assertEqual(detail.status_code, 404)
        finally:
            other_client.close()

    def test_market_restriction_does_not_leak(self):
        published = self.publish(intent=DE_ONLY_INTENT)
        asset_id = published["registered_asset_id"]
        fi_assets = self.generated_assets("DEMO-USER-FI")
        self.assertNotIn(asset_id, [a["asset_id"] for a in fi_assets])
        detail = self.client.get(
            f"/api/assets/{asset_id}", params={"user_id": "DEMO-USER-FI"}
        )
        self.assertEqual(detail.status_code, 404)
        self.assertNotIn(asset_id, detail.text)
        # The authorized user still sees it.
        self.assertIn(
            asset_id,
            [a["asset_id"] for a in self.generated_assets("DEMO-USER-GLOBAL")],
        )

    def test_reuse_endpoint_creates_confirmed_session(self):
        published = self.publish()
        asset_id = published["registered_asset_id"]
        response = self.client.post(
            f"/api/assets/{asset_id}/reuse",
            json={"user_id": "DEMO-USER-FI"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["session_id"])
        self.assertEqual(payload["state"]["outcome"], "REUSE")
        # Seed assets reuse through the same normal decision flow.
        seed = self.client.post(
            "/api/assets/DEMO-REPORT-NUB-DE/reuse",
            json={"user_id": "DEMO-USER-GLOBAL"},
        )
        self.assertEqual(seed.status_code, 200, seed.text)
        self.assertEqual(seed.json()["state"]["outcome"], "REUSE")

    def test_calculation_failure_does_not_publish(self):
        sid = self.session()
        state = self.confirm(sid, "DEMO-USER-GLOBAL", BUILD_INTENT)
        self.approve(sid, "DEMO-USER-GLOBAL", state["proposal"])
        with mock.patch(
            "smart_librarian.workflow.service.compute_monthly",
            side_effect=ValueError("forced failure"),
        ):
            response = self.render(sid, "DEMO-USER-GLOBAL")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.generated_assets(), [])

    def test_concurrent_session_change_blocks_publication(self):
        sid = self.session()
        state = self.confirm(sid, "DEMO-USER-GLOBAL", BUILD_INTENT)
        self.approve(sid, "DEMO-USER-GLOBAL", state["proposal"])

        def _mutate_mid_render(*args, **kwargs):
            from smart_librarian.reporting.calculations import compute_monthly

            # A new message invalidates the approval mid-render.
            posted = self.client.post(
                f"/api/sessions/{sid}/messages",
                json={"user_id": "DEMO-USER-GLOBAL", "text": "changed",
                      "use_llm": False},
            )
            assert posted.status_code == 200
            return compute_monthly(*args, **kwargs)

        with mock.patch(
            "smart_librarian.workflow.service.compute_monthly",
            side_effect=_mutate_mid_render,
        ):
            response = self.render(sid, "DEMO-USER-GLOBAL")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.generated_assets(), [])

    def test_repeat_render_registers_once(self):
        sid = self.session()
        state = self.confirm(sid, "DEMO-USER-GLOBAL", BUILD_INTENT)
        self.approve(sid, "DEMO-USER-GLOBAL", state["proposal"])
        for _ in range(2):
            response = self.render(sid, "DEMO-USER-GLOBAL")
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.generated_assets()), 1)
        audit = self.client.get(
            f"/api/sessions/{sid}/audit",
            params={"user_id": "DEMO-USER-GLOBAL"},
        ).json()["events"]
        registrations = [
            e for e in audit if e["event_type"] == "report_asset_registered"
        ]
        self.assertEqual(len(registrations), 1)

    def test_out_of_scope_generated_candidate_not_leaked(self):
        # GLOBAL publishes an asset spanning DE+FI.
        wide_intent = {**BUILD_INTENT, "market_ids": ["DE", "FI"]}
        published = self.publish(intent=wide_intent)
        asset_id = published["registered_asset_id"]
        # An FI-only requester must never see that candidate, even as
        # evidence text.
        sid = self.session("DEMO-USER-FI")
        state = self.confirm(sid, "DEMO-USER-FI", BUILD_INTENT)
        self.assertNotIn(asset_id, json.dumps(state))

    # Lifecycle management (retire/deprecate) is intentionally out of scope
    # for phase 1; generated assets are always registered as 'active'.


if __name__ == "__main__":
    unittest.main()
