"""Challenge builder-pack API/service/export tests (unittest, offline).

Covers the four source domains, immutable source-row values, validation
refusals, simulated-identity scope, approval/render CAS lifecycle, frozen
render resume, shared-registry dedup reuse, lifecycle proposals and
export packaging. UI workspaces are exercised via AppTest against a fake
HTTP layer that returns serialized snapshots like a real API.
"""

import base64
import copy
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from smart_librarian.api.app import (
    ConfigurationError,
    create_app,
)
from smart_librarian.catalog.store import SnapshotDrift

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT / "tests" / "fixtures" / "challenge_frozen_commercial.json"
)
GLOBAL = "DEMO-CHALLENGE-REQUESTER"
FI = "DEMO-CHALLENGE-FI"
APPROVER = "DEMO-CHALLENGE-APPROVER"
STEWARD = "DEMO-CHALLENGE-STEWARD"

COMMERCIAL = {
    "product_ids": ["P-NUB"], "market_ids": ["DE"],
    "metric_ids": ["net_sales_m_eur_syn", "forecast_m_eur_syn"],
    "months": ["2026-01-01", "2026-02-01", "2026-03-01"], "grain": "month",
}
MARKET_ACCESS = {
    "product_ids": ["P-NUB"], "market_ids": ["DE"],
    "metric_ids": ["coverage_pct_syn", "reimbursement_status"],
    "months": [], "grain": "snapshot",
}
SUPPLY = {
    "product_ids": ["P-NUB"], "market_ids": ["DE"],
    "metric_ids": ["otif_pct_syn", "inventory_weeks_syn", "risk_status"],
    "months": [], "grain": "snapshot",
}
LAUNCH = {
    "product_ids": ["P-NUB"], "market_ids": ["JP"],
    "metric_ids": ["milestone_id", "milestone_type", "status"],
    "months": ["2026-01-01"], "grain": "event",
}


def _tmp_db():
    handle, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(handle)
    os.unlink(path)
    return path


class ChallengeApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = _tmp_db()
        cls.client = TestClient(
            create_app(include_synthetic=True, challenge_mode=True,
                       runtime_db=cls.db_path)
        )

    _combos = iter(
        (p, m)
        for p in ("P-KER", "P-EYL", "P-XAR", "P-LYN", "P-BEY", "P-HYR")
        for m in ("FR", "IT", "ES", "SE", "UK", "US", "CA", "CN", "AU",
                  "BR", "MX")
    )

    def _fresh_intent(self):
        product, market = next(self._combos)
        return {**COMMERCIAL, "product_ids": [product],
                "market_ids": [market]}

    def _create(self, domain, intent, user=GLOBAL, owner="OWN-001"):
        return self.client.post("/api/challenge/plans", json={
            "kind": "report", "user_id": user, "domain_id": domain,
            "intent": intent, "owner_id": owner, "rationale": "test",
        })

    def _approve(self, plan, user=GLOBAL, actor=APPROVER, decision="approve",
                 revision=None):
        return self.client.post(
            f"/api/challenge/plans/{plan['plan_id']}/approval",
            json={
                "user_id": user, "actor_user_id": actor,
                "spec_hash": plan["spec_hash"], "decision": decision,
                "expected_revision": (
                    plan["revision"] if revision is None else revision
                ),
            },
        )

    def _render(self, plan, user=GLOBAL):
        return self.client.post(
            f"/api/challenge/plans/{plan['plan_id']}/render",
            json={
                "user_id": user, "spec_hash": plan["spec_hash"],
                "expected_revision": plan["revision"],
            },
        )

    def _rendered(self, domain, intent, user=GLOBAL):
        response = self._create(domain, intent, user=user)
        self.assertEqual(response.status_code, 200, response.text)
        plan = response.json()["plan"]
        if response.json()["outcome"] == "REUSE":
            if plan["status"] == "rendered":
                return plan
        response = self._approve(plan, user=user)
        self.assertEqual(response.status_code, 200, response.text)
        plan = response.json()["plan"]
        response = self._render(plan, user=user)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["plan"]


    def test_catalog_domains_and_choices(self):
        response = self.client.get(
            "/api/challenge/catalog", params={"domain_id": "commercial"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            sorted(d["domain_id"] for d in payload["domains"]),
            ["commercial", "launch", "market_access", "supply"],
        )
        choices = payload["choices"]
        self.assertEqual(choices["grain"], "month")
        self.assertIn("P-NUB", {p["product_id"] for p in choices["products"]})

    def test_actors_fixed_set(self):
        response = self.client.get("/api/challenge/actors")
        self.assertEqual(response.status_code, 200)
        actors = {a["user_id"]: a for a in response.json()["actors"]}
        self.assertEqual(set(actors), {GLOBAL, FI, APPROVER, STEWARD})
        self.assertIn("steward", actors[STEWARD]["roles"])
        self.assertNotIn("approver", actors[STEWARD]["roles"])

    def test_requests_preserve_source_rows(self):
        response = self.client.get("/api/challenge/requests")
        self.assertEqual(response.status_code, 200)
        rows = response.json()["requests"]
        self.assertEqual(len(rows), 150)
        self.assertEqual(rows[0]["request_id"], "REQ-0001")
        self.assertIn("request_text", rows[0])

    def test_challenge_routes_absent_without_mode(self):
        other = TestClient(create_app(runtime_db=_tmp_db()))
        self.assertEqual(
            other.get("/api/challenge/actors").status_code, 404)


    def test_commercial_first_row_values(self):
        plan = self._rendered("commercial", COMMERCIAL)
        rows = {r["month"]: r for r in plan["report"]["rows"]}
        first = rows["2026-01-01T00:00:00"]
        self.assertEqual(first["net_sales_m_eur_syn"], 19.66)
        self.assertEqual(first["forecast_m_eur_syn"], 18.42)
        self.assertEqual(first["value_type"], "forecast_like_synthetic")
        self.assertEqual(len(plan["report"]["rows"]), 3)
        self.assertEqual(plan["report"]["approval_status"], "approved")

    def test_market_access_snapshot_values(self):
        plan = self._rendered("market_access", MARKET_ACCESS)
        row = plan["report"]["rows"][0]
        self.assertEqual(row["coverage_pct_syn"], 65.6)

    def test_supply_snapshot_values(self):
        plan = self._rendered("supply", SUPPLY)
        row = plan["report"]["rows"][0]
        self.assertEqual(row["otif_pct_syn"], 87.9)
        self.assertEqual(row["inventory_weeks_syn"], 8.8)

    def test_launch_first_event(self):
        plan = self._rendered("launch", LAUNCH)
        row = plan["report"]["rows"][0]
        self.assertEqual(row["milestone_id"], "LM-0001")
        self.assertEqual(row["product_id"], "P-NUB")
        self.assertEqual(row["market_id"], "JP")
        self.assertEqual(row["milestone_date"], "2026-01-05T00:00:00")

    def test_estate_candidates_populated_metadata_only(self):
        plan = self._rendered("commercial", COMMERCIAL)
        candidates = plan["estate_candidates"]
        self.assertTrue(candidates)
        for candidate in candidates:
            self.assertIn("asset_id", candidate)
            self.assertNotIn("spec", candidate)
            self.assertNotIn("rows", candidate)


    def test_missing_month_invalid(self):
        response = self._create(
            "commercial", {**COMMERCIAL, "months": []})
        self.assertEqual(response.status_code, 409)

    def test_unknown_product_denied(self):
        response = self._create(
            "commercial", {**COMMERCIAL, "product_ids": ["P-NOPE"]})
        self.assertEqual(response.status_code, 409)

    def test_unknown_metric_denied(self):
        response = self._create(
            "commercial", {**COMMERCIAL, "metric_ids": ["profit"]})
        self.assertEqual(response.status_code, 409)

    def test_dated_snapshot_blocked(self):
        response = self._create(
            "market_access", {**MARKET_ACCESS, "months": ["2026-01-01"]})
        self.assertEqual(response.status_code, 409)

    def test_wrong_grain_denied(self):
        response = self._create(
            "commercial", {**COMMERCIAL, "grain": "snapshot"})
        self.assertEqual(response.status_code, 409)

    def test_event_without_source_fails(self):
        response = self._create(
            "launch", {**LAUNCH, "months": ["2025-12-01"]})
        self.assertEqual(response.status_code, 409)

    def test_cross_domain_metric_denied(self):
        response = self._create(
            "supply", {**SUPPLY, "metric_ids": ["net_sales_m_eur_syn"]})
        self.assertEqual(response.status_code, 409)

    def test_inactive_owner_denied(self):
        response = self._create(
            "commercial", COMMERCIAL, owner="OWN-018")
        self.assertEqual(response.status_code, 409)

    def test_missing_owner_denied(self):
        response = self._create(
            "commercial", COMMERCIAL, owner="OWN-9999")
        self.assertEqual(response.status_code, 409)

    def test_extra_body_fields_rejected(self):
        response = self.client.post("/api/challenge/plans", json={
            "kind": "report", "user_id": GLOBAL, "domain_id": "commercial",
            "intent": COMMERCIAL, "owner_id": "OWN-001",
            "rationale": "x", "admin": True,
        })
        self.assertEqual(response.status_code, 422)


    def test_fi_denied_de_market(self):
        response = self._create("commercial", COMMERCIAL, user=FI)
        self.assertEqual(response.status_code, 403)

    def test_fi_denied_estate(self):
        response = self.client.get(
            "/api/challenge/estate", params={"user_id": FI})
        self.assertEqual(response.status_code, 403)

    def test_fi_denied_foreign_plan(self):
        plan = self._rendered("commercial", COMMERCIAL)
        response = self.client.get(
            f"/api/challenge/plans/{plan['plan_id']}",
            params={"user_id": FI})
        self.assertEqual(response.status_code, 404)

    def test_fi_denied_mixed_market_plan(self):
        plan = self._create(
            "commercial", {**COMMERCIAL, "market_ids": ["DE", "FI"]}
        ).json()["plan"]
        response = self.client.get(
            f"/api/challenge/plans/{plan['plan_id']}",
            params={"user_id": FI})
        self.assertEqual(response.status_code, 404)
        response = self.client.get(
            "/api/challenge/plans", params={"user_id": FI})
        self.assertNotIn(
            plan["plan_id"],
            {p["plan_id"] for p in response.json()["plans"]},
        )

    def test_unknown_user_denied(self):
        response = self._create("commercial", COMMERCIAL, user="HACKER")
        self.assertEqual(response.status_code, 403)

    def test_shared_fi_registry_reuse_and_render(self):
        """Global-approved FI report is visible/reusable/renderable by FI."""
        intent = {**COMMERCIAL, "market_ids": ["FI"]}
        response = self._create("commercial", intent, user=GLOBAL)
        plan = response.json()["plan"]
        plan = self._approve(plan).json()["plan"]
        response = self.client.get(
            f"/api/challenge/plans/{plan['plan_id']}",
            params={"user_id": FI})
        self.assertEqual(response.status_code, 200)
        response = self._render(plan, user=FI)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["plan"]["status"], "rendered")
        response = self._create("commercial", intent, user=FI)
        self.assertEqual(response.json()["outcome"], "REUSE")
        response = self.client.get(
            f"/api/challenge/plans/{plan['plan_id']}/report",
            params={"user_id": FI})
        self.assertEqual(response.status_code, 200)

    def test_global_reuses_fi_approved(self):
        intent = {**SUPPLY, "market_ids": ["FI"]}
        response = self._create("supply", intent, user=FI)
        self.assertEqual(response.status_code, 200, response.text)
        plan = response.json()["plan"]
        plan = self._approve(plan, user=FI).json()["plan"]
        response = self._create("supply", intent, user=GLOBAL)
        self.assertEqual(response.json()["outcome"], "REUSE")


    def test_pending_cannot_render(self):
        plan = self._create("commercial", self._fresh_intent()).json()["plan"]
        self.assertEqual(self._render(plan).status_code, 409)

    def test_rejected_cannot_render(self):
        plan = self._create("commercial", self._fresh_intent()).json()["plan"]
        plan = self._approve(plan, decision="reject").json()["plan"]
        self.assertEqual(plan["status"], "rejected")
        self.assertEqual(self._render(plan).status_code, 409)

    def test_steward_cannot_approve(self):
        plan = self._create("commercial", self._fresh_intent()).json()["plan"]
        self.assertEqual(
            self._approve(plan, actor=STEWARD).status_code, 403)

    def test_unknown_actor_rejected(self):
        plan = self._create("commercial", self._fresh_intent()).json()["plan"]
        self.assertEqual(
            self._approve(plan, actor="NOPE").status_code, 403)

    def test_wrong_requester_rejected(self):
        plan = self._create("commercial", self._fresh_intent()).json()["plan"]
        self.assertEqual(self._approve(plan, user=FI).status_code, 403)

    def test_stale_hash_rejected(self):
        plan = self._create("commercial", self._fresh_intent()).json()["plan"]
        self.assertEqual(
            self._approve({**plan, "spec_hash": "0" * 64}).status_code, 409)

    def test_stale_revision_rejected(self):
        plan = self._create("commercial", self._fresh_intent()).json()["plan"]
        self.assertEqual(self._approve(plan, revision=9).status_code, 409)

    def test_opposite_terminal_decision_conflict(self):
        plan = self._create("commercial", self._fresh_intent()).json()["plan"]
        plan = self._approve(plan).json()["plan"]
        response = self._approve(plan, decision="reject")
        self.assertEqual(response.status_code, 409)

    def test_idempotent_same_decision(self):
        plan = self._create("commercial", self._fresh_intent()).json()["plan"]
        first = self._approve(plan).json()["plan"]
        second = self._approve(first).json()
        self.assertTrue(second["idempotent"])
        self.assertEqual(second["plan"]["status"], "approved")

    def test_approval_rationale_in_creation_audit(self):
        response = self.client.post("/api/challenge/plans", json={
            "kind": "report", "user_id": GLOBAL, "domain_id": "commercial",
            "intent": self._fresh_intent(), "owner_id": "OWN-001",
            "rationale": "why-this-scope",
        })
        plan = response.json()["plan"]
        created = next(
            e for e in plan["audit"] if e["event_type"] == "plan_created")
        self.assertEqual(created["detail"]["rationale"], "why-this-scope")

    def test_source_drift_blocks_approval(self):
        """A stale source snapshot must refuse approval, incl. idempotent."""
        plan = self._create("commercial", self._fresh_intent()).json()["plan"]
        service = self.client.app.state.challenge_service
        with mock.patch.object(
            service.data, "assert_current",
            side_effect=SnapshotDrift("drifted"),
        ):
            response = self._approve(plan)
        self.assertEqual(response.status_code, 409)
        after = self.client.get(
            f"/api/challenge/plans/{plan['plan_id']}",
            params={"user_id": GLOBAL}).json()["plan"]
        self.assertEqual(after["status"], "pending")
        self.assertFalse(
            any(e["event_type"].startswith("approval_")
                for e in after["audit"]))


    def test_stale_plan_fingerprint_blocks_approval(self):
        plan = self._create("commercial", self._fresh_intent()).json()["plan"]
        service = self.client.app.state.challenge_service
        with mock.patch.object(
            service.data, "fingerprint", "0" * 64,
        ):
            response = self._approve(plan)
        self.assertEqual(response.status_code, 409)
        after = self.client.get(
            f"/api/challenge/plans/{plan['plan_id']}",
            params={"user_id": GLOBAL}).json()["plan"]
        self.assertEqual(after["status"], "pending")
        self.assertFalse(
            any(e["event_type"].startswith("approval_")
                for e in after["audit"]))

    def test_idempotent_denied_on_fingerprint_mismatch(self):
        plan = self._create("commercial", self._fresh_intent()).json()["plan"]
        approved = self._approve(plan).json()["plan"]
        service = self.client.app.state.challenge_service
        with mock.patch.object(
            service.data, "fingerprint", "0" * 64,
        ):
            response = self._approve(
                approved, revision=approved["revision"])
        self.assertEqual(response.status_code, 409)

    def test_extract_llm_mixed_known_unknown_months(self):
        from smart_librarian.persistence.store import RuntimeStore
        from smart_librarian.workflow.challenge import ChallengeService

        class FakeLLM:
            def extract_intent(self, conversation, catalog_choices):
                return {
                    "product_ids": ["P-NUB"], "market_ids": ["DE"],
                    "metric_ids": ["net_sales_m_eur_syn"],
                    "months": ["2026-01-01", "2027-01-01"], "grain": "month",
                    "unresolved": [], "unsupported": [],
                }

        service = ChallengeService(RuntimeStore(_tmp_db()))
        result = service.extract(GLOBAL, "commercial", "text", True,
                                 llm=FakeLLM())
        self.assertEqual(result["partial_intent"]["months"], ["2026-01-01"])
        self.assertIn("months", result["unresolved"])
        self.assertTrue(
            any("2027-01-01" in u for u in result["unsupported"]))
        self.assertEqual(
            result["proposed_intent"]["months"],
            ["2026-01-01", "2027-01-01"])

    def test_equivalent_scope_reuses_approved(self):
        plan = self._rendered("commercial", COMMERCIAL)
        shuffled = {
            **COMMERCIAL,
            "months": list(reversed(COMMERCIAL["months"])),
            "metric_ids": list(reversed(COMMERCIAL["metric_ids"])),
        }
        response = self._create("commercial", shuffled)
        self.assertEqual(response.json()["outcome"], "REUSE")
        self.assertEqual(
            response.json()["plan"]["plan_id"], plan["plan_id"])

    def test_altered_scope_not_reused(self):
        self._rendered("commercial", COMMERCIAL)
        response = self._create(
            "commercial", {**COMMERCIAL, "market_ids": ["FR"]})
        self.assertEqual(response.json()["outcome"], "PENDING_APPROVAL")

    def test_pending_not_reusable(self):
        first = self._create("supply", SUPPLY).json()["plan"]
        second = self._create("supply", SUPPLY).json()
        self.assertEqual(second["outcome"], "PENDING_APPROVAL")
        self.assertNotEqual(second["plan"]["plan_id"], first["plan_id"])

    def test_two_pending_coalesce_at_approval(self):
        intent = self._fresh_intent()
        first = self._create("commercial", intent).json()["plan"]
        second = self._create("commercial", intent).json()["plan"]
        self.assertNotEqual(first["plan_id"], second["plan_id"])
        response = self._approve(first)
        self.assertEqual(response.status_code, 200)
        winner = response.json()["plan"]
        self.assertEqual(winner["status"], "approved")
        response = self._approve(second)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["outcome"], "REUSE")
        self.assertEqual(body["plan"]["plan_id"], winner["plan_id"])
        self.assertEqual(body["superseded_plan_id"], second["plan_id"])
        loser = self.client.get(
            f"/api/challenge/plans/{second['plan_id']}",
            params={"user_id": GLOBAL}).json()["plan"]
        self.assertEqual(loser["status"], "superseded")
        self.assertTrue(
            any(e["event_type"] == "duplicate_reused"
                and e["detail"]["winner_plan_id"] == winner["plan_id"]
                for e in loser["audit"]))
        plans = self.client.get(
            "/api/challenge/plans", params={"user_id": GLOBAL}
        ).json()["plans"]
        active = [
            p for p in plans
            if p["spec_hash"] == winner["spec_hash"]
            and p["status"] in ("approved", "rendered")
        ]
        self.assertEqual(len(active), 1)
        response = self._approve(loser, decision="reject",
                                 revision=loser["revision"])
        self.assertEqual(response.status_code, 409)

    def test_resume_frozen_report_new_app(self):
        plan = self._rendered("commercial", COMMERCIAL)
        fresh = TestClient(
            create_app(include_synthetic=True, challenge_mode=True,
                       runtime_db=self.db_path)
        )
        response = fresh.get(
            f"/api/challenge/plans/{plan['plan_id']}/report",
            params={"user_id": GLOBAL})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["report"]["rows"], plan["report"]["rows"])

    def test_report_before_render_409(self):
        plan = self._create("commercial", self._fresh_intent()).json()["plan"]
        response = self.client.get(
            f"/api/challenge/plans/{plan['plan_id']}/report",
            params={"user_id": GLOBAL})
        self.assertEqual(response.status_code, 409)


    def _extract(self, domain, text, use_llm=False, user=GLOBAL):
        return self.client.post("/api/challenge/extract", json={
            "user_id": user, "domain_id": domain, "text": text,
            "use_llm": use_llm,
        })

    def test_extract_offline_commercial(self):
        response = self._extract(
            "commercial",
            "Nubeqa Germany net sales and sales forecast January "
            "through March 2026")
        self.assertEqual(response.status_code, 200)
        intent = response.json()["partial_intent"]
        self.assertEqual(intent["product_ids"], ["P-NUB"])
        self.assertEqual(intent["market_ids"], ["DE"])
        self.assertEqual(
            sorted(intent["metric_ids"]),
            ["forecast_m_eur_syn", "net_sales_m_eur_syn"])
        self.assertEqual(response.json()["extraction_mode"], "offline")

    def test_extract_exact_source_ids(self):
        response = self._extract(
            "commercial",
            "P-NUB DE net_sales_m_eur_syn January 2026")
        intent = response.json()["partial_intent"]
        self.assertEqual(intent["product_ids"], ["P-NUB"])
        self.assertEqual(intent["market_ids"], ["DE"])
        self.assertEqual(intent["metric_ids"], ["net_sales_m_eur_syn"])
        self.assertEqual(intent["months"], ["2026-01-01"])

    def test_extract_snapshot_dated_unsupported(self):
        payload = self._extract(
            "supply", "Nubeqa Germany OTIF January 2026").json()
        self.assertEqual(payload["partial_intent"]["months"], [])
        self.assertTrue(payload["unsupported"])

    def test_extract_snapshot_trend_unsupported(self):
        payload = self._extract(
            "supply", "Nubeqa Germany OTIF trend").json()
        self.assertTrue(payload["unsupported"])

    def test_extract_all_months_unknown_year(self):
        payload = self._extract(
            "commercial",
            "Nubeqa Germany net sales all demo months 2027").json()
        self.assertTrue(payload["unsupported"] or payload["unresolved"])

    def test_extract_llm_months_out_of_coverage(self):
        from smart_librarian.persistence.store import RuntimeStore
        from smart_librarian.workflow.challenge import ChallengeService

        class FakeLLM:
            def extract_intent(self, conversation, catalog_choices):
                return {
                    "product_ids": ["P-NUB"], "market_ids": ["DE"],
                    "metric_ids": ["net_sales_m_eur_syn"],
                    "months": ["2027-01-01"], "grain": "month",
                    "unresolved": [], "unsupported": [],
                }

        service = ChallengeService(RuntimeStore(_tmp_db()))
        result = service.extract(GLOBAL, "commercial", "text", True,
                                 llm=FakeLLM())
        self.assertEqual(result["extraction_mode"], "llm")
        self.assertEqual(result["partial_intent"]["months"], [])
        self.assertIn("months", result["unresolved"])
        self.assertTrue(
            any("2027-01-01" in u for u in result["unsupported"]))
        self.assertEqual(
            result["proposed_intent"]["months"], ["2027-01-01"])

    def test_extract_llm_grain_mismatch_preserved(self):
        from smart_librarian.persistence.store import RuntimeStore
        from smart_librarian.workflow.challenge import ChallengeService

        class FakeLLM:
            def extract_intent(self, conversation, catalog_choices):
                return {
                    "product_ids": ["P-NUB"], "market_ids": ["DE"],
                    "metric_ids": ["net_sales_m_eur_syn"],
                    "months": ["2026-01-01"], "grain": "annual",
                    "unresolved": [], "unsupported": [],
                }

        service = ChallengeService(RuntimeStore(_tmp_db()))
        result = service.extract(GLOBAL, "commercial", "text", True,
                                 llm=FakeLLM())
        self.assertEqual(result["partial_intent"]["grain"], "month")
        self.assertEqual(result["proposed_intent"]["grain"], "annual")
        self.assertTrue(any("annual" in u for u in result["unsupported"]))

    def test_extract_llm_snapshot_dated_unsupported(self):
        from smart_librarian.persistence.store import RuntimeStore
        from smart_librarian.workflow.challenge import ChallengeService

        class FakeLLM:
            def extract_intent(self, conversation, catalog_choices):
                return {
                    "product_ids": ["P-NUB"], "market_ids": ["DE"],
                    "metric_ids": ["otif_pct_syn"],
                    "months": ["2026-01-01"], "grain": "snapshot",
                    "unresolved": [], "unsupported": [],
                }

        service = ChallengeService(RuntimeStore(_tmp_db()))
        result = service.extract(GLOBAL, "supply", "text", True,
                                 llm=FakeLLM())
        self.assertEqual(result["partial_intent"]["months"], [])
        self.assertTrue(result["unsupported"])

    def test_extract_llm_invalid_ids_preserved(self):
        from smart_librarian.persistence.store import RuntimeStore
        from smart_librarian.workflow.challenge import ChallengeService
        from smart_librarian.workflow.service import LLMUnavailable

        class FakeLLM:
            def extract_intent(self, conversation, catalog_choices):
                return {
                    "product_ids": ["P-NUB", "P-FAKE"],
                    "market_ids": ["DE"], "metric_ids": ["otif_pct_syn"],
                    "months": [], "grain": None,
                    "unresolved": [], "unsupported": ["growth asked"],
                }

        service = ChallengeService(RuntimeStore(_tmp_db()))
        result = service.extract(GLOBAL, "supply", "text", True,
                                 llm=FakeLLM())
        self.assertEqual(result["extraction_mode"], "llm")
        self.assertIn("product_ids:P-FAKE", result["invalid_ids"])
        self.assertIn("growth asked", result["unsupported"])

        class FailingLLM:
            def extract_intent(self, conversation, catalog_choices):
                raise LLMUnavailable("no key")

        result = service.extract(GLOBAL, "supply", "Nubeqa Germany OTIF",
                                 True, llm=FailingLLM())
        self.assertEqual(
            result["extraction_mode"],
            "offline_fallback_after_llm_unavailable")
        self.assertEqual(result["partial_intent"]["product_ids"], ["P-NUB"])


    def _lifecycle(self, asset_id, action, target=None, owner="OWN-001",
                   user=GLOBAL, rationale="reviewed"):
        return self.client.post("/api/challenge/plans", json={
            "kind": "lifecycle", "user_id": user, "asset_id": asset_id,
            "action": action, "target_asset_id": target,
            "owner_id": owner, "rationale": rationale,
        })

    def test_lifecycle_migrate_approve_not_executed(self):
        response = self._lifecycle("AST-0002", "migrate")
        self.assertEqual(response.status_code, 200, response.text)
        plan = response.json()["plan"]
        response = self._approve(plan)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["outcome"], "approved proposal; not executed")
        self.assertEqual(
            self._render(response.json()["plan"]).status_code, 409)

    def test_lifecycle_repair(self):
        response = self._lifecycle("AST-0002", "repair")
        self.assertEqual(response.status_code, 200, response.text)
        spec = response.json()["plan"]["spec"]
        self.assertEqual(spec["execution_status"], "not_executed")

    def test_lifecycle_consolidate_candidate(self):
        response = self._lifecycle("AST-0002", "consolidate",
                                 target="AST-0278")
        self.assertEqual(response.status_code, 200, response.text)

    def test_lifecycle_consolidate_invalid_target(self):
        response = self._lifecycle("AST-0002", "consolidate",
                                 target="AST-0001")
        self.assertEqual(response.status_code, 409)

    def test_migrate_non_tableau_refused(self):
        estate = self.client.get(
            "/api/challenge/estate", params={"user_id": GLOBAL}).json()
        non_tableau = next(
            a for a in estate["assets"] if a["platform"] != "Tableau")
        response = self._lifecycle(non_tableau["asset_id"], "migrate")
        self.assertEqual(response.status_code, 409)

    def test_retire_with_dependencies_refused(self):
        estate = self.client.get(
            "/api/challenge/estate", params={"user_id": GLOBAL}).json()
        for asset in estate["assets"]:
            detail = self.client.get(
                f"/api/challenge/estate/{asset['asset_id']}",
                params={"user_id": GLOBAL}).json()
            if detail["downstream_ids"]:
                response = self._lifecycle(asset["asset_id"], "retire")
                self.assertEqual(response.status_code, 409)
                return
        self.skipTest("no asset with downstream dependencies found")

    def test_lifecycle_fi_denied(self):
        response = self._lifecycle("AST-0002", "repair", user=FI)
        self.assertEqual(response.status_code, 403)

    def test_source_unchanged_by_proposals(self):
        self._lifecycle("AST-0002", "migrate")
        catalog = self.client.get(
            "/api/challenge/catalog",
            params={"domain_id": "supply"}).json()
        self.assertEqual(
            catalog["choices"]["source_sha256"],
            "7d01877096c640d7705c0507cfc32840dd88a99fe546d975a715f73b40f101ab")


    def test_estate_search_and_detail(self):
        response = self.client.get(
            "/api/challenge/estate",
            params={"user_id": GLOBAL, "q": "nubeqa"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["count"])
        asset_id = response.json()["assets"][0]["asset_id"]
        detail = self.client.get(
            f"/api/challenge/estate/{asset_id}",
            params={"user_id": GLOBAL}).json()
        self.assertIn("governance_rules", detail)
        self.assertEqual(len(detail["governance_rules"]), 8)
        self.assertIn("workspace", detail)


    def test_exports_frozen_and_safe(self):
        plan = self._rendered("commercial", COMMERCIAL)
        for fmt in ("html", "csv", "zip", "kit", "pbip"):
            response = self.client.get(
                f"/api/challenge/plans/{plan['plan_id']}/export",
                params={"user_id": GLOBAL, "format": fmt})
            self.assertEqual(response.status_code, 200, fmt)
        html = self.client.get(
            f"/api/challenge/plans/{plan['plan_id']}/export",
            params={"user_id": GLOBAL, "format": "html"}).text
        self.assertIn("19.66", html)
        self.assertNotIn("<script src", html)
        csv_text = self.client.get(
            f"/api/challenge/plans/{plan['plan_id']}/export",
            params={"user_id": GLOBAL, "format": "csv"}).text
        for line in csv_text.splitlines()[1:]:
            for cell in line.split(","):
                self.assertFalse(
                    cell.lstrip().startswith(("=", "+", "-", "@")), cell)

    def test_css_strings_intact(self):
        from smart_librarian.ui import challenge as ui
        self.assertIn("#f5f8fa", ui._CSS)
        self.assertIn("#0f3557", ui._CSS)
        from smart_librarian.reporting.challenge_exports import (
            challenge_report_html,
        )
        page = challenge_report_html(json.loads(FIXTURE.read_text()))
        self.assertIn("background: #f5f8fa", page)
        self.assertIn("border: 1px solid #d5e0e6", page)
        self.assertIn("color: #0f3557", page)
        self.assertIn("}}", page)

    def test_html_embedded_json_parses_and_escapes(self):
        from smart_librarian.reporting.challenge_exports import (
            challenge_report_html,
        )
        report = json.loads(FIXTURE.read_text())
        report["spec"] = dict(report["spec"])
        report["spec"]["injected"] = "</script><script>alert(1)</script>"
        page = challenge_report_html(report)
        marker = 'id="spec">'
        start = page.index(marker) + len(marker)
        end = page.index("</script>", start)
        embedded = json.loads(page[start:end])
        self.assertEqual(embedded["spec"]["injected"],
                         "</script><script>alert(1)</script>")
        self.assertNotIn("<script>alert", page)

    def test_kit_keeps_time_columns_text(self):
        import io as _io
        import zipfile as _zipfile
        from smart_librarian.reporting.challenge_exports import (
            challenge_import_kit,
        )
        report = json.loads(FIXTURE.read_text())
        with _zipfile.ZipFile(
            _io.BytesIO(challenge_import_kit(report))
        ) as archive:
            query = archive.read("PowerQuery_Report.m").decode()
        self.assertIn('"month", type text', query)
        self.assertNotIn('"month", type date', query)

    def test_pbip_packaging(self):
        report = json.loads(FIXTURE.read_text())
        from smart_librarian.reporting.challenge_pbip import (
            build_challenge_pbip_bundle,
            build_challenge_pbip_files,
        )
        files = build_challenge_pbip_files(report)
        names = set(files)
        self.assertIn("GovernedReport.pbip", names)
        self.assertIn("GovernedReport.SemanticModel/model.bim", names)
        model = json.loads(files["GovernedReport.SemanticModel/model.bim"])
        self.assertEqual(model["compatibilityLevel"], 1601)
        table = model["model"]["tables"][0]
        self.assertTrue(
            all(c["summarizeBy"] == "none" for c in table["columns"]))
        expression = "\n".join(
            table["partitions"][0]["source"]["expression"])
        self.assertNotIn("File.", expression.split("Json.Document")[0])
        self.assertNotIn("Web.", expression)
        encoded = expression.split('BinaryEncoding.Base64')[0]
        blob = encoded.split('"')[1]
        decoded = json.loads(base64.b64decode(blob))
        self.assertEqual(decoded, report["rows"])
        self.assertIn("_source_row", decoded[0])
        pbir = json.loads(
            files["GovernedReport.Report/definition.pbir"])
        self.assertEqual(
            pbir["datasetReference"]["byPath"]["path"],
            "../GovernedReport.SemanticModel")
        self.assertEqual(
            build_challenge_pbip_bundle(report),
            build_challenge_pbip_bundle(report))
        with zipfile.ZipFile(
            io.BytesIO(build_challenge_pbip_bundle(report))
        ) as archive:
            self.assertEqual(
                set(archive.namelist()), set(files))

    def test_pbip_required_package_files(self):
        report = json.loads(FIXTURE.read_text())
        from smart_librarian.reporting.challenge_pbip import (
            build_challenge_pbip_files,
        )
        files = build_challenge_pbip_files(report)
        required = [
            "GovernedReport.pbip",
            "GovernedReport.Report/definition.pbir",
            "GovernedReport.SemanticModel/definition.pbism",
            "GovernedReport.SemanticModel/model.bim",
            "GovernedReport.Report/definition/report.json",
            "GovernedReport.Report/definition/version.json",
            "GovernedReport.Report/definition/pages/pages.json",
            "GovernedReport.Report/definition/pages/Overview/page.json",
            "GovernedReport.Report/definition/pages/Overview/visuals/"
            "SourceRows/visual.json",
        ]
        for name in required:
            self.assertIn(name, set(files), name)
        version = json.loads(
            files["GovernedReport.Report/definition/version.json"])
        self.assertEqual(version["version"], "2.0.0")
        self.assertTrue(
            version["$schema"].endswith(
                "item/report/definition/versionMetadata/1.0.0/schema.json"))

    def test_pbip_rejects_invalid(self):
        from smart_librarian.reporting.challenge_pbip import (
            build_challenge_pbip_files,
        )
        report = json.loads(FIXTURE.read_text())
        mixed = copy.deepcopy(report)
        mixed["rows"].append({
            **mixed["rows"][0],
            "_source_row": 999,
            "net_sales_m_eur_syn": "mixed",
        })
        with self.assertRaises(ValueError):
            build_challenge_pbip_files(mixed)
        empty = copy.deepcopy(report)
        empty["rows"] = []
        with self.assertRaises(ValueError):
            build_challenge_pbip_files(empty)
        wrong_sheet = copy.deepcopy(report)
        wrong_sheet["rows"][0]["_source_sheet"] = "Other_Sheet"
        with self.assertRaises(ValueError):
            build_challenge_pbip_files(wrong_sheet)
        wrong_hash = copy.deepcopy(report)
        wrong_hash["source_provenance"]["source_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            build_challenge_pbip_files(wrong_hash)
        no_identity = copy.deepcopy(report)
        del no_identity["rows"][0]["_source_row"]
        with self.assertRaises(ValueError):
            build_challenge_pbip_files(no_identity)

    def test_runtime_db_in_data_dir_refused(self):
        with self.assertRaises(ConfigurationError):
            create_app(include_synthetic=True, challenge_mode=True,
                       runtime_db=ROOT / "data" / "evil.sqlite")


class _Fake:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = (
            payload if isinstance(payload, str) else str(payload))
        self.content = payload if isinstance(payload, bytes) else b""

    def json(self):
        return copy.deepcopy(self._payload)


class ChallengeUiTests(unittest.TestCase):
    """AppTest smoke for the challenge workspaces via a fake HTTP API."""

    APP = "apps/streamlit_app.py"

    def setUp(self):
        import httpx as _httpx
        self.plans = {}
        self.seq = [0]

        actors = {"actors": [
            {"user_id": GLOBAL, "name": "g", "roles": ["requester"],
             "allowed_market_ids": "all"},
            {"user_id": FI, "name": "fi", "roles": ["requester"],
             "allowed_market_ids": ["FI"]},
            {"user_id": APPROVER, "name": "a", "roles": ["approver"],
             "allowed_market_ids": "all"},
            {"user_id": STEWARD, "name": "s", "roles": ["steward"],
             "allowed_market_ids": "all"},
        ], "simulated": True}
        catalog = {
            "domains": [
                {"domain_id": d, "name": d, "grain": g}
                for d, g in (("commercial", "month"),
                             ("market_access", "snapshot"),
                             ("supply", "snapshot"), ("launch", "event"))
            ],
            "choices": {
                "domain_id": "commercial", "grain": "month",
                "source_sha256": "ab" * 32,
                "data_classification": "official_synthetic_challenge",
                "disclaimer": "synthetic",
                "products": [{"product_id": "P-NUB",
                              "product_name": "Nubeqa"}],
                "markets": [{"market_id": "DE", "market_name": "Germany"}],
                "owners": [{"owner_id": "OWN-001", "owner_name": "Owner"}],
                "metrics": [
                    {"metric_id": "net_sales_m_eur_syn", "name": "Net",
                     "unit": "million EUR", "context_kpi_id": "KPI-001",
                     "aliases": []},
                ],
                "months": ["2026-01-01"],
                "model": {"model_id": "CHALLENGE-COMMERCIAL",
                          "supported_grains": ["month"],
                          "coverage": {"months": ["2026-01-01"]}},
            },
        }
        requests = {"requests": [
            {"request_id": "REQ-0001", "request_text": "Nubeqa DE sales",
             "product_context": "Nubeqa", "market_context": "EMEA",
             "request_date": "2026-01-01", "urgency": "normal",
             "status": "new", "_source_row": 2},
        ]}
        estate = {"assets": [
            {"asset_id": "AST-0002", "asset_name": "Old QBR",
             "platform": "Tableau", "product_scope": "P-NUB",
             "market_scope": "BR", "endorsement": "none",
             "lifecycle_status": "candidate_retire"},
        ], "count": 1}
        estate_detail = {
            "asset": {"asset_id": "AST-0002", "asset_name": "Old QBR",
                      "platform": "Tableau", "product_scope": "P-NUB",
                      "market_scope": "BR",
                      "lifecycle_status": "candidate_retire",
                      "endorsement": "none"},
            "model": None, "owner": None, "kpis": [], "usage": [],
            "lineage": [], "downstream_ids": [], "signals": [],
            "data_quality": [],
            "governance_gaps": ["missing_semantic_model"],
            "exact_metadata_candidates": [],
            "consolidation_candidates": [
                {"asset_id": "AST-0278",
                 "shared_canonical_metrics": ["On-Time In-Full"],
                 "model_id": "SM-9", "equivalence": "not_verified",
                 "required_review": "reconcile"},
            ],
            "migration_inputs": [], "workspace": None,
            "governance_rules": [{"rule_id": "RULE-001"}],
            "owner_options": [{"owner_id": "OWN-001",
                               "owner_name": "Owner"}],
            "decision": "REPAIR_REVIEW", "decision_note": "note",
        }

        def fi_visible(plan):
            if plan["kind"] != "report":
                return plan["requester"] == FI
            return plan["spec"].get("intent", {}).get(
                "market_ids") == ["FI"]

        def fake_get(url, params=None, timeout=None):
            if url.endswith("/api/domains"):
                return _Fake(200, {"domains": [], "challenge_mode": True,
                                   "simulated": True})
            if url.endswith("/actors"):
                return _Fake(200, actors)
            if url.endswith("/catalog"):
                payload = copy.deepcopy(catalog)
                domain = (params or {}).get("domain_id", "commercial")
                payload["choices"]["domain_id"] = domain
                grains = {"commercial": "month", "launch": "event"}
                payload["choices"]["grain"] = grains.get(domain, "snapshot")
                if payload["choices"]["grain"] == "snapshot":
                    payload["choices"]["months"] = []
                return _Fake(200, payload)
            if url.endswith("/requests"):
                return _Fake(200, requests)
            if url.endswith("/export"):
                return _Fake(200, b"bytes")
            if "/estate/" in url:
                return _Fake(200, estate_detail)
            if url.endswith("/estate"):
                return _Fake(200, estate)
            if url.endswith("/report"):
                pid = url.split("/plans/")[1].split("/")[0]
                plan = self.plans[pid]
                if (params or {}).get("user_id") == FI \
                        and not fi_visible(plan):
                    return _Fake(404, {"detail": "not found"})
                return _Fake(200, {
                    "plan_id": pid, "report": plan.get("report"),
                    "audit": []})
            if "/plans/" in url:
                pid = url.split("/plans/")[1].split("/")[0]
                plan = self.plans.get(pid)
                if plan is None:
                    return _Fake(404, {"detail": "not found"})
                if (params or {}).get("user_id") == FI \
                        and not fi_visible(plan):
                    return _Fake(404, {"detail": "not found"})
                return _Fake(200, {"plan": plan})
            if url.endswith("/plans"):
                user = (params or {}).get("user_id")
                plans = list(self.plans.values())
                if user == FI:
                    plans = [p for p in plans if fi_visible(p)]
                return _Fake(200, {"plans": plans})
            return _Fake(404, {"detail": url})

        def fake_post(url, json=None, timeout=None):
            if url.endswith("/plans"):
                self.seq[0] += 1
                pid = f"plan-{self.seq[0]}"
                plan = {
                    "plan_id": pid, "revision": 0,
                    "requester": json["user_id"], "kind": json["kind"],
                    "status": "pending",
                    "domain_id": json.get("domain_id"),
                    "spec_hash": "h" * 64,
                    "spec": {"kind": json["kind"],
                             "intent": json.get("intent", {})},
                    "report": None, "audit": [],
                    "estate_candidates": [
                        {"asset_id": "AST-0002", "asset_name": "Old QBR",
                         "platform": "Tableau"},
                    ] if json["kind"] == "report" else [],
                }
                if (json.get("intent") or {}).get("market_ids") == ["FI"] \
                        and json["user_id"] == FI:
                    pass
                self.plans[pid] = plan
                return _Fake(200, {"outcome": "PENDING_APPROVAL",
                                   "plan": plan})
            if url.endswith("/approval"):
                pid = url.split("/plans/")[1].split("/")[0]
                if json["actor_user_id"] != APPROVER:
                    return _Fake(403, {"detail": "not an approver"})
                if json["user_id"] != self.plans[pid]["requester"]:
                    return _Fake(403, {"detail": "different requester"})
                self.plans[pid]["status"] = (
                    "approved" if json["decision"] == "approve"
                    else "rejected")
                self.plans[pid]["revision"] += 1
                return _Fake(200, {"plan": self.plans[pid],
                                   "idempotent": False})
            if url.endswith("/render"):
                pid = url.split("/plans/")[1].split("/")[0]
                self.plans[pid]["status"] = "rendered"
                self.plans[pid]["report"] = {
                    "spec": {"intent": {"grain": "month",
                                        "metric_ids":
                                        ["net_sales_m_eur_syn"]},
                             "fields": []},
                    "rows": [{"product_id": "P-NUB",
                              "product_name": "Nubeqa",
                              "market_id": "DE", "market_name": "Germany",
                              "month": "2026-01-01T00:00:00",
                              "net_sales_m_eur_syn": 19.66,
                              "value_type": "forecast_like_synthetic"}],
                    "units": {"net_sales_m_eur_syn": "million EUR"},
                }
                self.plans[pid]["revision"] += 1
                return _Fake(200, {"plan": self.plans[pid],
                                   "idempotent": False})
            if url.endswith("/extract"):
                return _Fake(200, {
                    "domain_id": json["domain_id"],
                    "partial_intent": {"product_ids": ["P-NUB"],
                                       "market_ids": ["DE"],
                                       "metric_ids": [],
                                       "months": ["2026-01-01"],
                                       "grain": "month"},
                    "proposed_intent": {"product_ids": ["P-NUB"],
                                        "market_ids": ["DE"],
                                        "metric_ids": [],
                                        "months": ["2026-01-01"],
                                        "grain": "month"},
                    "unresolved": ["metric_ids"],
                    "questions": ["which metrics"],
                    "unsupported": [], "invalid_ids": [],
                    "extraction_mode": (
                        "llm" if json["use_llm"] else "offline"),
                    "limitations": "note"})
            return _Fake(404, {"detail": url})

        self.get_p = mock.patch.object(_httpx, "get",
                                       side_effect=fake_get)
        self.post_p = mock.patch.object(_httpx, "post",
                                        side_effect=fake_post)
        self.get_p.start()
        self.post_p.start()
        self.addCleanup(self.get_p.stop)
        self.addCleanup(self.post_p.stop)

        from streamlit.testing.v1 import AppTest
        self.at = AppTest.from_file(self.APP, default_timeout=30)

    def _all_text(self, at):
        parts = [m.value for m in at.markdown]
        for kind in ("caption", "info", "warning", "error", "success",
                     "subheader", "header"):
            parts.extend(str(e.value) for e in getattr(at, kind, []))
        return " ".join(parts)

    def _radio(self, at):
        return next(r for r in at.sidebar.radio
                    if r.label == "Workspace")

    def _full_flow(self, at):
        prefill = next(b for b in at.button if "Prefill" in str(b.label))
        prefill.click(); at.run()
        self.assertFalse(at.exception)
        owner = next(
            s for s in at.selectbox
            if "Accountable owner" in str(s.label))
        self.assertIsNone(owner.value)
        create = next(
            b for b in at.button if "Create plan" in str(b.label))
        self.assertTrue(create.disabled)
        owner.set_value("OWN-001"); at.run()
        self.assertFalse(at.exception)
        create = next(
            b for b in at.button if "Create plan" in str(b.label))
        create.click(); at.run()
        self.assertFalse(at.exception)
        approve = next(b for b in at.button if b.label == "Approve")
        approve.click(); at.run()
        self.assertFalse(at.exception)
        render = next(
            b for b in at.button if b.label == "Render frozen report")
        render.click(); at.run()
        self.assertFalse(at.exception)

    def test_builder_full_flow_then_second_plan(self):
        at = self.at
        at.run()
        self.assertFalse(at.exception)
        self._full_flow(at)
        text = self._all_text(at)
        self.assertIn("rendered", text)
        self.assertIn("plan-1", text)
        frames = list(at.dataframe)
        self.assertTrue(any(
            "net_sales_m_eur_syn" in getattr(df.value, "columns", [])
            for df in frames))
        try:
            buttons = list(at.get("download_button"))
        except Exception:
            buttons = []
        labels = [str(b.label) for b in buttons]
        for expected in ("HTML", "CSV", "ZIP bundle",
                         "Power Query kit (CSV+M)",
                         "Power BI project (PBIP ZIP)"):
            self.assertIn(expected, labels)
        create = next(
            b for b in at.button if "Create plan" in str(b.label))
        create.click(); at.run()
        self.assertFalse(at.exception)
        text = self._all_text(at)
        self.assertIn("plan-2", text)
        self.assertNotIn("status: **rendered**", text)

    def test_sample_load_keeps_edits(self):
        at = self.at
        at.run()
        self.assertFalse(at.exception)
        expander = next(
            e for e in at.expander
            if "business requests" in str(e.label).lower())
        pick = next(
            s for s in expander.selectbox
            if s.label == "Sample request")
        pick.set_value("REQ-0001"); at.run()
        self.assertFalse(at.exception)
        expander = next(
            e for e in at.expander
            if "business requests" in str(e.label).lower())
        load = next(b for b in expander.button
                    if b.label == "Load request text")
        load.click(); at.run()
        self.assertFalse(at.exception)
        text_input = next(
            t for t in at.text_input if t.label == "Describe the report")
        self.assertEqual(text_input.value, "Nubeqa DE sales")
        text_input.set_value("edited text"); at.run()
        self.assertFalse(at.exception)
        text_input = next(
            t for t in at.text_input if t.label == "Describe the report")
        self.assertEqual(text_input.value, "edited text")

    def test_identity_switch_clears_state(self):
        at = self.at
        at.run()
        self.assertFalse(at.exception)
        self._full_flow(at)
        self.assertIn("plan-1", self._all_text(at))
        user = next(
            s for s in at.sidebar.selectbox
            if s.label == "Simulated requester identity")
        user.set_value(FI); at.run()
        self.assertFalse(at.exception)
        text = self._all_text(at)
        self.assertNotIn("plan-1", text)
        self.assertNotIn("rendered", text)

    def test_estate_page(self):
        at = self.at
        at.run()
        self.assertFalse(at.exception)
        radio = self._radio(at)
        radio.set_value("Estate decisions"); at.run()
        self.assertFalse(at.exception)
        text = self._all_text(at)
        self.assertIn("Estate decisions", text)

    def _seed_rendered(self, kind="report", domain="supply",
                       status="rendered"):
        self.seq[0] += 1
        pid = f"plan-{self.seq[0]}"
        plan = {
            "plan_id": pid, "revision": 2, "requester": GLOBAL,
            "kind": kind, "status": status, "domain_id": domain,
            "spec_hash": "h" * 64,
            "spec": {"kind": kind, "intent": {"grain": "snapshot",
                                            "market_ids": ["DE"],
                                            "metric_ids": []}},
            "report": {
                "spec": {"intent": {"grain": "snapshot", "metric_ids":
                                    ["otif_pct_syn"]}, "fields": []},
                "rows": [{"product_id": "P-NUB", "product_name": "Nubeqa",
                          "market_id": "DE", "market_name": "Germany",
                          "otif_pct_syn": 87.9}],
                "units": {"otif_pct_syn": "%"},
            } if status == "rendered" else None,
            "audit": [],
        }
        self.plans[pid] = plan
        return pid

    def test_fresh_resume_rendered_report(self):
        from streamlit.testing.v1 import AppTest
        pid = self._seed_rendered()
        at = AppTest.from_file(self.APP, default_timeout=30)
        at.query_params["plan_id"] = pid
        at.run()
        self.assertFalse(at.exception)
        text = self._all_text(at)
        self.assertIn(pid, text)
        self.assertIn("rendered", text)
        domain = next(s for s in at.selectbox if s.label == "Source domain")
        self.assertEqual(domain.value, "supply")
        self.assertTrue(list(at.dataframe))
        self.assertIn(pid, at.query_params.get("plan_id"))

    def test_fresh_resume_lifecycle_saved(self):
        from streamlit.testing.v1 import AppTest
        pid = self._seed_rendered(kind="lifecycle", status="approved")
        at = AppTest.from_file(self.APP, default_timeout=30)
        at.query_params["plan_id"] = pid
        at.run()
        self.assertFalse(at.exception)
        self.assertIn("Saved plans", self._all_text(at))
        self.assertIn(pid, self._all_text(at))
        self.assertIn("approved", self._all_text(at))

    def test_saved_and_ownership_pages(self):
        at = self.at
        at.run()
        self.assertFalse(at.exception)
        radio = self._radio(at)
        radio.set_value("Saved plans"); at.run()
        self.assertFalse(at.exception)
        self.assertIn("Saved plans", self._all_text(at))
        radio = self._radio(at)
        radio.set_value("Ownership & deployment"); at.run()
        self.assertFalse(at.exception)
        self.assertIn("Simulated roles", self._all_text(at))

    def test_llm_unavailable_fallback_warning_form_usable(self):
        at = self.at
        fallback = {
            "domain_id": "commercial",
            "partial_intent": {"product_ids": ["P-NUB"],
                               "market_ids": ["DE"],
                               "metric_ids": ["net_sales_m_eur_syn"],
                               "months": ["2026-01-01"], "grain": "month"},
            "proposed_intent": {"product_ids": ["P-NUB"],
                                "market_ids": ["DE"],
                                "metric_ids": ["net_sales_m_eur_syn"],
                                "months": ["2026-01-01"], "grain": "month"},
            "unresolved": [], "questions": [], "unsupported": [],
            "invalid_ids": [],
            "extraction_mode": "offline_fallback_after_llm_unavailable",
            "llm_error": "simulated outage",
            "limitations": "offline parser - review carefully",
        }

        def fake_post(path, payload, timeout=30):
            if path.endswith("/extract"):
                return _Fake(200, fallback)
            return _Fake(404, {"detail": path})

        with mock.patch(
                "smart_librarian.ui.challenge._safe_post",
                side_effect=fake_post):
            at.run()
            self.assertFalse(at.exception)
            cb = next(c for c in at.checkbox if "opt-in" in str(c.label))
            cb.set_value(True); at.run()
            text = next(i for i in at.text_input
                        if i.label == "Describe the report")
            text.set_value("Nubeqa Germany sales Jan 2026"); at.run()
            btn = next(b for b in at.button
                       if "Extract intent" in str(b.label))
            btn.click(); at.run()
        self.assertFalse(at.exception)
        body = self._all_text(at)
        self.assertIn("Extraction used the offline fallback", body)
        owner = next(s for s in at.selectbox
                     if "Accountable owner" in str(s.label))
        create = next(b for b in at.button
                      if "Create plan" in str(b.label))
        self.assertIsNone(owner.value)
        self.assertTrue(create.disabled)
        owner.set_value("OWN-001"); at.run()
        self.assertFalse(at.exception)
        create = next(b for b in at.button
                      if "Create plan" in str(b.label))
        self.assertFalse(create.disabled)


if __name__ == "__main__":
    unittest.main()
