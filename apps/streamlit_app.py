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
    _EXPORTS_AVAILABLE = True
except Exception:
    _EXPORTS_AVAILABLE = False

API_URL = os.environ.get("SMART_LIBRARIAN_API_URL", "http://127.0.0.1:8000")

_CSS = """
<style>
html, body, [class*="css"] { background-color: #faf6ef; }
.stApp { background-color: #faf6ef; }
h1, h2, h3 { font-family: Georgia, 'Times New Roman', serif; color: #16494a; }
.status-strip {
    background: #16494a; color: #f3ead9; padding: 6px 14px;
    border-radius: 6px; font-size: 0.85rem; margin-bottom: 12px;
}
.step-strip {
    display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px;
    font-size: 0.8rem;
}
.step {
    background: #efe6d3; color: #7a6f5c; padding: 4px 12px;
    border-radius: 12px; border: 1px solid #e4d9c3;
}
.step.done { background: #dfe8dd; color: #3d5a40; border-color: #b9cdb9; }
.step.now { background: #16494a; color: #f3ead9; border-color: #16494a; }
.card {
    background: #ffffff; border: 1px solid #e4d9c3; border-radius: 8px;
    padding: 10px 14px; margin-bottom: 8px;
}
.card-title { font-family: Georgia, serif; color: #16494a; font-weight: bold; }
.small-muted { color: #7a6f5c; font-size: 0.8rem; }
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


def main():
    st.set_page_config(page_title="Smart Librarian (demo)", layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)
    st.title("Smart Librarian")
    st.caption(
        "Governed analytics over synthetic fixtures. Simulated identities, "
        "roles and approvals - demonstration only, not real Bayer data, "
        "authentication or access control."
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
        st.header("Demo scope")
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
        user_id = st.selectbox(
            "Simulated user",
            options=list(user_options),
            format_func=lambda uid: f"{user_options[uid]['name']} ({uid})",
            key="identity_select",
        )
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

    st.markdown(
        "<div class='status-strip'>Synthetic snapshot as of "
        + html.escape(str(model_meta.get("snapshot_as_of", "unknown")))
        + " (not live data) | Domain: " + html.escape(str(domain_id))
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
        return month + (" (outside coverage)" if month in extra_months else "")

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
            "Months", month_options,
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

    with st.expander("Evidence (simulated catalog snapshot)", expanded=False):
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
    actor_id = st.selectbox(
        "Simulated approval actor",
        options=list(options) or ["DEMO-APPROVER"],
        format_func=lambda aid: (
            f"{options[aid]['name']} ({aid}) - roles: "
            f"{', '.join(options[aid]['roles'])}"
            if aid in options else aid
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
    st.subheader("Report preview")
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

    frame = pd.DataFrame(report["rows"])

    def traces(metrics_list):
        """One trace per product x market x metric, months on the x-axis."""
        for metric in metrics_list:
            for (product, market), group in frame.groupby(
                ["product_name", "market_name"], sort=True
            ):
                group = group.sort_values("month")
                yield go.Scatter(
                    x=group["month"], y=group[metric], mode="lines+markers",
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
    else:
        st.caption(
            "HTML/ZIP export unavailable - the export helper is not "
            "importable in this environment."
        )


if __name__ == "__main__":
    main()
else:
    main()
