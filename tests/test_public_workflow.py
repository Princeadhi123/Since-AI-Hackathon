"""Governed public-actuals domain: lifecycle gates, rendering, artifacts.

Integration tests only - no numeric gold answers (lead-authored value
checks live elsewhere). Uses the real frozen evidence file through the
normal create_app path (demo_dir=None mounts public_sales).
"""

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from smart_librarian.api.app import create_app
from smart_librarian.reporting.exports import (
    build_report_bundle,
    export_report_html,
)
from smart_librarian.reporting.powerbi import build_powerbi_import_bundle

INTENT_2025 = {
    "product_ids": ["PUBLIC-NUBEQA"],
    "market_ids": ["GLOBAL"],
    "metric_ids": ["PUBLIC-REPORTED-SALES"],
    "months": ["2025"],
    "grain": "year",
}

INTENT_MULTI = {
    "product_ids": ["PUBLIC-NUBEQA", "PUBLIC-KERENDIA", "PUBLIC-EYLEA",
                    "PUBLIC-XARELTO"],
    "market_ids": ["GLOBAL"],
    "metric_ids": ["PUBLIC-REPORTED-SALES"],
    "months": ["2024", "2025"],
    "grain": "year",
}


class PublicWorkflowTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "runtime.sqlite"
        self.client = TestClient(
            create_app(runtime_db=db, include_synthetic=True)
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _session(self, user="DEMO-USER-GLOBAL"):
        response = self.client.post(
            "/api/sessions",
            json={"user_id": user, "domain_id": "public_sales"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["session_id"]

    def _confirm(self, session_id, intent=INTENT_2025,
                 user="DEMO-USER-GLOBAL"):
        return self.client.post(
            f"/api/sessions/{session_id}/intent",
            json={"user_id": user, "intent": intent},
        )

    def _decide(self, session_id, proposal, decision="approve",
                actor="DEMO-PUBLIC-APPROVER",
                spec_hash=None, user="DEMO-USER-GLOBAL"):
        return self.client.post(
            f"/api/sessions/{session_id}/approval",
            json={
                "user_id": user,
                "proposal_id": proposal["proposal_id"],
                "spec_hash": spec_hash or proposal["spec_hash"],
                "decision": decision,
                "actor_user_id": actor,
            },
        )

    def _render(self, session_id, user="DEMO-USER-GLOBAL"):
        return self.client.get(
            f"/api/sessions/{session_id}/report", params={"user_id": user}
        )

    def _approved_session(self, intent=INTENT_2025):
        session_id = self._session()
        confirmed = self._confirm(session_id, intent)
        self.assertEqual(confirmed.status_code, 200)
        state = confirmed.json()
        self.assertEqual(state["outcome"], "PROPOSE_BUILD")
        proposal = state["proposal"]
        self.assertEqual(proposal["approval_status"], "pending")
        decided = self._decide(session_id, proposal)
        self.assertEqual(decided.status_code, 200, decided.text)
        return session_id, decided.json()

    def test_domains_lists_public_first(self):
        domains = self.client.get("/api/domains").json()["domains"]
        self.assertEqual(domains[0]["domain_id"], "public_sales")
        self.assertEqual(
            domains[0]["display_name"], "Bayer public sales (real data)"
        )
        self.assertIn("sales", [d["domain_id"] for d in domains])

    def test_public_users_and_catalog(self):
        users = self.client.get(
            "/api/demo-users", params={"domain_id": "public_sales"}
        ).json()["users"]
        self.assertEqual(
            {u["user_id"] for u in users},
            {"DEMO-USER-GLOBAL", "DEMO-USER-FI"},
        )
        catalog = self.client.get(
            "/api/catalog",
            params={"user_id": "DEMO-USER-GLOBAL",
                    "domain_id": "public_sales"},
        ).json()
        choices = catalog["choices"]
        self.assertEqual(choices["period_label"], "Fiscal years")
        self.assertEqual(choices["time_column"], "fiscal_year")
        self.assertFalse(choices["synthetic_record"])
        self.assertEqual(
            choices["data_classification"], "public_reported_actual"
        )
        self.assertEqual(choices["months"], ["2024", "2025"])

    def test_pending_report_blocked_409(self):
        session_id = self._session()
        confirmed = self._confirm(session_id)
        self.assertEqual(confirmed.json()["outcome"], "PROPOSE_BUILD")
        self.assertEqual(self._render(session_id).status_code, 409)

    def test_wrong_actor_and_wrong_hash_rejected(self):
        session_id = self._session()
        proposal = self._confirm(session_id).json()["proposal"]
        response = self._decide(session_id, proposal, actor="DEMO-APPROVER")
        self.assertEqual(response.status_code, 403)
        response = self._decide(
            session_id, proposal, spec_hash="0" * 64
        )
        self.assertEqual(response.status_code, 409)

    def test_approval_render_and_metadata(self):
        session_id, state = self._approved_session()
        spec = state["proposal"]["spec"]
        self.assertFalse(spec["synthetic_record"])
        self.assertEqual(
            spec["data_classification"], "public_reported_actual"
        )
        self.assertEqual(spec["time_column"], "fiscal_year")
        self.assertIn("source_url", spec["source_provenance"])
        rendered = self._render(session_id)
        self.assertEqual(rendered.status_code, 200, rendered.text)
        report = rendered.json()
        self.assertEqual(report["time_column"], "fiscal_year")
        self.assertEqual(
            report["data_classification"], "public_reported_actual"
        )
        self.assertFalse(report["synthetic_record"])
        self.assertTrue(report["rows"])
        for row in report["rows"]:
            self.assertIn("fiscal_year", row)
            self.assertNotIn("month", row)
            self.assertIn("source_table", row)
            self.assertIn("source_row_label", row)
        self.assertEqual(report["units"]["PUBLIC-REPORTED-SALES"],
                         "EUR million")
        self.assertEqual(
            list(report["totals"]), ["PUBLIC-REPORTED-SALES"]
        )
        self.assertTrue(report["registered_asset_id"])

    def test_multi_year_totals_empty(self):
        session_id, _state = self._approved_session(INTENT_MULTI)
        report = self._render(session_id).json()
        self.assertEqual(report["totals"], {})
        self.assertEqual(len(report["rows"]), 8)

    def test_registered_scope_reuses_across_sessions(self):
        first_id, _ = self._approved_session()
        self.assertEqual(self._render(first_id).status_code, 200)
        second_id = self._session()
        confirmed = self._confirm(second_id)
        self.assertEqual(confirmed.status_code, 200)
        state = confirmed.json()
        self.assertEqual(state["outcome"], "REUSE")
        self.assertEqual(
            state["proposal"]["approval_status"], "not_required"
        )
        self.assertEqual(self._render(second_id).status_code, 200)

    def test_unsupported_scope_and_grain_fail_closed(self):
        session_id = self._session()
        denied = self._confirm(
            session_id, dict(INTENT_2025, market_ids=["GLOBAL", "XX"])
        ).json()
        self.assertEqual(denied["outcome"], "ACCESS_DENIED")
        for intent in (
            dict(INTENT_2025, months=["2026"]),
            dict(INTENT_2025, months=["2025-01-01"]),
            dict(INTENT_2025, grain="month"),
            dict(INTENT_2025, metric_ids=["PUBLIC-FORECAST"]),
            dict(INTENT_2025, product_ids=["PUBLIC-UNKNOWN"]),
        ):
            with self.subTest(intent=intent):
                response = self._confirm(session_id, intent)
                state = response.json()
                self.assertEqual(state["outcome"], "NEEDS_REVIEW")
                self.assertIsNone(state["proposal"])

    def test_finland_identity_denied_global_scope(self):
        session_id = self._session(user="DEMO-USER-FI")
        state = self._confirm(
            session_id, INTENT_2025, user="DEMO-USER-FI"
        ).json()
        self.assertEqual(state["outcome"], "ACCESS_DENIED")

    def test_offline_parse_rejects_subannual_and_country(self):
        session_id = self._session()
        for text in (
            "Show monthly reported sales for Nubeqa",
            "Show Nubeqa sales in Germany for 2025",
            "Show Nubeqa forecast for 2025",
        ):
            with self.subTest(text=text):
                state = self.client.post(
                    f"/api/sessions/{session_id}/messages",
                    json={"user_id": "DEMO-USER-GLOBAL", "text": text,
                          "use_llm": False},
                ).json()
                self.assertEqual(state["outcome"], "CLARIFY")
                self.assertTrue(state["unsupported"])

    def test_offline_parse_complete_annual_intent(self):
        session_id = self._session()
        state = self.client.post(
            f"/api/sessions/{session_id}/messages",
            json={"user_id": "DEMO-USER-GLOBAL",
                  "text": "Show global reported sales for Nubeqa in 2025",
                  "use_llm": False},
        ).json()
        self.assertEqual(state["outcome"], "CONFIRM_INTENT")
        partial = state["partial_intent"]
        self.assertEqual(partial["product_ids"], ["PUBLIC-NUBEQA"])
        self.assertEqual(partial["months"], ["2025"])
        self.assertEqual(partial["grain"], "year")

    def _public_report(self, intent=INTENT_2025):
        session_id, _ = self._approved_session(intent)
        return self._render(session_id).json()

    def test_html_export_public_banner_and_year(self):
        page = export_report_html(self._public_report())
        self.assertIn("Published actual", page)
        self.assertNotIn("Synthetic demo data", page)
        self.assertIn("fiscal_year", page)
        self.assertIn("reports.bayer.com", page)
        self.assertIn("fiscal year", page)

    def test_bundle_csv_uses_fiscal_year(self):
        bundle = zipfile.ZipFile(
            io.BytesIO(build_report_bundle(self._public_report()))
        )
        csv_text = bundle.read("report.csv").decode("utf-8")
        self.assertIn("fiscal_year", csv_text.splitlines()[0])
        readme = bundle.read("README.txt").decode("utf-8")
        self.assertIn("published actual", readme.lower())
        self.assertIn("fiscal_year", readme)

    def test_bundle_readme_annual_instructions(self):
        for intent in (INTENT_2025, INTENT_MULTI):
            with self.subTest(months=intent["months"]):
                bundle = zipfile.ZipFile(
                    io.BytesIO(
                        build_report_bundle(self._public_report(intent))
                    )
                )
                readme = bundle.read("README.txt").decode("utf-8")
                self.assertIn("fiscal_year", readme)
                self.assertNotIn("as a date column", readme)
                self.assertIn("whole-number", readme)
                self.assertIn("EUR million", readme)
                self.assertIn("cross-year", readme)

    def test_powerbi_readme_grain_and_totals_wording(self):
        bundle = zipfile.ZipFile(
            io.BytesIO(
                build_powerbi_import_bundle(
                    self._public_report(INTENT_2025)
                )
            )
        )
        readme = bundle.read("README.txt").decode("utf-8")
        self.assertIn("x fiscal_year", readme)
        self.assertNotIn("x month", readme)
        self.assertIn("single frozen totals row", readme)
        bundle = zipfile.ZipFile(
            io.BytesIO(
                build_powerbi_import_bundle(
                    self._public_report(INTENT_MULTI)
                )
            )
        )
        readme = bundle.read("README.txt").decode("utf-8")
        self.assertIn("x fiscal_year", readme)
        self.assertNotIn("x month", readme)
        self.assertNotIn("single frozen totals row", readme)
        self.assertIn("header", readme.lower())
        self.assertIn("cross-year", readme)

    def test_powerbi_kit_public(self):
        report = self._public_report(INTENT_MULTI)
        bundle = zipfile.ZipFile(
            io.BytesIO(build_powerbi_import_bundle(report))
        )
        report_m = bundle.read("PowerQuery_Report.m").decode("utf-8")
        self.assertIn('"fiscal_year", Int64.Type', report_m)
        self.assertIn('"source_row_label", type text', report_m)
        self.assertIn("QuoteStyle.Csv", report_m)
        csv_text = bundle.read("report.csv").decode("utf-8")
        self.assertIn("source_row_label", csv_text.splitlines()[0])
        totals_lines = [
            line for line in bundle.read("totals.csv").decode("utf-8")
            .splitlines() if line.strip()
        ]
        self.assertEqual(totals_lines, ["PUBLIC-REPORTED-SALES"])
        readme = bundle.read("README.txt").decode("utf-8")
        self.assertIn("cross-year", readme)
        self.assertIn("EUR million", readme)
        provenance = json.loads(bundle.read("provenance.json"))
        self.assertEqual(
            provenance["data_classification"], "public_reported_actual"
        )
        self.assertEqual(provenance["time_column"], "fiscal_year")
        self.assertIn("source_url", provenance["source_provenance"])

    def test_powerbi_kit_single_year_has_totals_row(self):
        report = self._public_report(INTENT_2025)
        bundle = zipfile.ZipFile(
            io.BytesIO(build_powerbi_import_bundle(report))
        )
        totals_lines = [
            line for line in bundle.read("totals.csv").decode("utf-8")
            .splitlines() if line.strip()
        ]
        self.assertEqual(len(totals_lines), 2)


if __name__ == "__main__":
    unittest.main()
