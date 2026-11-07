"""Smart Librarian local demo UI.

Talks only to the FastAPI loopback service over HTTP (httpx). No direct
database access, no business calculations - report numbers come from the API,
which uses the fixed calculation engine. Simulated identities, roles and
approvals for demonstration only.
"""

import html
import json
import os

import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from smart_librarian.reporting.exports import (
        build_report_bundle,
        export_report_html,
    )
    from smart_librarian.reporting.powerbi import (
        build_powerbi_import_bundle,
        build_public_financials_bundle,
        serialize_rows_csv,
    )
    _EXPORTS_AVAILABLE = True
except Exception:
    _EXPORTS_AVAILABLE = False

API_URL = os.environ.get("SMART_LIBRARIAN_API_URL", "http://127.0.0.1:8000")

_CSS = """
<style>
html, body, [class*="css"] {
    background-color: #f4f7f9;
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
}
.stApp { background-color: #f4f7f9; }
h1, h2, h3 {
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    color: #0f3557;
}
.tagline {
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 1.05rem; font-weight: 600; color: #0e7c7b;
    margin-top: -10px; margin-bottom: 4px;
}
.status-strip {
    background: #0f3557; color: #e8f0f4; padding: 6px 14px;
    border-radius: 6px; font-size: 0.85rem; margin-bottom: 12px;
}
.step-strip {
    display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px;
    font-size: 0.8rem;
}
.step {
    background: #e6edf1; color: #5a6b7a; padding: 4px 12px;
    border-radius: 12px; border: 1px solid #d5e0e6;
}
.step.done { background: #dff0ee; color: #155f5e; border-color: #b8dcd8; }
.step.now { background: #0e7c7b; color: #eef7f6; border-color: #0e7c7b; }
.card {
    background: #ffffff; border: 1px solid #d5e0e6; border-radius: 8px;
    padding: 10px 14px; margin-bottom: 8px;
}
.card-title {
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    color: #0f3557; font-weight: bold;
}
.small-muted { color: #5a6b7a; font-size: 0.8rem; }
</style>
"""

_STEPS = ["Request", "Confirm intent", "Decision", "Approval", "Preview"]

# Guided-form prefills for the five demo paths. They fill the form only;
# nothing is approved or rendered automatically.
SCENARIOS = {
    "sales": [
        {
            "label": "Sales reuse - Nubeqa Germany Q1 Net Sales",
            "intent": {
                "product_ids": ["DEMO-P-NUB"], "market_ids": ["DE"],
                "metric_ids": ["DEMO-NET-SALES"],
                "months": ["2026-01-01", "2026-02-01", "2026-03-01"],
                "grain": "month",
            },
            "note": "Expects REUSE of the certified seed report.",
        },
        {
            "label": "Sales extension - Nubeqa Germany Q1 Net Sales + Forecast",
            "intent": {
                "product_ids": ["DEMO-P-NUB"], "market_ids": ["DE"],
                "metric_ids": ["DEMO-NET-SALES", "DEMO-FORECAST"],
                "months": ["2026-01-01", "2026-02-01", "2026-03-01"],
                "grain": "month",
            },
            "note": "Expects PROPOSE_CHANGE, approval and publish - or REUSE if this scope was already registered in a previous run.",
        },
        {
            "label": "Access denied - Germany scope as the Finland analyst",
            "intent": {
                "product_ids": ["DEMO-P-NUB"], "market_ids": ["DE"],
                "metric_ids": ["DEMO-NET-SALES"],
                "months": ["2026-01-01"],
                "grain": "month",
            },
            "note": "Requires the DEMO-USER-FI identity; expects ACCESS_DENIED.",
        },
    ],
    "logistics": [
        {
            "label": "Logistics - Cold Chain Germany Q1 (all metrics)",
            "intent": {
                "product_ids": ["DEMO-L-COLD"], "market_ids": ["DE"],
                "metric_ids": ["DEMO-DELIVERED", "DEMO-ON-TIME-PCT",
                               "DEMO-LEAD-DAYS"],
                "months": ["2026-01-01", "2026-02-01", "2026-03-01"],
                "grain": "month",
            },
            "note": "Expects PROPOSE_BUILD, approval and publish - or REUSE if this scope was already registered in a previous run.",
        },
    ],
    "quality": [
        {
            "label": "Quality - Tablet Line A Germany Q1 (all metrics)",
            "intent": {
                "product_ids": ["DEMO-Q-TAB"], "market_ids": ["DE"],
                "metric_ids": ["DEMO-INSPECTED", "DEMO-REJECTED",
                               "DEMO-REJECT-PCT", "DEMO-BATCHES"],
                "months": ["2026-01-01", "2026-02-01", "2026-03-01"],
                "grain": "month",
            },
            "note": "Expects PROPOSE_BUILD, approval and publish - or REUSE if this scope was already registered in a previous run.",
        },
    ],
    "public_sales": [
        {
            "label": "Public data - Nubeqa Global 2025 Reported Sales",
            "intent": {
                "product_ids": ["PUBLIC-NUBEQA"], "market_ids": ["GLOBAL"],
                "metric_ids": ["PUBLIC-REPORTED-SALES"],
                "months": ["2025"],
                "grain": "year",
            },
            "note": "Actual published figures; first run expects PROPOSE_BUILD and approval - or REUSE if this scope was already registered.",
        },
        {
            "label": "Public data - all four products 2024/2025 comparison",
            "intent": {
                "product_ids": ["PUBLIC-NUBEQA", "PUBLIC-KERENDIA",
                                "PUBLIC-EYLEA", "PUBLIC-XARELTO"],
                "market_ids": ["GLOBAL"],
                "metric_ids": ["PUBLIC-REPORTED-SALES"],
                "months": ["2024", "2025"],
                "grain": "year",
            },
            "note": "Actual published figures; first run expects PROPOSE_BUILD and approval - or REUSE if this scope was already registered.",
        },
    ],
}


def api_get(path, params=None):
    return httpx.get(f"{API_URL}{path}", params=params, timeout=15)


def api_post(path, payload, timeout=30):
    return httpx.post(f"{API_URL}{path}", json=payload, timeout=timeout)


def api_unavailable():
    st.error(
        f"Cannot reach the API at {API_URL}. Start it first, for example:\n\n"
        "```\n$env:PYTHONPATH = 'src'\n"
        "python -m uvicorn smart_librarian.api.app:app "
        "--host 127.0.0.1 --port 8000\n```\n"
        "or run `python run_demo.py`."
    )


def _widget_key(field):
    return (
        f"intent_{field}_{st.session_state.session_id}"
        f"_{st.session_state.form_rev}"
    )


def _reset_identity(user_id, domain_id):
    for key in ("state", "catalog", "report", "prefill", "preview_open",
                "actors"):
        st.session_state.pop(key, None)
    st.session_state.user_id = user_id
    st.session_state.domain_id = domain_id
    st.session_state.form_rev = 0
    st.session_state.report_rev = 0
    try:
        response = api_post(
            "/api/sessions",
            {"user_id": user_id, "domain_id": domain_id},
        )
    except httpx.HTTPError:
        st.session_state.session_id = None
        return
    if response.status_code != 200:
        st.session_state.session_id = None
        return
    st.session_state.session_id = response.json()["session_id"]
    if st.query_params.get("session_id") != st.session_state.session_id:
        st.query_params["session_id"] = st.session_state.session_id
    refresh_state()


def refresh_state():
    if not st.session_state.get("session_id"):
        return
    try:
        response = api_get(
            f"/api/sessions/{st.session_state.session_id}",
            {"user_id": st.session_state.user_id},
        )
    except httpx.HTTPError:
        return
    if response.status_code == 200:
        st.session_state.state = response.json()


def load_catalog(user_id, domain_id):
    try:
        response = api_get(
            "/api/catalog", {"user_id": user_id, "domain_id": domain_id}
        )
    except httpx.HTTPError:
        return None
    return response.json() if response.status_code == 200 else None


def _try_resume(resume, user_id, domains):
    """Attempt to adopt a session id from the URL under this requester.

    Returns "adopted" or "failed"; every failure path warns explicitly -
    nothing is silently ignored or claimed.
    """
    try:
        response = api_get(f"/api/sessions/{resume}", {"user_id": user_id})
    except httpx.HTTPError:
        st.session_state["resume_notice"] = (
            f"Unable to resume session {resume}: API offline."
        )
        return "failed"
    if response.status_code != 200:
        st.session_state["resume_notice"] = (
            f"Unable to resume session {resume}: session not found or "
            "belongs to a different simulated identity."
        )
        return "failed"
    adopted = response.json()
    adopted_domain = adopted.get("domain_id") or "sales"
    if adopted_domain not in domains:
        st.session_state["resume_notice"] = (
            f"Unable to resume session {resume}: unknown domain "
            f"'{adopted_domain}'."
        )
        return "failed"
    for key in ("state", "catalog", "report", "preview_open"):
        st.session_state.pop(key, None)
    st.session_state.user_id = user_id
    st.session_state.domain_id = adopted_domain
    st.session_state.session_id = resume
    st.session_state.state = adopted
    st.session_state.prefill = adopted.get("partial_intent") or {}
    st.session_state.form_rev = st.session_state.get("form_rev", 0) + 1
    st.session_state.report_rev = 0
    if adopted_domain != st.session_state.get("domain_select"):
        st.session_state.pending_domain = adopted_domain
    st.session_state.resume_adopted = True
    return "adopted"


def _progress_strip(state):
    outcome = state.get("outcome")
    approval = (state.get("proposal") or {}).get("approval_status")
    if st.session_state.get("preview_open"):
        current = 4
    elif approval in ("approved", "rejected"):
        current = 3
    elif outcome in ("REUSE", "PROPOSE_CHANGE", "PROPOSE_BUILD"):
        current = 3
    elif outcome in ("CONFIRM_INTENT", "CLARIFY", "NEEDS_REVIEW",
                     "ACCESS_DENIED"):
        current = 1
    else:
        current = 0
    if outcome == "REUSE" and approval == "not_required":
        current = max(current, 3)
    chips = []
    for index, name in enumerate(_STEPS):
        cls = "now" if index == current else ("done" if index < current else "")
        chips.append(f"<span class='step {cls}'>{index + 1}. {name}</span>")
    st.markdown(
        "<div class='step-strip'>" + "".join(chips) + "</div>",
        unsafe_allow_html=True,
    )


def _legacy_main():
    st.set_page_config(page_title="Smart Librarian (demo)", layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)
    st.title("Smart Librarian")
    st.markdown(
        "<div class='tagline'>Build less. Trust more.</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Governed report workflow over synthetic demo fixtures plus the "
        "published-actual public domain. Identities and approvals are "
        "simulated, not authentication or enterprise access control."
    )

    try:
        domains_response = api_get("/api/domains")
        capabilities_response = api_get("/api/capabilities")
    except httpx.HTTPError:
        api_unavailable()
        return
    if domains_response.status_code != 200:
        api_unavailable()
        return
    domains = {
        item["domain_id"]: item
        for item in domains_response.json()["domains"]
    }
    capabilities = (
        capabilities_response.json()
        if capabilities_response.status_code == 200
        else {"configured": False, "model": "unknown"}
    )

    # A resumed session from another domain applies its domain before the
    # selector widget is constructed this run.
    pending_domain = st.session_state.pop("pending_domain", None)
    if pending_domain in domains:
        st.session_state["domain_select"] = pending_domain

    with st.sidebar:
        workspace = st.radio(
            "Workspace",
            options=[
                "Build & reuse",
                "Challenge estate",
                "Public financials",
                "Deployment readiness",
            ],
            key="workspace_select",
        )
        if workspace == "Build & reuse":
            st.header("Demo scope")
            sticky_domain = st.session_state.get("sticky_domain_id")
            if (sticky_domain in domains
                    and "domain_select" not in st.session_state):
                st.session_state["domain_select"] = sticky_domain
            domain_id = st.selectbox(
                "Domain",
                options=list(domains),
                format_func=lambda did: domains[did]["display_name"],
                key="domain_select",
            )
            try:
                users_response = api_get("/api/demo-users", {"domain_id": domain_id})
            except httpx.HTTPError:
                api_unavailable()
                return
            if users_response.status_code != 200:
                api_unavailable()
                return
            users = users_response.json()["users"]
            user_options = {u["user_id"]: u for u in users}
            sticky_user = st.session_state.get("sticky_user_id")
            if (sticky_user in user_options
                    and "identity_select" not in st.session_state):
                st.session_state["identity_select"] = sticky_user
            user_id = st.selectbox(
                "Simulated user",
                options=list(user_options),
                format_func=lambda uid: f"{user_options[uid]['name']} ({uid})",
                key="identity_select",
            )
            st.session_state.sticky_domain_id = domain_id
            st.session_state.sticky_user_id = user_id
            st.caption(
                "Switching domain or identity starts a fresh session and clears "
                "results. Identities are simulated; this is not authentication."
            )
            if st.button("New request", key="new_request"):
                st.session_state.pop("chat_text", None)
                st.session_state.pop("resume_checked", None)
                _reset_identity(user_id, domain_id)
                st.rerun()

            provider_label = capabilities.get("label") or "provider"
            config_error = capabilities.get("error")
            if capabilities.get("configured"):
                llm_note = (
                    f"{provider_label} configured ({capabilities.get('model')})"
                )
            elif config_error:
                llm_note = f"config error - {config_error}"
            else:
                llm_note = "not configured - offline parser will be used"
            llm_selected = st.checkbox(
                "Use LLM intent extraction (opt-in)",
                value=False,
                key="use_llm",
                disabled=not capabilities.get("configured"),
                help=(
                    f"Sends your request text plus catalog metadata choices to "
                    f"the configured provider ({provider_label}). Catalog "
                    "metadata contains no source business figures, but your "
                    "request text may contain confidential information - do not "
                    "enter secrets. Checking this box is your permission for "
                    "that transmission."
                ),
            )
            # Even if a stale True lingers in widget state, never send use_llm
            # to the API unless the provider is currently configured.
            use_llm = bool(llm_selected) and bool(capabilities.get("configured"))
            st.caption(
                f"LLM provider: {llm_note}. No provider call happens unless "
                "this box is checked. Aitta may need to cold-start the model "
                "(first request can take a while); failures fall back to the "
                "offline parser."
            )
        st.caption(f"API: {API_URL}")

    if workspace != "Build & reuse":
        if workspace == "Challenge estate":
            _page_challenge_estate()
        elif workspace == "Public financials":
            _page_public_financials()
        else:
            _page_deployment_readiness()
        return

    if st.session_state.pop("resume_adopted", None):
        # Session was adopted via ?session_id= including its own domain;
        # do not create a fresh session this run.
        pass
    elif (
        st.session_state.get("user_id") != user_id
        or st.session_state.get("domain_id") != domain_id
        or not st.session_state.get("session_id")
    ):
        # Bootstrap: if the URL asks for a session and none is loaded yet,
        # try to adopt it BEFORE creating (and URL-writing) a fresh one.
        requested = st.query_params.get("session_id")
        if requested and not st.session_state.get("session_id"):
            if _try_resume(requested, user_id, domains) == "adopted":
                st.rerun()
            del st.query_params["session_id"]
        # User-selected identity/domain changes keep the fresh-session path.
        _reset_identity(user_id, domain_id)
        st.rerun()
    if not st.session_state.get("session_id"):
        api_unavailable()
        return
    notice = st.session_state.pop("resume_notice", None)
    if notice:
        st.warning(notice)

    # In-UI resume: a different ?session_id= pasted into an existing UI.
    resume = st.query_params.get("session_id")
    if resume and resume != st.session_state.get("session_id") \
            and not st.session_state.get("resume_checked"):
        st.session_state.resume_checked = True
        if _try_resume(resume, user_id, domains) == "adopted":
            st.rerun()
        del st.query_params["session_id"]

    if st.session_state.get("catalog") is None:
        st.session_state.catalog = load_catalog(user_id, domain_id)
        if st.session_state.catalog is None:
            api_unavailable()
            return
    if "state" not in st.session_state:
        refresh_state()

    catalog = st.session_state.catalog
    state = st.session_state.get("state") or {}
    model_meta = catalog["choices"]["model"]
    labels = catalog["choices"].get("dimension_labels") or {}
    product_label = labels.get("products", "Products")
    market_label = labels.get("markets", "Markets")
    mode = state.get("extraction_mode") or "offline"

    is_public_domain = domain_id == "public_sales"
    if is_public_domain:
        snapshot_text = (
            "Published actual annual data - public source snapshot as of "
            + html.escape(str(model_meta.get("snapshot_as_of", "unknown")))
            + " (frozen file, not live company systems)"
        )
    else:
        snapshot_text = (
            "Synthetic snapshot as of "
            + html.escape(str(model_meta.get("snapshot_as_of", "unknown")))
            + " (not live data)"
        )
    st.markdown(
        "<div class='status-strip'>" + snapshot_text
        + " | Domain: " + html.escape(str(domain_id))
        + " | Simulated identity: " + html.escape(user_id)
        + " | Extraction mode: " + html.escape(str(mode))
        + " | Dataset: " + html.escape(str(catalog["choices"]["dataset_id"]))
        + "</div>",
        unsafe_allow_html=True,
    )
    _progress_strip(state)

    # --- chat -------------------------------------------------------------
    st.subheader("Request")
    scenario_cols = st.columns(len(SCENARIOS.get(domain_id, [])) or 1)
    for col, scenario in zip(
        scenario_cols, SCENARIOS.get(domain_id, [])
    ):
        if col.button(
            scenario["label"], key=f"scenario_{scenario['label']}",
            help=scenario["note"],
        ):
            st.session_state.prefill = dict(scenario["intent"])
            st.session_state.form_rev += 1
            st.session_state.preview_open = False
            st.rerun()
    if SCENARIOS.get(domain_id):
        st.caption(
            "Scenario buttons only prefill the guided form - review and "
            "confirm the exact scope below; nothing is approved for you."
        )
    text = st.text_input(
        "Describe the report you want",
        placeholder=(
            "e.g. Show global reported sales for Nubeqa in 2025"
            if is_public_domain else
            "e.g. Show monthly figures for a product in a market from "
            "January through March 2026"
        ),
        key="chat_text",
    )
    if st.button("Send", key="chat_send", disabled=not text.strip()):
        try:
            with st.spinner(
                "Contacting configured provider; Aitta may need to start "
                "the model..." if use_llm else "Processing..."
            ):
                response = api_post(
                    f"/api/sessions/{st.session_state.session_id}/messages",
                    {"user_id": user_id, "text": text, "use_llm": use_llm},
                    timeout=180 if use_llm else 30,
                )
        except httpx.HTTPError:
            api_unavailable()
            return
        if response.status_code == 200:
            st.session_state.state = response.json()
            st.session_state.preview_open = False
            st.session_state.form_rev += 1
            st.session_state.prefill = (
                st.session_state.state.get("partial_intent") or {}
            )
            st.rerun()
        else:
            st.error(f"API error {response.status_code}: {response.text}")

    for message in state.get("messages") or []:
        role = "You" if message["role"] == "user" else "Librarian"
        st.markdown(f"**{role}:** {message['text']}")

    if state.get("limitations"):
        st.caption(f"Parser note: {state['limitations']}")

    # --- guided intent selectors (outside any form) ------------------------
    choices = catalog["choices"]
    product_ids = [p["product_id"] for p in choices["products"]]
    product_names = {p["product_id"]: p["product_name"] for p in choices["products"]}
    market_ids = [m["market_id"] for m in choices["markets"]]
    market_names = {m["market_id"]: m["market_name"] for m in choices["markets"]}
    metrics = choices["metrics"]
    metric_names = {m["metric_id"]: m["name"] for m in metrics}
    coverage_months = choices["months"]

    prefill = dict(state.get("partial_intent") or {})
    if st.session_state.get("prefill"):
        prefill = dict(st.session_state.prefill)

    def options_with_extras(field, base_options):
        extras = [
            value for value in prefill.get(field, [])
            if value not in base_options
        ]
        return list(base_options) + extras, set(extras)

    product_options, extra_products = options_with_extras("product_ids", product_ids)
    market_options, extra_markets = options_with_extras("market_ids", market_ids)
    metric_options, extra_metrics = options_with_extras(
        "metric_ids", list(metric_names)
    )
    month_options, extra_months = options_with_extras("months", coverage_months)

    st.subheader("Confirm intent")
    st.caption(
        "The guided form is authoritative - nothing runs until you confirm "
        "this exact scope. Periods outside coverage are never silently reduced."
    )
    unsupported_notes = list(state.get("unsupported") or [])
    draft_metrics = [
        m for m in metrics if m["approval_status"] != "approved"
    ]

    def metric_label(mid):
        metric = next((m for m in metrics if m["metric_id"] == mid), None)
        name = metric_names.get(mid, mid)
        if metric and metric["approval_status"] != "approved":
            return f"{name} ({mid}) - unsupported: {metric['approval_status']}"
        return f"{name} ({mid})"

    def month_label(month):
        return str(month) + (
            " (outside coverage)" if month in extra_months else ""
        )

    cols = st.columns(2)
    with cols[0]:
        sel_products = st.multiselect(
            product_label, product_options,
            default=[v for v in prefill.get("product_ids", []) if v in product_options],
            format_func=lambda pid: f"{product_names.get(pid, pid)} ({pid})",
            key=_widget_key("product_ids"),
        )
        sel_markets = st.multiselect(
            market_label, market_options,
            default=[v for v in prefill.get("market_ids", []) if v in market_options],
            format_func=lambda mid: f"{market_names.get(mid, mid)} ({mid})",
            key=_widget_key("market_ids"),
        )
    with cols[1]:
        sel_metrics = st.multiselect(
            "Metrics", metric_options,
            default=[v for v in prefill.get("metric_ids", []) if v in metric_options],
            format_func=metric_label,
            key=_widget_key("metric_ids"),
        )
        sel_months = st.multiselect(
            choices.get("period_label") or "Months", month_options,
            default=[v for v in prefill.get("months", []) if v in month_options],
            format_func=month_label,
            key=_widget_key("months"),
        )
    grain_options = choices["grain_options"] or ["month"]
    sel_grain = st.selectbox(
        "Grain", grain_options,
        index=grain_options.index(prefill.get("grain"))
        if prefill.get("grain") in grain_options else 0,
        key=_widget_key("grain"),
    )

    extras_selected = sorted(
        (set(sel_products) & extra_products)
        | (set(sel_markets) & extra_markets)
        | (set(sel_metrics) & extra_metrics)
        | (set(sel_months) & extra_months)
    )
    for note in unsupported_notes:
        st.warning(f"Unsupported requirement flagged by the parser: {note}")
    for value in extras_selected:
        st.warning(f"Extracted value not in catalog coverage: {value}")
    if draft_metrics and not unsupported_notes:
        st.caption(
            "Draft metrics are shown for completeness; selecting one requires "
            "review and cannot render."
        )

    needs_ack = bool(unsupported_notes or extras_selected)
    if needs_ack:
        ack = st.checkbox(
            "Replace unsupported requirements with the selections above",
            key=_widget_key("ack"),
        )
    complete = all([sel_products, sel_markets, sel_metrics, sel_months, sel_grain])
    if not complete:
        st.caption("Select at least one value in every field to enable confirmation.")
    if st.button(
        "Confirm intent", key=_widget_key("confirm"),
        disabled=not complete or (needs_ack and not ack),
    ):
        intent = {
            "product_ids": sel_products,
            "market_ids": sel_markets,
            "metric_ids": sel_metrics,
            "months": sel_months,
            "grain": sel_grain,
        }
        try:
            response = api_post(
                f"/api/sessions/{st.session_state.session_id}/intent",
                {"user_id": user_id, "intent": intent},
            )
        except httpx.HTTPError:
            api_unavailable()
            return
        if response.status_code == 200:
            st.session_state.state = response.json()
            st.session_state.preview_open = False
            st.session_state.prefill = intent
            st.rerun()
        else:
            st.error(f"API error {response.status_code}: {response.text}")

    outcome = state.get("outcome")
    if outcome in (None, "CLARIFY", "CONFIRM_INTENT"):
        if state.get("questions"):
            st.info("Open questions: " + " ".join(state["questions"]))
        _asset_library(user_id, domain_id)
        _audit_expander(user_id)
        return
    if outcome == "ACCESS_DENIED":
        st.error(
            "Access denied for this simulated identity. The requested scope "
            "includes markets outside your allowed set; no report details "
            "or values were returned."
        )
        _asset_library(user_id, domain_id)
        return
    if outcome == "NEEDS_REVIEW":
        st.warning(
            "This request needs review before it can proceed: "
            + ", ".join(state.get("review_reasons") or [])
        )
        _asset_library(user_id, domain_id)
        return

    # --- decision + evidence ------------------------------------------------
    proposal = state.get("proposal") or {}
    spec = proposal.get("spec") or {}
    # If the guided form no longer matches the confirmed spec, the old
    # proposal must not be approvable or previewable in the UI (the backend
    # rejects it too, but we do not invite a stale-scope action).
    selected_intent = {
        "product_ids": sorted(sel_products),
        "market_ids": sorted(sel_markets),
        "metric_ids": sorted(sel_metrics),
        "months": sorted(sel_months),
        "grain": sel_grain,
    }
    if spec.get("intent") and selected_intent != spec["intent"]:
        st.warning(
            "Draft changed - confirm intent again. The proposal below is "
            "stale and its approval/preview is hidden until you reconfirm."
        )
        _asset_library(user_id, domain_id)
        _audit_expander(user_id)
        return
    headings = {
        "REUSE": "Reuse an existing governed report",
        "PROPOSE_CHANGE": "Propose a change to an existing report",
        "PROPOSE_BUILD": "Propose building a new report",
    }
    st.subheader(headings.get(outcome, outcome))
    if spec.get("source_asset_id"):
        st.write(f"Source report asset: `{spec['source_asset_id']}`")
    for note in state.get("candidate_explanations") or []:
        st.caption(note)

    with st.expander(
        "Evidence (frozen public-source snapshot; simulated governance)"
        if is_public_domain else
        "Evidence (simulated catalog snapshot)",
        expanded=False,
    ):
        for item in state.get("evidence") or []:
            st.markdown(
                "<div class='card'><span class='card-title'>"
                + html.escape(str(item["evidence_id"])) + " - "
                + html.escape(str(item["kind"])) + "</span><br/>"
                + html.escape(str(item["detail"])) + "<br/>"
                + "<span class='small-muted'>"
                + html.escape(str(item["ref_path"])) + " -> "
                + html.escape(str(item["record_id"])) + " | "
                + html.escape(str(item["status"])) + "</span></div>",
                unsafe_allow_html=True,
            )

    st.markdown("**Specification** (approvals bind to this hash):")
    st.code(json.dumps(spec, indent=2), language="json")
    st.code(f"spec_hash: {proposal.get('spec_hash')}", language="text")
    st.download_button(
        "Download specification JSON",
        data=json.dumps({"approval_status": proposal.get("approval_status"),
                         "spec": spec, "spec_hash": proposal.get("spec_hash")},
                        indent=2),
        file_name="smart_librarian_spec.json",
        mime="application/json",
    )

    approval_status = proposal.get("approval_status")
    if approval_status == "pending":
        actor_id = _approval_panel(user_id)
        cols = st.columns(2)
        if cols[0].button("Approve proposal", type="primary",
                          key=_widget_key("approve")):
            decide("approve", actor_id)
            st.rerun()
        if cols[1].button("Reject proposal", key=_widget_key("reject")):
            decide("reject", actor_id)
            st.rerun()
    elif approval_status == "approved":
        st.success("Proposal approved for this session (simulated approval).")
    elif approval_status == "rejected":
        st.error("Proposal rejected. The report cannot be rendered.")
        _asset_library(user_id, domain_id)
        return
    else:
        st.info("Exact coverage already exists - no approval required.")

    # --- report preview (revalidated against the API on every render) -------
    if approval_status in ("approved", "not_required"):
        if st.button("Open report preview", key=_widget_key("preview")):
            st.session_state.preview_open = True
        if st.session_state.get("preview_open"):
            report = fetch_report(user_id)
            if report is not None:
                refreshed = load_catalog(user_id, domain_id)
                if refreshed is not None:
                    st.session_state.catalog = refreshed
                render_report(report)

    _asset_library(user_id, domain_id)
    _audit_expander(user_id)


def _approval_panel(user_id):
    """Separate simulated approver selection; not authentication."""
    if st.session_state.get("actors") is None:
        try:
            response = api_get("/api/governance-actors")
            st.session_state.actors = (
                response.json()["actors"]
                if response.status_code == 200 else []
            )
        except httpx.HTTPError:
            st.session_state.actors = []
    actors = st.session_state.actors or []
    options = {a["actor_id"]: a for a in actors}
    spec_markets = (
        ((st.session_state.get("state") or {}).get("proposal") or {})
        .get("spec") or {}
    ).get("intent", {}).get("market_ids") or []
    eligible = {
        aid: a for aid, a in options.items()
        if "approver" in (a.get("roles") or [])
        and set(spec_markets).issubset(set(a.get("allowed_market_ids") or []))
    }
    shown = eligible or options
    actor_id = st.selectbox(
        "Simulated approval actor",
        options=list(shown) or ["DEMO-APPROVER"],
        format_func=lambda aid: (
            f"{shown[aid]['name']} ({aid}) - roles: "
            f"{', '.join(shown[aid]['roles'])}"
            if aid in shown else aid
        ),
        key=_widget_key("actor"),
    )
    st.caption(
        "Approvals are recorded against this separate simulated governance "
        "actor, not your requester identity "
        f"({user_id}). This demonstrates role separation only; it is not "
        "a login or real authorization."
    )
    return actor_id


def _asset_library(user_id, domain_id):
    with st.expander("Asset library", expanded=False):
        try:
            response = api_get(
                "/api/assets", {"user_id": user_id, "domain_id": domain_id}
            )
            assets = (
                response.json().get("assets", [])
                if response.status_code == 200 else []
            )
        except httpx.HTTPError:
            assets = []
        if not assets:
            st.caption("No assets available for this identity in this domain.")
        for asset in assets:
            st.markdown(
                f"**{asset.get('name')}** `{asset.get('asset_id')}`  \n"
                f"<span class='small-muted'>owner: "
                f"{html.escape(str(asset.get('owner_name') or asset.get('owner_id')))}"
                f" | {asset.get('endorsement')} | "
                f"{asset.get('lifecycle_status')} | "
                f"{asset.get('origin', 'seed')}</span>",
                unsafe_allow_html=True,
            )
            if st.button(
                "Open / reuse", key=f"reuse_{domain_id}_{asset.get('asset_id')}"
            ):
                try:
                    reuse_response = api_post(
                        f"/api/assets/{asset.get('asset_id')}/reuse",
                        {"user_id": user_id, "domain_id": domain_id},
                    )
                except httpx.HTTPError:
                    reuse_response = None
                if reuse_response and reuse_response.status_code == 200:
                    payload = reuse_response.json()
                    for key in ("state", "report", "prefill"):
                        st.session_state.pop(key, None)
                    st.session_state.session_id = payload["session_id"]
                    st.query_params["session_id"] = payload["session_id"]
                    st.session_state.state = payload["state"]
                    st.session_state.prefill = (
                        payload["state"].get("partial_intent") or {}
                    )
                    st.session_state.form_rev += 1
                    st.session_state.preview_open = False
                    st.rerun()
                else:
                    detail = (
                        reuse_response.text if reuse_response is not None
                        else "API offline"
                    )
                    st.error(f"Reuse failed: {detail}")


def _audit_expander(user_id):
    with st.expander("Session audit trail", expanded=False):
        try:
            response = api_get(
                f"/api/sessions/{st.session_state.session_id}/audit",
                {"user_id": user_id},
            )
            if response.status_code == 200:
                for event in response.json()["events"]:
                    st.text(
                        f"{event['created_at']}  {event['event_type']}  "
                        f"{event.get('user_id', '')}  "
                        f"{json.dumps(event['detail'])}"
                    )
            else:
                st.caption("Audit unavailable.")
        except httpx.HTTPError:
            st.caption("Audit unavailable (API offline).")


def fetch_report(user_id):
    """Always re-validate with the backend; never trust a cached render."""
    try:
        response = api_get(
            f"/api/sessions/{st.session_state.session_id}/report",
            {"user_id": user_id},
        )
    except httpx.HTTPError:
        api_unavailable()
        return None
    if response.status_code != 200:
        st.session_state.preview_open = False
        st.error(
            f"Report unavailable ({response.status_code}): "
            f"{response.json().get('detail', response.text)}"
        )
        return None
    return response.json()


def decide(decision, actor_id):
    proposal = st.session_state.state["proposal"]
    try:
        response = api_post(
            f"/api/sessions/{st.session_state.session_id}/approval",
            {
                "user_id": st.session_state.user_id,
                "proposal_id": proposal["proposal_id"],
                "spec_hash": proposal["spec_hash"],
                "decision": decision,
                "actor_user_id": actor_id,
            },
        )
    except httpx.HTTPError:
        api_unavailable()
        return
    if response.status_code == 200:
        st.session_state.state = response.json()
        st.session_state.report_rev += 1
    else:
        st.error(f"Decision rejected ({response.status_code}): "
                 f"{response.json().get('detail', response.text)}")


def render_report(report):
    is_public = (
        report.get("data_classification") == "public_reported_actual"
        or report.get("synthetic_record") is False
    )
    st.subheader("Report preview")
    if is_public:
        st.caption(
            "Published actual annual sales from public company disclosure; "
            "approval, owner and registry metadata are simulated - not "
            "Bayer certification or internal data. Local preview only."
        )
        source = report.get("source_provenance") or {}
        st.caption(
            "Source: " + str(source.get("source_title") or "public source")
            + " | " + str(source.get("source_url") or "")
            + " | sha256: " + str(source.get("source_sha256") or "")[:16]
            + "..."
        )
    else:
        st.caption(
            "Local preview only - generated assets live in the local registry; "
            "no BI file or published URL exists. Values are synthetic."
        )
    asset = report.get("asset") or {}
    if report.get("registered_asset_id"):
        owner = asset.get("owner_name") or asset.get("owner_id") or "unknown"
        st.caption(
            f"Published asset: `{report['registered_asset_id']}` "
            f"(owner: {owner}, endorsement: {asset.get('endorsement', 'n/a')})"
        )
    totals = report["totals"]
    units = report["units"]
    metric_names = {
        item["metric_id"]: item.get("name") or item["metric_id"]
        for item in (report.get("spec") or {}).get("requested_metrics") or []
    }
    if totals:
        cols = st.columns(len(totals))
        for col, (metric, value) in zip(cols, totals.items()):
            label = metric_names.get(metric, metric)
            unit = units.get(metric)
            if value is None:
                display = "N/A"
            elif unit == "percent":
                display = f"{value:.2f}%"
            elif unit == "EUR":
                display = f"{value:,} EUR"
            else:
                display = f"{value:,} {unit or ''}".strip()
            col.metric(label, display)
    else:
        st.caption(
            "No combined total is shown: a total is defined only for a "
            "single fiscal year and is never summed across years."
        )

    frame = pd.DataFrame(report["rows"])
    time_column = report.get("time_column") or "month"

    def traces(metrics_list):
        """One trace per product x market x metric, periods on the x-axis."""
        for metric in metrics_list:
            for (product, market), group in frame.groupby(
                ["product_name", "market_name"], sort=True
            ):
                group = group.sort_values(time_column)
                yield go.Scatter(
                    x=group[time_column], y=group[metric],
                    mode="lines+markers",
                    name=f"{metric_names.get(metric, metric)} | "
                         f"{product} | {market}",
                )

    # One chart panel per unit so counts are never plotted as currency.
    by_unit: dict[str, list[str]] = {}
    for metric, unit in units.items():
        by_unit.setdefault(unit or "value", []).append(metric)
    for unit, metrics_list in by_unit.items():
        figure = go.Figure(list(traces(metrics_list)))
        figure.update_layout(
            title=f"{unit} metrics", yaxis_title=unit,
            template="simple_white", font_family="Georgia",
        )
        st.plotly_chart(figure, use_container_width=True)

    st.dataframe(frame, use_container_width=True)
    st.caption(report.get("aggregation_note", ""))
    st.download_button(
        "Download rows as CSV",
        data=frame.to_csv(index=False),
        file_name="smart_librarian_report.csv",
        mime="text/csv",
    )
    if _EXPORTS_AVAILABLE:
        st.download_button(
            "Download standalone HTML report",
            data=export_report_html(report),
            file_name="smart_librarian_report.html",
            mime="text/html",
        )
        st.download_button(
            "Download report bundle (ZIP)",
            data=build_report_bundle(report),
            file_name="smart_librarian_report.zip",
            mime="application/zip",
        )
        st.download_button(
            "Download Power BI import kit (ZIP)",
            data=build_powerbi_import_bundle(report),
            file_name="smart_librarian_powerbi_kit.zip",
            mime="application/zip",
            help=(
                "Frozen report values plus typed Power Query scripts and a "
                "theme for manual import. Not a PBIP/PBIX file; no service "
                "publishing."
            ),
        )
    else:
        st.caption(
            "HTML/ZIP export unavailable - the export helper is not "
            "importable in this environment."
        )


def _fetch_evidence(kind):
    try:
        response = api_get(f"/api/evidence/{kind}")
    except httpx.HTTPError:
        api_unavailable()
        return None
    if response.status_code != 200:
        st.error(
            f"Evidence unavailable ({response.status_code}): "
            f"{response.json().get('detail', response.text)}"
        )
        return None
    return response.json()


def _rows_by(tables, name, column, value):
    return [
        row for row in (tables.get(name) or [])
        if value is not None and row.get(column) == value
    ]


def _provenance_strip(payload, source_label):
    st.markdown(
        "<div class='status-strip'>"
        + html.escape(source_label) + " | retrieved (UTC): "
        + html.escape(str(payload.get("retrieved_at_utc", "unknown")))
        + " | classification: "
        + html.escape(str(payload.get("data_classification", "unknown")))
        + "</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "This is public or synthetic challenge evidence - not secured "
        "company systems. No user data is exposed."
    )
    with st.expander("Data provenance and scope", expanded=False):
        st.markdown(payload.get("disclaimer") or "")
        st.caption(
            "source_sha256: " + str(payload.get("source_sha256", ""))
        )


def _page_challenge_estate():
    st.header("Challenge estate")
    st.caption(
        "Read-only browser over the official SinceAI builder-pack estate. "
        "The Smart Librarian workflow uses separate demo fixtures and does "
        "not evaluate this workbook estate."
    )
    payload = _fetch_evidence("challenge")
    if payload is None:
        return
    _provenance_strip(payload, f"Source file: {payload.get('source_file')}")
    tables = payload.get("tables") or {}
    assets = tables.get("Analytics_Assets") or []

    search = st.text_input(
        "Search assets by name or ID", key="estate_search",
        placeholder="Literal substring match",
    )
    platforms = sorted({a.get("platform") for a in assets if a.get("platform")})
    platform = st.selectbox(
        "Platform", ["All"] + platforms, key="estate_platform"
    )
    needle = search.strip().lower()
    filtered = [
        a for a in assets
        if (platform == "All" or a.get("platform") == platform)
        and (not needle
             or needle in str(a.get("asset_name", "")).lower()
             or needle in str(a.get("asset_id", "")).lower())
    ]
    st.caption(
        f"{len(filtered)} of {len(assets)} analytics assets shown. "
        "_source_row links each record back to the source workbook row."
    )
    st.dataframe(pd.DataFrame(filtered), use_container_width=True,
                 hide_index=True)

    options = {a["asset_id"]: a for a in filtered if a.get("asset_id")}
    if not options:
        st.warning("No assets match the current search/filter.")
        return
    asset_id = st.selectbox(
        "Select asset by ID",
        options=list(options),
        format_func=lambda aid: f"{options[aid].get('asset_name')} ({aid})",
        key="estate_asset",
    )
    asset = options[asset_id]
    model_id = asset.get("model_id")
    owner_id = asset.get("owner_id")

    st.subheader("Selected record (unmodified)")
    st.caption(
        f"Source workbook row {asset.get('_source_row')} of "
        "Analytics_Assets."
    )
    st.json(asset)

    models = tables.get("Semantic_Models") or []
    owners = tables.get("Owners") or []
    model = next((m for m in models if m.get("model_id") == model_id), None)
    owner = next((o for o in owners if o.get("owner_id") == owner_id), None)
    cols = st.columns(2)
    with cols[0]:
        st.markdown("**Linked semantic model**")
        if model:
            st.caption(f"Source row {model.get('_source_row')}")
            st.json(model)
        else:
            st.caption("No matching Semantic_Models record.")
    with cols[1]:
        st.markdown("**Linked owner**")
        if owner:
            st.caption(f"Source row {owner.get('_source_row')}")
            st.json(owner)
        else:
            st.caption("No matching Owners record.")

    st.subheader("KPI mappings")
    kpi_rows = _rows_by(tables, "Asset_KPI_Map", "asset_id", asset_id)
    catalog = {k.get("kpi_id"): k for k in (tables.get("KPI_Catalog") or [])}
    resolved = []
    for row in kpi_rows:
        kpi = catalog.get(row.get("kpi_id"))
        resolved.append({
            **row,
            "kpi_name": kpi.get("kpi_name") if kpi else None,
            "kpi_unit": kpi.get("unit") if kpi else None,
            "kpi_definition_status":
                kpi.get("definition_status") if kpi else None,
            "kpi_source_row": kpi.get("_source_row") if kpi else None,
        })
    st.caption(
        f"{len(resolved)} Asset_KPI_Map rows resolved against KPI_Catalog "
        "by kpi_id."
    )
    st.dataframe(pd.DataFrame(resolved), use_container_width=True,
                 hide_index=True)

    st.subheader("Usage")
    usage = _rows_by(tables, "Asset_Usage", "asset_id", asset_id)
    st.caption(
        f"{len(usage)} monthly rows shown as recorded. Monthly unique "
        "users are reported per row and are never summed."
    )
    st.dataframe(pd.DataFrame(usage), use_container_width=True,
                 hide_index=True)

    st.subheader("Governance signals")
    signals = _rows_by(tables, "Governance_Signals", "asset_id", asset_id)
    st.dataframe(pd.DataFrame(signals), use_container_width=True,
                 hide_index=True)
    st.caption(
        "The absence of a governance signal is not a certification of "
        "quality; signals are recorded observations only."
    )

    st.subheader("Lineage (direct edges)")
    anchor_ids = {asset_id}
    if model_id:
        anchor_ids.add(model_id)
    edges = [
        e for e in (tables.get("Lineage_Edges") or [])
        if e.get("source_id") in anchor_ids or e.get("target_id") in anchor_ids
    ]
    st.caption(
        "Direct edges where the selected asset or its semantic model is "
        "source or target; no transitive closure is computed."
    )
    st.dataframe(pd.DataFrame(edges), use_container_width=True,
                 hide_index=True)

    st.subheader("Migration backlog")
    backlog = _rows_by(tables, "Migration_Backlog", "source_asset_id",
                       asset_id)
    st.dataframe(pd.DataFrame(backlog), use_container_width=True,
                 hide_index=True)
    st.caption(
        "Migration backlog entries are supplied scenario inputs from the "
        "challenge pack, not executed actions or validated recommendations."
    )

    st.subheader("Data quality findings")
    record_ids = {v for v in (asset_id, model_id, owner_id) if v}
    issues = [
        r for r in (tables.get("Data_Quality") or [])
        if r.get("record_id") in record_ids
    ]
    st.caption(
        "Findings whose record_id matches the selected asset, its model "
        "or its owner."
    )
    st.dataframe(pd.DataFrame(issues), use_container_width=True,
                 hide_index=True)

    with st.expander("Governance rules (reference)", expanded=False):
        st.dataframe(pd.DataFrame(tables.get("Governance_Rules") or []),
                     use_container_width=True, hide_index=True)


def _page_public_financials():
    st.header("Public financials")
    st.caption(
        "Actual public annual sales for selected products - global "
        "reported figures in EUR million, from published company "
        "disclosure."
    )
    payload = _fetch_evidence("public")
    if payload is None:
        return
    _provenance_strip(payload, "Public source")
    source_url = payload.get("source_url")
    if source_url:
        st.markdown(
            f"Source: [{html.escape(str(payload.get('source_title') or source_url))}]"
            f"({source_url})"
        )
    st.caption(
        f"Unit: {payload.get('unit')} | Grain: {payload.get('grain')} | "
        f"Local snapshot: {payload.get('source_snapshot')} | The original "
        "source spreadsheet (bayer_public_product_sales_2025.xlsx) is "
        "retained under data/evidence for the Power BI import path."
    )

    rows = payload.get("rows") or []
    frame = pd.DataFrame(rows)
    if not frame.empty:
        chart = go.Figure()
        for year in sorted(frame["year"].unique()):
            part = frame[frame["year"] == year]
            chart.add_trace(go.Bar(
                x=part["product_name"], y=part["sales_eur_million"],
                name=str(year),
            ))
        chart.update_layout(
            barmode="group",
            title=(
                "Actual public annual product sales - global, "
                f"{payload.get('unit', 'EUR million')}"
            ),
            yaxis_title=str(payload.get("unit", "EUR million")),
            template="simple_white",
        )
        st.plotly_chart(chart, use_container_width=True)

    st.dataframe(frame, use_container_width=True, hide_index=True)
    if _EXPORTS_AVAILABLE:
        st.download_button(
            "Download rows as CSV",
            data=serialize_rows_csv(
                rows,
                ["product_name", "year", "sales_eur_million",
                 "source_table", "source_row_label"],
            ),
            file_name="public_financials.csv",
            mime="text/csv",
        )
    else:
        st.download_button(
            "Download rows as CSV",
            data=frame.to_csv(index=False),
            file_name="public_financials.csv",
            mime="text/csv",
        )
    st.download_button(
        "Download rows as JSON",
        data=json.dumps(rows, indent=2),
        file_name="public_financials_rows.json",
        mime="application/json",
    )
    if _EXPORTS_AVAILABLE:
        st.download_button(
            "Download Power BI public-data kit (ZIP)",
            data=build_public_financials_bundle(payload),
            file_name="public_financials_powerbi_kit.zip",
            mime="application/zip",
            help=(
                "CSV, typed Power Query script, theme and provenance for "
                "manual import. Not a PBIP/PBIX file."
            ),
        )
    st.warning(
        "Scope limits: these figures are global annual reported sales for "
        "four selected products only. This view cannot answer monthly, "
        "country-level or forecast questions. The governed 'Bayer public "
        "sales (real data)' workflow domain uses this same actual dataset; "
        "the legacy synthetic demo fixtures remain separate and are never "
        "combined with it."
    )


def _page_deployment_readiness():
    st.header("Deployment readiness")
    st.caption(
        "Honest status: this is a local demonstration, not production-"
        "ready software. Nothing below is a commitment to deploy."
    )

    st.subheader("Implemented (works locally today)")
    st.markdown(
        "- Governed request workflow: intent confirmation, spec-hash-bound "
        "approvals, REUSE / PROPOSE_CHANGE / PROPOSE_BUILD outcomes\n"
        "- Fixed calculation engines over the synthetic demo fixtures plus "
        "a fixed annual adapter serving the frozen public-source file; no "
        "arbitrary SQL or formulas\n"
        "- Session audit trail and local asset registry\n"
        "- Report preview with HTML / CSV / ZIP and Power BI import-kit "
        "exports\n"
        "- Read-only evidence API for the challenge estate and public "
        "financials\n"
        "- Opt-in LLM intent extraction with an offline-parser fallback"
    )
    st.subheader("Simulated (demo-only, not real)")
    st.markdown(
        "- Identities, roles and approvals (no authentication)\n"
        "- Endorsement and certification labels on generated assets\n"
        "- 'Published' assets - they are local registry records, not BI "
        "workspace artifacts\n"
        "- Migration backlog paths - supplied scenario inputs, not "
        "executed actions"
    )
    st.subheader("Unbuilt (would require production work)")
    st.markdown(
        "- Entra ID (Microsoft Entra) authentication and group-based "
        "authorization\n"
        "- Publishing into a real Power BI workspace; PBIP/PBIX artifact "
        "generation\n"
        "- Microsoft Fabric integration (OneLake, semantic models, "
        "pipelines)\n"
        "- Connections to real data platforms, monitoring, row-level "
        "security, secret management\n"
        "- TLS / network hardening - this demo is loopback HTTP only"
    )

    st.subheader("Target architecture")
    st.markdown(
        "Entra ID sign-in -> governed API service -> governed semantic "
        "layer -> Power BI workspace / Fabric capacity. Each hop needs the "
        "unbuilt items above before it can be claimed."
    )

    st.subheader("Responsibilities")
    st.dataframe(
        pd.DataFrame([
            {"role": "Asset owner",
             "responsibility": "Owns the report's business content and "
                               "lifecycle; requests changes; accountable "
                               "for what the asset claims."},
            {"role": "Business steward",
             "responsibility": "Maintains KPI definitions, market/product "
                               "scope metadata and endorsement decisions; "
                               "approves spec changes."},
            {"role": "Platform admin",
             "responsibility": "Operates the service, identities and "
                               "workspaces; enforces access control, "
                               "secrets and release gates."},
        ]),
        use_container_width=True, hide_index=True,
    )
    st.subheader("Human release checkpoint")
    st.warning(
        "No simulated approval in this demo authorizes a real release. "
        "Production use requires a named human checkpoint: platform admin "
        "verifies identity/security, business steward certifies KPI "
        "definitions, and the asset owner signs off on content - before "
        "anything reaches a Power BI workspace."
    )


def main():
    try:
        domains_response = api_get("/api/domains")
    except httpx.HTTPError:
        api_unavailable()
        return
    if domains_response.status_code == 200 and domains_response.json().get(
        "challenge_mode"
    ):
        from smart_librarian.ui.challenge import main as _challenge_main
        _challenge_main()
        return
    if domains_response.status_code == 200 and domains_response.json().get(
        "real_data_only"
    ):
        from smart_librarian.ui.demo import main as _real_demo_main
        _real_demo_main()
        return
    _legacy_main()


if __name__ == "__main__":
    main()
else:
    main()
