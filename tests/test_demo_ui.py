"""AppTest coverage for the real-data-only demo UI (mocked HTTP only).

The new smart_librarian.ui.demo UI is exercised through the
apps/streamlit_app.py dispatcher with canned API responses. No live
servers and no business arithmetic - assertions cover transport, widget
state and disclosure text only.
"""

import unittest
from unittest import mock

import httpx
from streamlit.delta_generator import DeltaGenerator
from streamlit.testing.v1 import AppTest

APP_PATH = "apps/streamlit_app.py"

_DOMAINS = {
    "domains": [
        {
            "domain_id": "public_sales",
            "display_name": "Bayer public sales (real data)",
            "dimension_labels": {"products": "Products",
                                 "markets": "Markets"},
            "data_classification": "public_reported_actual",
        }
    ],
    "real_data_only": True,
    "simulated": True,
}

_CAPABILITIES = {"configured": False, "model": "test", "label": None}

_USERS = {
    "users": [
        {"user_id": "DEMO-USER-GLOBAL", "name": "Global Analyst",
         "allowed_market_ids": ["GLOBAL"]},
    ]
}

_PERIODS = [
    {"period_id": "2024", "period_kind": "year", "label": "FY 2024",
     "start_date": "2024-01-01", "end_date": "2024-12-31"},
    {"period_id": "2025", "period_kind": "year", "label": "FY 2025",
     "start_date": "2025-01-01", "end_date": "2025-12-31"},
    {"period_id": "2025-Q2", "period_kind": "quarter", "label": "Q2 2025",
     "start_date": "2025-04-01", "end_date": "2025-06-30"},
    {"period_id": "2026-Q1", "period_kind": "quarter", "label": "Q1 2026",
     "start_date": "2026-01-01", "end_date": "2026-03-31"},
    {"period_id": "2026-Q2", "period_kind": "quarter", "label": "Q2 2026",
     "start_date": "2026-04-01", "end_date": "2026-06-30"},
    {"period_id": "2026-H1", "period_kind": "half_year", "label": "H1 2026",
     "start_date": "2026-01-01", "end_date": "2026-06-30"},
]

_CATALOG = {
    "choices": {
        "dataset_id": "PUBLIC-FINANCIALS-V2",
        "domain_id": "public_sales",
        "dimension_labels": {"products": "Products", "markets": "Markets"},
        "synthetic_record": False,
        "data_classification": "public_reported_actual",
        "period_label": "Reporting periods",
        "time_column": "period",
        "products": [
            {"product_id": "PUBLIC-NUBEQA", "product_name": "Nubeqa"},
            {"product_id": "PUBLIC-EYLEA", "product_name": "Eylea"},
        ],
        "markets": [{"market_id": "GLOBAL", "market_name": "Global"}],
        "metrics": [{"metric_id": "PUBLIC-REPORTED-SALES",
                     "name": "Reported Sales", "unit": "EUR million",
                     "approval_status": "approved"}],
        "months": [p["period_id"] for p in _PERIODS],
        "periods": _PERIODS,
        "grain_options": ["year", "quarter", "half_year"],
        "model": {"model_id": "PUBLIC-MODEL-FINANCIALS",
                  "snapshot_as_of": "2026-11-07"},
    },
    "user": {"user_id": "DEMO-USER-GLOBAL"},
}

_ACTORS = {
    "actors": [{
        "actor_id": "DEMO-PUBLIC-APPROVER",
        "name": "Demo Public-data Approver",
        "roles": ["approver"], "allowed_market_ids": ["GLOBAL"],
    }]
}

_SNAPSHOT = {
    "data_classification": "public_reported_actual",
    "unit": "EUR million",
    "grain": "product x period",
    "disclaimer": "Published actuals only.",
    "retrieved_at_utc": "2026-11-07T00:00:00+00:00",
    "products": [{"product_id": "PUBLIC-NUBEQA", "product_name": "Nubeqa"}],
    "periods": _PERIODS,
    "sources": [{
        "source_id": "SRC-1",
        "source_url": "https://reports.bayer.com/example",
        "source_title": "Annual Report",
        "source_sha256": "cd" * 32,
        "source_snapshot": "snapshot.html",
        "retrieved_at_utc": "2026-11-07T00:00:00+00:00",
        "notes": "official publisher page",
    }],
    "rows": [
        {"product_id": "PUBLIC-NUBEQA", "product_name": "Nubeqa",
         "market_id": "GLOBAL", "market_name": "Global",
         "period": "2025", "period_kind": "year",
         "PUBLIC-REPORTED-SALES": 2385, "source_id": "SRC-1",
         "source_table": "t", "source_row_label": "Nubeqa",
         "source_column": "2025", "source_row": "Nubeqa"},
        {"product_id": "PUBLIC-NUBEQA", "product_name": "Nubeqa",
         "market_id": "GLOBAL", "market_name": "Global",
         "period": "2026-Q1", "period_kind": "quarter",
         "PUBLIC-REPORTED-SALES": 700, "source_id": "SRC-1",
         "source_table": "t", "source_row_label": "Nubeqa",
         "source_column": "Q1", "source_row": "Nubeqa"},
    ],
}

POST_CALLS = []
POST_BODIES = []
SESSION_STATE = {}
LAST_INTENT = {}
ASSETS = []
SESSION_COUNTER = [0]


def _empty_session():
    return {"session_id": "sess-1", "domain_id": "public_sales",
            "messages": [], "partial_intent": {}}


def _intent_state(intent):
    spec_intent = {
        "product_ids": sorted(intent.get("product_ids") or []),
        "market_ids": sorted(intent.get("market_ids") or []),
        "metric_ids": sorted(intent.get("metric_ids") or []),
        "months": sorted(intent.get("months") or []),
        "grain": intent.get("grain"),
    }
    return {
        "session_id": "sess-1", "domain_id": "public_sales",
        "messages": [], "outcome": "PROPOSE_BUILD",
        "partial_intent": spec_intent,
        "proposal": {
            "proposal_id": "prop-1", "spec_hash": "ab" * 32,
            "approval_status": "pending",
            "spec": {
                "model_id": "PUBLIC-MODEL-FINANCIALS",
                "intent": spec_intent,
                "requested_metrics": [{
                    "metric_id": "PUBLIC-REPORTED-SALES",
                    "name": "Reported Sales", "unit": "EUR million",
                }],
                "source_provenance": {"sources": _SNAPSHOT["sources"]},
            },
        },
        "evidence": [{
            "evidence_id": "EV-1", "kind": "snapshot",
            "detail": "frozen public rows", "ref_path": "public-financials",
            "record_id": "row-1", "status": "loaded",
        }],
    }


def _report():
    return {
        "rows": list(_SNAPSHOT["rows"][:1]),
        "totals": {"PUBLIC-REPORTED-SALES": 2385},
        "units": {"PUBLIC-REPORTED-SALES": "EUR million"},
        "time_column": "period", "time_label": "Reporting period",
        "data_classification": "public_reported_actual",
        "synthetic_record": False,
        "registered_asset_id": "GEN-ABCDEF0123456789",
        "asset": {"name": "Generated Reported Sales",
                  "owner_name": "Demo Steward", "endorsement": "promoted"},
        "spec": _intent_state({})["proposal"]["spec"],
        "source_provenance": {"sources": _SNAPSHOT["sources"]},
        "aggregation_note": "Published global reported sales in EUR million.",
    }


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
    if url.endswith("/api/governance-actors"):
        return _FakeResponse(200, _ACTORS)
    if url.endswith("/api/public-financials"):
        return _FakeResponse(200, _SNAPSHOT)
    if url.endswith("/api/assets"):
        return _FakeResponse(200, {"assets": list(ASSETS),
                                 "simulated": True})
    if url.endswith("/audit"):
        return _FakeResponse(200, {"events": []})
    if url.endswith("/report"):
        return _FakeResponse(200, _report())
    if "/api/sessions/foreign" in url:
        return _FakeResponse(403, {"detail": "different identity"})
    if "/api/sessions/" in url:
        return _FakeResponse(200, SESSION_STATE or _empty_session())
    return _FakeResponse(404, {"detail": url})


def _fake_post(url, json=None, timeout=None):
    POST_CALLS.append(url)
    POST_BODIES.append((url, dict(json or {})))
    if url.endswith("/api/sessions"):
        SESSION_COUNTER[0] += 1
        return _FakeResponse(
            200, {"session_id": f"sess-{SESSION_COUNTER[0]}"}
        )
    if url.endswith("/messages"):
        return _FakeResponse(200, {
            "session_id": "sess-1", "domain_id": "public_sales",
            "extraction_mode": (
                "llm" if (json or {}).get("use_llm") else "offline"
            ),
            "outcome": "CLARIFY",
            "unsupported": ["Requested weekly grain is not supported."],
            "questions": ["Which reporting period(s)?"],
            "messages": [{"role": "assistant",
                          "text": "Unsupported requirements detected."}],
            "partial_intent": {},
        })
    if url.endswith("/reuse"):
        state = _intent_state(LAST_INTENT)
        state["outcome"] = "REUSE"
        state["proposal"]["approval_status"] = "not_required"
        state["proposal"]["spec"]["source_asset_id"] = "GEN-SEED"
        return _FakeResponse(200, {"session_id": "sess-reuse",
                                   "state": state})
    if url.endswith("/intent"):
        LAST_INTENT.clear()
        LAST_INTENT.update(json["intent"])
        return _FakeResponse(200, _intent_state(json["intent"]))
    if url.endswith("/approval"):
        state = _intent_state(LAST_INTENT)
        state["proposal"]["approval_status"] = "approved"
        return _FakeResponse(200, state)
    return _FakeResponse(404, {"detail": url})


def _all_text(at):
    parts = [m.value for m in at.markdown]
    for kind in ("caption", "info", "warning", "error", "success",
                 "subheader", "header"):
        parts.extend(e.value for e in getattr(at, kind, []))
    return " ".join(parts)


def _by_label(widgets, label):
    for widget in widgets:
        if getattr(widget, "label", None) == label:
            return widget
    return None


class RealOnlyDemoUiTests(unittest.TestCase):
    def setUp(self):
        POST_CALLS.clear()
        POST_BODIES.clear()
        SESSION_STATE.clear()
        LAST_INTENT.clear()
        ASSETS.clear()
        SESSION_COUNTER[0] = 0
        get_patch = mock.patch.object(httpx, "get", side_effect=_fake_get)
        post_patch = mock.patch.object(httpx, "post", side_effect=_fake_post)
        get_patch.start()
        post_patch.start()
        self.addCleanup(get_patch.stop)
        self.addCleanup(post_patch.stop)
        self.at = AppTest.from_file(APP_PATH, default_timeout=30)
        self.at.run()
        self.assertFalse(self.at.exception)

    def _workspace(self, name):
        radio = next(
            r for r in
            list(self.at.sidebar.radio) + list(self.at.radio)
            if r.label == "Workspace"
        )
        radio.set_value(name)
        self.at.run()
        self.assertFalse(self.at.exception)

    def test_startup_real_only_navigation(self):
        selectboxes = (
            list(self.at.sidebar.selectbox) + list(self.at.selectbox)
        )
        self.assertFalse(any(s.label == "Domain" for s in selectboxes))
        radio = next(
            r for r in
            list(self.at.sidebar.radio) + list(self.at.radio)
            if r.label == "Workspace"
        )
        self.assertEqual(radio.value, "Report builder")
        self.assertEqual(
            set(radio.options),
            {"Report builder", "Performance explorer", "Saved reports",
             "Sources & coverage"},
        )
        text = _all_text(self.at)
        self.assertIn("Real data only", text)
        self.assertIn("Published actual sales", text)
        self.assertNotIn("synthetic", text.lower().replace("simulated", ""))

    def test_starter_prefills_without_confirming(self):
        starter = _by_label(self.at.button, "Nubeqa annual performance")
        self.assertIsNotNone(starter)
        starter.click()
        self.at.run()
        self.assertFalse(self.at.exception)
        products = _by_label(self.at.multiselect, "Products")
        self.assertEqual(products.value, ["PUBLIC-NUBEQA"])
        periods = _by_label(self.at.multiselect, "Reporting periods")
        self.assertEqual(sorted(periods.value), ["2024", "2025"])
        self.assertFalse(
            any(u.endswith("/intent") for u in POST_CALLS)
        )
        self.assertEqual(
            _by_label(self.at.selectbox, "Period type").value, "Annual"
        )

    def test_period_type_filters_periods(self):
        _by_label(self.at.selectbox, "Period type").set_value("Quarterly")
        self.at.run()
        self.assertFalse(self.at.exception)
        periods = _by_label(self.at.multiselect, "Reporting periods")
        self.assertEqual(
            sorted(periods.options), ["Q1 2026", "Q2 2025", "Q2 2026"]
        )
        _by_label(self.at.selectbox, "Period type").set_value("Half-year")
        self.at.run()
        periods = _by_label(self.at.multiselect, "Reporting periods")
        self.assertEqual(list(periods.options), ["H1 2026"])

    def test_send_unsupported_blocks_confirm_until_ack(self):
        _by_label(
            self.at.text_input, "Describe the report you want"
        ).set_value("weekly Nubeqa sales")
        self.at.run()
        _by_label(self.at.button, "Send").click()
        self.at.run()
        self.assertFalse(self.at.exception)
        self.assertIn("weekly", _all_text(self.at).lower())
        products = _by_label(self.at.multiselect, "Products")
        products.set_value(["PUBLIC-NUBEQA"])
        _by_label(self.at.selectbox, "Period type").set_value("Annual")
        self.at.run()
        periods = _by_label(self.at.multiselect, "Reporting periods")
        periods.set_value(["2025"])
        self.at.run()
        confirm = _by_label(self.at.button, "Confirm intent")
        self.assertTrue(confirm.disabled)
        _by_label(
            self.at.checkbox,
            "Replace unsupported requirements with the selections above",
        ).set_value(True)
        self.at.run()
        self.assertFalse(
            _by_label(self.at.button, "Confirm intent").disabled
        )

    def _confirm(self):
        _by_label(self.at.multiselect, "Products").set_value(
            ["PUBLIC-NUBEQA"]
        )
        self.at.run()
        _by_label(self.at.multiselect, "Reporting periods").set_value(
            ["2025"]
        )
        self.at.run()
        _by_label(self.at.button, "Confirm intent").click()
        self.at.run()
        self.assertFalse(self.at.exception)

    def test_edited_scope_hides_approval(self):
        self._confirm()
        self.assertIsNotNone(
            _by_label(self.at.button, "Approve proposal")
        )
        _by_label(self.at.multiselect, "Products").set_value(
            ["PUBLIC-NUBEQA", "PUBLIC-EYLEA"]
        )
        self.at.run()
        self.assertFalse(self.at.exception)
        self.assertIn("stale", _all_text(self.at).lower())
        self.assertIsNone(_by_label(self.at.button, "Approve proposal"))
        self.assertIsNone(_by_label(self.at.button, "Open report preview"))

    def test_approve_render_exports(self):
        self._confirm()
        actor = _by_label(
            self.at.selectbox, "Simulated approval actor"
        )
        self.assertIsNotNone(actor)
        actor.set_value("DEMO-PUBLIC-APPROVER")
        self.at.run()
        _by_label(self.at.button, "Approve proposal").click()
        self.at.run()
        self.assertFalse(self.at.exception)
        self.assertIn("approved", _all_text(self.at).lower())
        _by_label(self.at.button, "Open report preview").click()
        self.at.run()
        self.assertFalse(self.at.exception)
        self.assertTrue(len(self.at.dataframe) >= 1)
        downloads = {b.label for b in self.at.get("download_button")}
        self.assertIn("Download report bundle (ZIP)", downloads)
        self.assertIn("Download Power BI import kit (ZIP)", downloads)
        self.assertIn("Download standalone HTML report", downloads)
        self.assertIn("Published actual", _all_text(self.at))

    def test_download_buttons_ignore_rerun(self):
        import streamlit
        original = DeltaGenerator.download_button
        module_spy = mock.patch.object(
            streamlit, "download_button",
            wraps=streamlit.download_button,
        )
        with module_spy as module_calls, mock.patch.object(
            DeltaGenerator, "download_button", autospec=True,
            side_effect=original,
        ) as spy:
            self._confirm()
            actor = _by_label(
                self.at.selectbox, "Simulated approval actor"
            )
            actor.set_value("DEMO-PUBLIC-APPROVER")
            self.at.run()
            _by_label(self.at.button, "Approve proposal").click()
            self.at.run()
            _by_label(self.at.button, "Open report preview").click()
            self.at.run()
            self.assertFalse(self.at.exception)
            self._workspace("Performance explorer")
        calls = {}
        for call in spy.call_args_list:
            calls.setdefault(call.args[1], call)
        for call in module_calls.call_args_list:
            calls.setdefault(call.args[0], call)
        expected = [
            "Download rows as CSV",
            "Download standalone HTML report",
            "Download report bundle (ZIP)",
            "Download Power BI import kit (ZIP)",
            "Download filtered rows (CSV)",
        ]
        for label in expected:
            self.assertIn(label, calls)
            self.assertEqual(
                calls[label].kwargs.get("on_click"), "ignore",
                f"{label} must pass on_click='ignore'",
            )

    def _llm_checkbox(self, at=None):
        at = at or self.at
        return _by_label(
            list(at.sidebar.checkbox) + list(at.checkbox),
            "Use LLM intent extraction (opt-in)",
        )

    def test_llm_opt_in_disabled_when_unconfigured(self):
        box = self._llm_checkbox()
        self.assertIsNotNone(box)
        self.assertFalse(box.value)
        self.assertTrue(box.disabled)
        text = _all_text(self.at)
        self.assertIn("not configured", text)
        self.assertIn("Processing mode: Offline parser", text)

    def test_llm_opt_in_enabled_default_off_when_configured(self):
        with mock.patch.dict(_CAPABILITIES, {
            "configured": True, "label": "CSC / LUMI Aitta",
            "model": "openai/gpt-oss-120b",
        }):
            at = AppTest.from_file(APP_PATH, default_timeout=30)
            at.run()
        self.assertFalse(at.exception)
        box = self._llm_checkbox(at)
        self.assertIsNotNone(box)
        self.assertFalse(box.value)
        self.assertFalse(box.disabled)
        text = _all_text(at)
        self.assertIn("CSC / LUMI Aitta", text)
        self.assertIn("openai/gpt-oss-120b", text)
        self.assertIn("Processing mode: Offline parser", text)

    def test_llm_opt_in_sends_use_llm_and_shows_live_mode(self):
        with mock.patch.dict(_CAPABILITIES, {
            "configured": True, "label": "CSC / LUMI Aitta",
            "model": "openai/gpt-oss-120b",
        }):
            at = AppTest.from_file(APP_PATH, default_timeout=30)
            at.run()
            self.assertFalse(at.exception)
            box = self._llm_checkbox(at)
            box.set_value(True)
            at.run()
            self.assertFalse(at.exception)
            text = _all_text(at)
            self.assertIn("Processing mode: Live LLM", text)
            self.assertIn("openai/gpt-oss-120b", text)
            _by_label(
                at.text_input, "Describe the report you want"
            ).set_value("global Nubeqa sales 2025")
            at.run()
            _by_label(at.button, "Send").click()
            at.run()
            self.assertFalse(at.exception)
        message_posts = [
            body for url, body in POST_BODIES
            if url.endswith("/messages")
        ]
        self.assertTrue(message_posts)
        self.assertIs(message_posts[-1].get("use_llm"), True)
        self.assertIn("Last extraction: Live LLM", _all_text(at))

    def test_offline_extraction_caption(self):
        SESSION_STATE.update({
            "session_id": "sess-1", "domain_id": "public_sales",
            "messages": [], "extraction_mode": "offline",
        })
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        self.assertFalse(at.exception)
        self.assertIn("Last extraction: Offline parser", _all_text(at))

    def test_fallback_extraction_warning_distinct(self):
        SESSION_STATE.update({
            "session_id": "sess-1", "domain_id": "public_sales",
            "messages": [],
            "extraction_mode": "offline_fallback_after_llm_unavailable",
        })
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        self.assertFalse(at.exception)
        warnings = " ".join(w.value for w in at.warning)
        self.assertIn("Offline fallback", warnings)
        self.assertIn("live LLM unavailable", warnings)
        self.assertNotIn(
            "Last extraction: Offline parser", _all_text(at)
        )

    def test_workspace_roundtrip_preserves_session(self):
        sessions_before = [
            u for u in POST_CALLS if u.endswith("/api/sessions")
        ]
        self._workspace("Performance explorer")
        self.assertTrue(len(self.at.dataframe) >= 1)
        self._workspace("Report builder")
        sessions_after = [
            u for u in POST_CALLS if u.endswith("/api/sessions")
        ]
        self.assertEqual(len(sessions_after), len(sessions_before))

    def test_wrong_identity_resume_warns(self):
        self.at.query_params["session_id"] = "foreign"
        self.at.run()
        self.assertFalse(self.at.exception)
        self.assertIn(
            "Unable to resume", _all_text(self.at)
        )

    def test_q2_starter_year_over_year_scope(self):
        starter = _by_label(
            self.at.button, "Q2 year-over-year comparison"
        )
        self.assertIsNotNone(starter)
        starter.click()
        self.at.run()
        self.assertFalse(self.at.exception)
        self.assertEqual(
            _by_label(self.at.selectbox, "Period type").value, "Quarterly"
        )
        periods = _by_label(self.at.multiselect, "Reporting periods")
        self.assertEqual(periods.value, ["2025-Q2", "2026-Q2"])
        self.assertEqual(
            _by_label(self.at.multiselect, "Products").value,
            ["PUBLIC-NUBEQA"],
        )

    def test_out_of_coverage_extras_need_ack(self):
        SESSION_STATE.update({
            "session_id": "sess-1", "domain_id": "public_sales",
            "messages": [], "unsupported": [],
            "partial_intent": {
                "product_ids": ["PUBLIC-NUBEQA", "PUBLIC-UNKNOWN"],
                "market_ids": ["DE"],
                "metric_ids": ["PUBLIC-FORECAST"],
                "months": ["2025-01-01"],
                "grain": "month",
            },
        })
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        self.assertFalse(at.exception)
        self.at = at
        text = _all_text(at)
        self.assertIn("PUBLIC-UNKNOWN", text)
        self.assertIn("DE", text)
        self.assertIn("PUBLIC-FORECAST", text)
        self.assertIn("month", text)
        self.assertIn("2025-01-01", text)
        products = _by_label(at.multiselect, "Products")
        self.assertIn("PUBLIC-UNKNOWN", products.value)
        self.assertTrue(
            _by_label(at.button, "Confirm intent").disabled
        )
        _by_label(
            at.checkbox,
            "Replace unsupported requirements with the selections above",
        ).set_value(True)
        at.run()
        confirm = _by_label(at.button, "Confirm intent")
        self.assertIsNotNone(confirm)

    def test_new_session_writes_url_and_resume(self):
        self.assertEqual(
            self.at.query_params.get("session_id"), ["sess-1"]
        )
        _by_label(self.at.button, "New request").click()
        self.at.run()
        self.assertFalse(self.at.exception)
        self.assertEqual(
            self.at.query_params.get("session_id"), ["sess-2"]
        )

    def test_saved_report_reuse_switches_workspace(self):
        ASSETS.append({
            "asset_id": "GEN-SEED", "name": "Nubeqa FY 2025",
            "owner_name": "Demo Steward", "endorsement": "promoted",
            "lifecycle_status": "active", "grain": "year",
            "coverage": {"product_ids": ["PUBLIC-NUBEQA"],
                         "market_ids": ["GLOBAL"], "months": ["2025"]},
        })
        LAST_INTENT.update({
            "product_ids": ["PUBLIC-NUBEQA"], "market_ids": ["GLOBAL"],
            "metric_ids": ["PUBLIC-REPORTED-SALES"], "months": ["2025"],
            "grain": "year",
        })
        self._workspace("Saved reports")
        reuse = _by_label(self.at.button, "Open / reuse")
        self.assertIsNotNone(reuse)
        reuse.click()
        self.at.run()
        self.assertFalse(self.at.exception)
        radio = next(
            r for r in
            list(self.at.sidebar.radio) + list(self.at.radio)
            if r.label == "Workspace"
        )
        self.assertEqual(radio.value, "Report builder")
        self.assertIn("Reuse", _all_text(self.at))
        self.assertIsNotNone(
            _by_label(self.at.button, "Open report preview")
        )

    def test_later_url_replacement_attempts_new_id(self):
        SESSION_STATE.update(_intent_state({
            "product_ids": ["PUBLIC-NUBEQA"], "market_ids": ["GLOBAL"],
            "metric_ids": ["PUBLIC-REPORTED-SALES"], "months": ["2025"],
            "grain": "year",
        }))
        self.at.query_params["session_id"] = "sess-adopted"
        self.at.run()
        self.assertFalse(self.at.exception)
        self.at.query_params["session_id"] = "foreign"
        self.at.run()
        self.assertFalse(self.at.exception)
        self.assertIn("Unable to resume", _all_text(self.at))

    def test_failed_resume_drops_old_session(self):
        SESSION_STATE.update(_intent_state({
            "product_ids": ["PUBLIC-NUBEQA"], "market_ids": ["GLOBAL"],
            "metric_ids": ["PUBLIC-REPORTED-SALES"], "months": ["2025"],
            "grain": "year",
        }))
        self.at.query_params["session_id"] = "sess-adopted"
        self.at.run()
        self.assertFalse(self.at.exception)
        self.assertIn("Propose", _all_text(self.at))
        self.at.query_params["session_id"] = "foreign"
        self.at.run()
        self.assertFalse(self.at.exception)
        self.assertIn("Unable to resume", _all_text(self.at))
        self.assertNotIn("Approve proposal", _all_text(self.at))
        url_value = self.at.query_params.get("session_id")
        self.assertNotEqual(url_value, ["sess-adopted"])
        self.assertNotEqual(url_value, ["foreign"])
        self.assertTrue(url_value and url_value[0].startswith("sess-"))


class OfflineApiTests(unittest.TestCase):
    def test_api_offline_friendly_error(self):
        def boom(*args, **kwargs):
            raise httpx.ConnectError("refused")

        with mock.patch.object(httpx, "get", side_effect=boom):
            at = AppTest.from_file(APP_PATH, default_timeout=30)
            at.run()
        self.assertFalse(at.exception)
        self.assertIn("Cannot reach the API", _all_text(at))


if __name__ == "__main__":
    unittest.main()
