"""Workspace navigation tests: auxiliary pages via mocked HTTP, plus
preservation of the default Build & reuse workflow bootstrap.

Runs under unittest discovery - no live servers required. httpx calls
made by the Streamlit app are intercepted with canned responses.
"""

import copy
import unittest
from unittest import mock

import httpx
from streamlit.testing.v1 import AppTest

APP_PATH = "apps/streamlit_app.py"

_DOMAINS = {
    "domains": [
        {
            "domain_id": "sales",
            "display_name": "Sales",
            "dimension_labels": {"products": "Products",
                                 "markets": "Markets"},
        }
    ],
    "simulated": True,
}

_CAPABILITIES = {"configured": False, "model": "test", "label": None}

_USERS = {
    "users": [
        {"user_id": "DEMO-USER-GLOBAL", "name": "Global Analyst",
         "roles": ["analyst"]},
        {"user_id": "DEMO-USER-FI", "name": "Finland Analyst",
         "roles": ["analyst"]},
    ]
}

_CATALOG = {
    "choices": {
        "dataset_id": "DEMO-DATASET",
        "model": {"snapshot_as_of": "2026-04-01"},
        "dimension_labels": {"products": "Products", "markets": "Markets"},
        "products": [{"product_id": "DEMO-P-NUB", "product_name": "Nubeqa"}],
        "markets": [{"market_id": "DE", "market_name": "Germany"}],
        "metrics": [{"metric_id": "DEMO-NET-SALES", "name": "Net Sales",
                     "unit": "EUR", "approval_status": "approved"}],
        "months": ["2026-01-01"],
        "grain_options": ["month"],
    }
}

_CHALLENGE = {
    "source_file": "pack.xlsx",
    "source_sha256": "ab" * 32,
    "retrieved_at_utc": "2026-11-07T00:00:00+00:00",
    "data_classification": "official_synthetic_challenge",
    "disclaimer": "Synthetic estate metadata.",
    "tables": {
        "Analytics_Assets": [
            {"_source_row": 2, "asset_id": "AA-1", "asset_name": "Sales QBR",
             "platform": "Power BI", "model_id": "SM-1",
             "owner_id": "OW-1"},
        ],
        "Semantic_Models": [
            {"_source_row": 5, "model_id": "SM-1", "model_name": "Sales SM"},
        ],
        "Owners": [
            {"_source_row": 3, "owner_id": "OW-1", "owner_name": "Owner A"},
        ],
        "KPI_Catalog": [
            {"_source_row": 2, "kpi_id": "KPI-1", "kpi_name": "Net Sales",
             "unit": "EUR"},
        ],
        "Asset_KPI_Map": [
            {"_source_row": 2, "asset_id": "AA-1", "kpi_id": "KPI-1"},
        ],
        "Asset_Usage": [
            {"_source_row": 2, "asset_id": "AA-1", "month": "2026-01",
             "views": 10, "unique_users": 4},
        ],
        "Lineage_Edges": [
            {"_source_row": 2, "source_id": "SM-1", "target_id": "AA-1"},
        ],
        "Governance_Signals": [
            {"_source_row": 2, "asset_id": "AA-1", "signal_code": "STALE"},
        ],
        "Migration_Backlog": [
            {"_source_row": 2, "source_asset_id": "AA-1",
             "recommended_path_candidate": "consolidate"},
        ],
        "Data_Quality": [
            {"_source_row": 2, "record_id": "OW-1", "field": "email",
             "severity": "low"},
        ],
        "Governance_Rules": [
            {"rule_id": "GR-1", "rule_name": "Naming"},
        ],
    },
}

_PUBLIC = {
    "source_url": "https://reports.bayer.com/example",
    "source_title": "Public source",
    "source_sha256": "cd" * 32,
    "retrieved_at_utc": "2026-11-07T00:00:00+00:00",
    "data_classification": "public_reported_actual",
    "disclaimer": "Public actuals.",
    "unit": "EUR million",
    "grain": "product x fiscal_year",
    "rows": [
        {"product_name": "Nubeqa", "year": 2024, "sales_eur_million": 1523,
         "source_table": "t", "source_row_label": "Nubeqa"},
        {"product_name": "Nubeqa", "year": 2025, "sales_eur_million": 2385,
         "source_table": "t", "source_row_label": "Nubeqa"},
    ],
}

POST_CALLS = []


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def _fake_get(url, params=None, timeout=None):
    if url.endswith("/api/domains"):
        return _FakeResponse(200, _DOMAINS)
    if url.endswith("/api/capabilities"):
        return _FakeResponse(200, _CAPABILITIES)
    if url.endswith("/api/demo-users"):
        return _FakeResponse(200, _USERS)
    if url.endswith("/api/catalog"):
        return _FakeResponse(200, _CATALOG)
    if url.endswith("/api/evidence/challenge"):
        return _FakeResponse(200, _CHALLENGE)
    if url.endswith("/api/evidence/public"):
        return _FakeResponse(200, _PUBLIC)
    if url.endswith("/audit"):
        return _FakeResponse(200, {"events": []})
    if "/api/assets" in url:
        return _FakeResponse(200, {"assets": []})
    if "/api/sessions/" in url:
        return _FakeResponse(200, {"session_id": "sess-1",
                                   "domain_id": "sales", "messages": []})
    return _FakeResponse(404, {"detail": url})


def _fake_post(url, json=None, timeout=None):
    POST_CALLS.append(url)
    if url.endswith("/api/sessions"):
        return _FakeResponse(200, {"session_id": "sess-1"})
    return _FakeResponse(404, {"detail": url})


def _all_text(at):
    parts = [m.value for m in at.markdown]
    for kind in ("caption", "info", "warning", "error", "success",
                 "subheader", "header"):
        parts.extend(e.value for e in getattr(at, kind, []))
    return " ".join(parts)


class WorkspaceNavigationTests(unittest.TestCase):
    def setUp(self):
        POST_CALLS.clear()
        get_patch = mock.patch.object(httpx, "get", side_effect=_fake_get)
        post_patch = mock.patch.object(httpx, "post", side_effect=_fake_post)
        get_patch.start()
        post_patch.start()
        self.addCleanup(get_patch.stop)
        self.addCleanup(post_patch.stop)
        self.at = AppTest.from_file(APP_PATH, default_timeout=30)
        self.at.run()
        self.assertFalse(self.at.exception)

    def _workspace_radio(self):
        radios = list(self.at.sidebar.radio) + list(self.at.radio)
        return next(r for r in radios if r.label == "Workspace")

    def _switch(self, workspace):
        radio = self._workspace_radio()
        radio.set_value(workspace)
        self.at.run()
        self.assertFalse(self.at.exception)

    def test_default_workspace_is_build_and_reuse(self):
        at = self.at
        radio = self._workspace_radio()
        self.assertEqual(radio.value, "Build & reuse")
        text = _all_text(at)
        self.assertIn("Build less. Trust more.", text)
        self.assertIn("Confirm intent", text)
        confirm = next(b for b in at.button if b.label == "Confirm intent")
        self.assertTrue(confirm.disabled)
        self.assertTrue(
            any(url.endswith("/api/sessions") for url in POST_CALLS)
        )

    def test_challenge_estate_page(self):
        POST_CALLS.clear()
        self._switch("Challenge estate")
        text = _all_text(self.at)
        self.assertIn("official_synthetic_challenge", text)
        self.assertIn("Sales QBR", " ".join(
            str(v) for df in self.at.dataframe for v in df.value.values
        ))
        self.assertFalse(
            any(url.endswith("/api/sessions") for url in POST_CALLS)
        )
        self.assertIn("scenario inputs", text)
        self.assertIn("not a certification", text)

    def test_public_financials_page(self):
        self._switch("Public financials")
        text = _all_text(self.at)
        self.assertIn("public_reported_actual", text)
        self.assertIn("EUR million", text)
        self.assertIn("monthly", text)
        labels = {b.label for b in self.at.get("download_button")}
        self.assertIn("Download Power BI public-data kit (ZIP)", labels)
        self.assertIn("Download rows as CSV", labels)
        self.assertIn("Download rows as JSON", labels)

    def test_deployment_readiness_page(self):
        self._switch("Deployment readiness")
        text = _all_text(self.at)
        self.assertIn("Entra ID", text)
        self.assertIn("Power BI workspace", text)
        self.assertIn("not production", text.lower())

    def test_returning_to_build_workspace_restores_flow(self):
        self._switch("Challenge estate")
        POST_CALLS.clear()
        self._switch("Build & reuse")
        text = _all_text(self.at)
        self.assertIn("Confirm intent", text)

    def test_identity_survives_workspace_roundtrip(self):
        select = next(
            s for s in self.at.sidebar.selectbox
            if s.label == "Simulated user"
        )
        select.set_value("DEMO-USER-FI")
        self.at.run()
        self.assertFalse(self.at.exception)
        sessions_posts = [
            u for u in POST_CALLS if u.endswith("/api/sessions")
        ]
        self.assertEqual(len(sessions_posts), 2)

        self._switch("Public financials")
        self._switch("Build & reuse")
        select = next(
            s for s in self.at.sidebar.selectbox
            if s.label == "Simulated user"
        )
        self.assertEqual(select.value, "DEMO-USER-FI")
        sessions_posts = [
            u for u in POST_CALLS if u.endswith("/api/sessions")
        ]
        self.assertEqual(len(sessions_posts), 2)
        text = _all_text(self.at)
        self.assertIn("DEMO-USER-FI", text)


class PublicDefaultDomainTests(unittest.TestCase):
    """Default workspace boots on public_sales with annual metadata."""

    def setUp(self):
        self._domains = copy.deepcopy(_DOMAINS)
        self._domains["domains"].insert(0, {
            "domain_id": "public_sales",
            "display_name": "Bayer public sales (real data)",
            "dimension_labels": {"products": "Products",
                                 "markets": "Markets"},
        })
        self._catalog = copy.deepcopy(_CATALOG)
        self._catalog["choices"].update({
            "period_label": "Fiscal years",
            "time_column": "fiscal_year",
            "synthetic_record": False,
            "data_classification": "public_reported_actual",
            "months": ["2024", "2025"],
            "grain_options": ["year"],
            "products": [{"product_id": "PUBLIC-NUBEQA",
                          "product_name": "Nubeqa"}],
            "markets": [{"market_id": "GLOBAL", "market_name": "Global"}],
            "metrics": [{"metric_id": "PUBLIC-REPORTED-SALES",
                         "name": "Reported sales", "unit": "EUR million",
                         "approval_status": "approved"}],
        })

        self._session_payload = {
            "session_id": "sess-1", "domain_id": "public_sales",
            "messages": [],
        }

        def fake_get(url, params=None, timeout=None):
            if url.endswith("/api/domains"):
                return _FakeResponse(200, self._domains)
            if url.endswith("/api/catalog"):
                return _FakeResponse(200, self._catalog)
            if url.endswith("/audit"):
                return _FakeResponse(200, {"events": []})
            if "/api/sessions/" in url:
                return _FakeResponse(200, self._session_payload)
            return _fake_get(url, params=params, timeout=timeout)

        get_patch = mock.patch.object(httpx, "get", side_effect=fake_get)
        post_patch = mock.patch.object(httpx, "post", side_effect=_fake_post)
        get_patch.start()
        post_patch.start()
        self.addCleanup(get_patch.stop)
        self.addCleanup(post_patch.stop)
        self.at = AppTest.from_file(APP_PATH, default_timeout=30)
        self.at.run()
        self.assertFalse(self.at.exception)

    def test_public_domain_is_default(self):
        selectboxes = (
            list(self.at.sidebar.selectbox) + list(self.at.selectbox)
        )
        domain = next(s for s in selectboxes if s.label == "Domain")
        self.assertEqual(domain.value, "public_sales")
        prompt = next(
            t for t in self.at.text_input
            if t.label == "Describe the report you want"
        )
        self.assertIn("Nubeqa", prompt.placeholder or "")
        self.assertIn("2025", prompt.placeholder or "")
        self.assertTrue(
            any(m.label == "Fiscal years" for m in self.at.multiselect)
        )
        self.assertFalse(self.at.exception)

    def test_public_proposal_evidence_heading(self):
        self._session_payload = {
            "session_id": "sess-1", "domain_id": "public_sales",
            "messages": [], "outcome": "PROPOSE_BUILD",
            "proposal": {
                "proposal_id": "prop-1", "spec_hash": "ab" * 32,
                "approval_status": "pending",
                "spec": {"model_id": "PUBLIC-MODEL"},
            },
            "evidence": [{
                "evidence_id": "EV-1", "kind": "snapshot",
                "detail": "frozen public rows", "ref_path": "evidence",
                "record_id": "row-1", "status": "loaded",
            }],
        }
        self.at = AppTest.from_file(APP_PATH, default_timeout=30)
        self.at.run()
        self.assertFalse(self.at.exception)
        labels = [e.label for e in self.at.expander]
        self.assertIn(
            "Evidence (frozen public-source snapshot; "
            "simulated governance)",
            labels,
        )
        self.assertNotIn(
            "Evidence (simulated catalog snapshot)", labels
        )


if __name__ == "__main__":
    unittest.main()
