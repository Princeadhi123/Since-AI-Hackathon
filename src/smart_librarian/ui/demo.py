"""Real-data-only demo UI (Streamlit), driven by the governed HTTP API only.

This module renders the published-actuals workflow: no business arithmetic,
no database access, no metric definitions. Every number shown comes verbatim
from API responses; approvals bind to the backend spec hash and are recorded
against a separate simulated governance actor.
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
        serialize_rows_csv,
    )
    _EXPORTS_AVAILABLE = True
except Exception:
    _EXPORTS_AVAILABLE = False

API_URL = os.environ.get("SMART_LIBRARIAN_API_URL", "http://127.0.0.1:8000")

_CSS = """
<style>
html, body, [class*="css"] {
    background-color: #f5f8fa;
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
}
.stApp { background-color: #f5f8fa; }
h1, h2, h3 {
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    color: #0f3557;
}
.block-container { padding-top: 2.5rem; }
.tagline {
    font-size: 1.05rem; font-weight: 600; color: #0e7c7b;
    margin-top: -10px; margin-bottom: 4px;
}
.badge {
    display: inline-block; background: #0e7c7b; color: #eef7f6;
    padding: 3px 12px; border-radius: 12px; font-size: 0.78rem;
    margin-bottom: 10px;
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
.card-title { color: #0f3557; font-weight: bold; }
.small-muted { color: #5a6b7a; font-size: 0.8rem; }
</style>
"""

_STEPS = ["Request", "Confirm intent", "Decision", "Preview"]

_PERIOD_TYPES = [
    ("Annual", "year"),
    ("Quarterly", "quarter"),
    ("Half-year", "half_year"),
]
_PERIOD_TYPE_LABELS = {kind: label for label, kind in _PERIOD_TYPES}
_PERIOD_TYPE_KINDS = {label: kind for label, kind in _PERIOD_TYPES}

_STARTERS = [
    ("Nubeqa annual performance", "nubeqa", "year", None),
    ("Compare all products", None, "year", None),
    ("Q2 year-over-year comparison", "nubeqa", "quarter",
     ["2025-Q2", "2026-Q2"]),
]


def api_get(path, params=None):
    return httpx.get(f"{API_URL}{path}", params=params, timeout=15)


def api_post(path, payload, timeout=30):
    return httpx.post(f"{API_URL}{path}", json=payload, timeout=timeout)


def _api_problem():
    st.error(
        f"Cannot reach the API at {API_URL}. Check that the service is "
        "running, then press New request or reload this page to retry."
    )


def _detail(response):
    try:
        return response.json().get("detail", response.text)
    except Exception:
        return response.text


def _new_session(user_id):
    try:
        response = api_post(
            "/api/sessions", {"user_id": user_id, "domain_id": "public_sales"}
        )
    except httpx.HTTPError:
        _api_problem()
        return False
    if response.status_code != 200:
        st.error(f"Could not start a session: {_detail(response)}")
        return False
    for key in ("state", "catalog", "prefill", "preview_open", "actors"):
        st.session_state.pop(key, None)
    st.session_state.user_id = user_id
    st.session_state.session_id = response.json()["session_id"]
    st.session_state.form_rev += 1
    st.query_params["session_id"] = st.session_state.session_id
    st.session_state.resume_attempted = st.session_state.session_id
    _refresh_state(user_id)
    return True


def _refresh_state(user_id):
    try:
        response = api_get(
            f"/api/sessions/{st.session_state.session_id}",
            {"user_id": user_id},
        )
    except httpx.HTTPError:
        return
    if response.status_code == 200:
        st.session_state.state = response.json()


def _load_catalog(user_id):
    try:
        response = api_get("/api/catalog", {"user_id": user_id})
    except httpx.HTTPError:
        return None
    return response.json() if response.status_code == 200 else None


def _widget_key(field):
    return (
        f"fin_{field}_{st.session_state.session_id}"
        f"_{st.session_state.form_rev}"
    )


def _try_resume(session_id, user_id):
    try:
        response = api_get(f"/api/sessions/{session_id}", {"user_id": user_id})
    except httpx.HTTPError:
        st.warning("Unable to resume the requested session: API offline.")
        return
    if response.status_code != 200:
        for key in ("session_id", "state", "prefill", "preview_open",
                    "actors"):
            st.session_state.pop(key, None)
        st.session_state.resume_notice = (
            "Unable to resume that session: it does not exist or belongs "
            "to a different simulated identity. A fresh session was started "
            "instead."
        )
        if st.query_params.get("session_id"):
            del st.query_params["session_id"]
        return
    adopted = response.json()
    for key in ("prefill", "preview_open", "actors"):
        st.session_state.pop(key, None)
    st.session_state.session_id = session_id
    st.session_state.state = adopted
    st.session_state.prefill = adopted.get("partial_intent") or {}
    st.session_state.form_rev += 1


def _progress(state):
    outcome = state.get("outcome")
    approval = (state.get("proposal") or {}).get("approval_status")
    if st.session_state.get("preview_open"):
        current = 3
    elif approval in ("approved", "rejected") or outcome in (
        "REUSE", "PROPOSE_CHANGE", "PROPOSE_BUILD"
    ):
        current = 2
    elif outcome:
        current = 1
    else:
        current = 0
    chips = []
    for index, name in enumerate(_STEPS):
        cls = "now" if index == current else ("done" if index < current else "")
        chips.append(f"<span class='step {cls}'>{index + 1}. {name}</span>")
    st.markdown(
        "<div class='step-strip'>" + "".join(chips) + "</div>",
        unsafe_allow_html=True,
    )


def _starter_intent(choices, product_fragment, period_kind, exact_periods):
    products = choices.get("products") or []
    if product_fragment:
        selected = [
            p["product_id"] for p in products
            if product_fragment in (p["product_id"] + p["product_name"]).lower()
        ]
    else:
        selected = [p["product_id"] for p in products]
    available = {
        p["period_id"] for p in (choices.get("periods") or [])
        if p.get("period_kind") == period_kind
    }
    if exact_periods:
        period_ids = [p for p in exact_periods if p in available]
    else:
        period_ids = [
            p["period_id"] for p in (choices.get("periods") or [])
            if p.get("period_kind") == period_kind
        ]
    return {
        "product_ids": selected,
        "periods": period_ids,
        "period_kind": period_kind,
    }


def _decide(decision_value, actor_id, user_id):
    proposal = st.session_state.state["proposal"]
    try:
        response = api_post(
            f"/api/sessions/{st.session_state.session_id}/approval",
            {
                "user_id": user_id,
                "proposal_id": proposal["proposal_id"],
                "spec_hash": proposal["spec_hash"],
                "decision": decision_value,
                "actor_user_id": actor_id,
            },
        )
    except httpx.HTTPError:
        _api_problem()
        return
    if response.status_code == 200:
        st.session_state.state = response.json()
    else:
        st.error(f"Decision rejected ({response.status_code}): {_detail(response)}")


def _approval_actor(spec_markets):
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
    eligible = {
        aid: a for aid, a in options.items()
        if "approver" in (a.get("roles") or [])
        and set(spec_markets).issubset(set(a.get("allowed_market_ids") or []))
    }
    shown = eligible or options
    actor_id = st.selectbox(
        "Simulated approval actor",
        options=list(shown) or ["DEMO-PUBLIC-APPROVER"],
        format_func=lambda aid: (
            f"{shown[aid]['name']} ({aid}) - roles: "
            f"{', '.join(shown[aid]['roles'])}"
            if aid in shown else aid
        ),
        key=_widget_key("actor"),
    )
    st.caption(
        "Approvals are recorded against this separate simulated governance "
        "actor. It demonstrates role separation only - it is not a login or "
        "real authorization."
    )
    return actor_id


def _render_report(report, user_id):
    st.subheader("Report preview")
    st.caption(
        "Published actual sales from public company disclosure; approval, "
        "owner and registry metadata are simulated - not certification or "
        "internal data. Local preview only."
    )
    source = report.get("source_provenance") or {}
    if source.get("sources"):
        st.caption(
            "Sources: " + " | ".join(
                str(item.get("source_title") or item.get("source_id"))
                for item in source["sources"]
            )
        )
    asset = report.get("asset") or {}
    if report.get("registered_asset_id"):
        owner = asset.get("owner_name") or asset.get("owner_id") or "unknown"
        st.caption(
            f"Registered asset: `{report['registered_asset_id']}` "
            f"(owner: {owner}, endorsement: "
            f"{asset.get('endorsement', 'n/a')}) - local registry record, "
            "not a published BI artifact."
        )
    totals = report.get("totals") or {}
    units = report.get("units") or {}
    metric_names = {
        item["metric_id"]: item.get("name") or item["metric_id"]
        for item in (report.get("spec") or {}).get("requested_metrics") or []
    }
    if totals:
        cols = st.columns(len(totals))
        for col, (metric, value) in zip(cols, totals.items()):
            unit = units.get(metric)
            display = "N/A" if value is None else f"{value:,} {unit or ''}".strip()
            col.metric(metric_names.get(metric, metric), display)
    else:
        st.caption(
            "No combined total is shown: a total is defined only for a "
            "single selected reporting period and is never summed across "
            "periods."
        )
    frame = pd.DataFrame(report.get("rows") or [])
    time_column = report.get("time_column") or "period"
    if not frame.empty:
        metric_ids = [
            m["metric_id"]
            for m in (report.get("spec") or {}).get("requested_metrics") or []
        ] or [m for m in units]
        figure = go.Figure()
        for metric in metric_ids:
            for product, group in frame.groupby("product_name", sort=True):
                group = group.sort_values(time_column)
                figure.add_trace(go.Bar(
                    x=group[time_column], y=group[metric],
                    name=f"{product}",
                ))
        figure.update_layout(
            barmode="group",
            xaxis_title=report.get("time_label") or "Reporting period",
            yaxis_title=", ".join(sorted(set(units.values()) or {"value"})),
            template="simple_white", font_family="Segoe UI",
        )
        st.plotly_chart(figure, use_container_width=True)
        display = frame.rename(columns={
            "product_name": "Product",
            time_column: report.get("time_label") or "Reporting period",
        })
        keep = ["Product", report.get("time_label") or "Reporting period"]
        keep += [
            col for col in display.columns
            if col in (units or {}) or col in metric_names
        ]
        rename_metrics = {
            col: f"{metric_names.get(col, col)} ({units.get(col, '')})".strip()
            for col in keep if col in units
        }
        st.dataframe(
            display[keep].rename(columns=rename_metrics),
            use_container_width=True, hide_index=True,
        )
        source_cols = [
            c for c in frame.columns
            if c.startswith("source_") or c.endswith("_id")
        ]
        with st.expander("Source rows", expanded=False):
            st.dataframe(frame[source_cols] if source_cols else frame,
                         use_container_width=True, hide_index=True)
    st.caption(report.get("aggregation_note", ""))
    download_cols = st.columns(2)
    csv_data = frame.to_csv(index=False)
    if _EXPORTS_AVAILABLE and not frame.empty:
        csv_data = serialize_rows_csv(
            frame.to_dict(orient="records"), list(frame.columns)
        )
    download_cols[0].download_button(
        "Download rows as CSV",
        data=csv_data,
        file_name="smart_librarian_report.csv",
        mime="text/csv",
        on_click="ignore",
    )
    if _EXPORTS_AVAILABLE:
        download_cols[1].download_button(
            "Download standalone HTML report",
            data=export_report_html(report),
            file_name="smart_librarian_report.html",
            mime="text/html",
            on_click="ignore",
        )
        download_cols2 = st.columns(2)
        download_cols2[0].download_button(
            "Download report bundle (ZIP)",
            data=build_report_bundle(report),
            file_name="smart_librarian_report.zip",
            mime="application/zip",
            on_click="ignore",
        )
        download_cols2[1].download_button(
            "Download Power BI import kit (ZIP)",
            data=build_powerbi_import_bundle(report),
            file_name="smart_librarian_powerbi_kit.zip",
            mime="application/zip",
            on_click="ignore",
            help=(
                "Frozen report values plus typed Power Query scripts and a "
                "theme for manual import. Not a PBIP/PBIX file; no service "
                "publishing."
            ),
        )
    else:
        st.caption("HTML/ZIP export helpers are unavailable in this environment.")


def _page_builder(user_id, catalog, capabilities, use_llm):
    choices = catalog["choices"]
    state = st.session_state.get("state") or {}
    model_meta = choices.get("model") or {}
    st.markdown(
        "<div class='status-strip'>Published actual sales | Simulated "
        "approval &amp; registry | Snapshot as of "
        + html.escape(str(model_meta.get("snapshot_as_of", "unknown")))
        + " (frozen file, not live company systems) | Identity: "
        + html.escape(user_id) + "</div>",
        unsafe_allow_html=True,
    )
    _progress(state)

    heading_cols = st.columns([4, 1])
    heading_cols[0].header("Report builder")
    if heading_cols[1].button("New request", key="new_request"):
        if st.query_params.get("session_id"):
            del st.query_params["session_id"]
        for key in ("state", "catalog", "prefill", "preview_open", "actors",
                    "chat_text", "resume_attempted"):
            st.session_state.pop(key, None)
        st.session_state.form_rev += 1
        _new_session(user_id)
        st.rerun()
    st.caption(
        "Scope: 15 published products and product families, fiscal years "
        "2024/2025 plus reported quarters and half-years - global figures "
        "only, in EUR million. No country, monthly or forecast figures exist "
        "in this source."
    )
    st.caption(
        "Choose an example, confirm scope, then approve and preview."
    )

    cols = st.columns(len(_STARTERS))
    for col, (label, fragment, kind, exact_periods) in zip(cols, _STARTERS):
        if col.button(label, key=f"starter_{label}"):
            st.session_state.prefill = _starter_intent(
                choices, fragment, kind, exact_periods
            )
            st.session_state.form_rev += 1
            st.session_state.preview_open = False
            st.rerun()
    st.caption(
        "Starter buttons only prefill the form - review and confirm the "
        "exact scope; nothing is approved for you."
    )

    text = st.text_input(
        "Describe the report you want",
        placeholder="e.g. Show global Nubeqa reported sales in 2025",
        key="chat_text",
    )
    if use_llm:
        st.caption(
            "Processing mode: Live LLM intent extraction ("
            + f"{capabilities.get('label') or 'provider'}, "
            f"{capabilities.get('model')})"
        )
    else:
        st.caption("Processing mode: Offline parser")
    extraction_mode = state.get("extraction_mode")
    if extraction_mode == "offline_fallback_after_llm_unavailable":
        st.warning(
            "Last extraction: Offline fallback - live LLM unavailable."
        )
    elif extraction_mode == "llm":
        st.caption("Last extraction: Live LLM")
    elif extraction_mode == "offline":
        st.caption("Last extraction: Offline parser")
    if st.button("Send", key="chat_send", disabled=not text.strip()):
        try:
            with st.spinner(
                "Contacting configured provider; this can take a while..."
                if use_llm else "Processing..."
            ):
                response = api_post(
                    f"/api/sessions/{st.session_state.session_id}/messages",
                    {"user_id": user_id, "text": text, "use_llm": use_llm},
                    timeout=180 if use_llm else 30,
                )
        except httpx.HTTPError:
            _api_problem()
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
            st.error(f"API error {response.status_code}: {_detail(response)}")

    for message in state.get("messages") or []:
        role = "You" if message["role"] == "user" else "Librarian"
        st.markdown(f"**{role}:** {message['text']}")
    if state.get("limitations"):
        st.caption(f"Parser note: {state['limitations']}")

    products = choices.get("products") or []
    product_ids = [p["product_id"] for p in products]
    product_names = {p["product_id"]: p["product_name"] for p in products}
    periods = choices.get("periods") or []
    period_by_id = {p["period_id"]: p for p in periods}
    metric = (choices.get("metrics") or [{}])[0]
    market_ids = [m["market_id"] for m in choices.get("markets") or []]

    prefill = dict(state.get("partial_intent") or {})
    ui_prefill = st.session_state.get("prefill") or {}
    if (
        ui_prefill.get("product_ids") or ui_prefill.get("periods")
        or ui_prefill.get("months")
    ):
        prefill = {
            "product_ids": ui_prefill.get("product_ids") or [],
            "market_ids": ui_prefill.get("market_ids") or [],
            "metric_ids": ui_prefill.get("metric_ids") or [],
            "months": (
                ui_prefill.get("periods") or ui_prefill.get("months") or []
            ),
            "grain": ui_prefill.get("period_kind") or ui_prefill.get("grain"),
        }
    default_kind = (
        prefill.get("grain")
        if prefill.get("grain") in _PERIOD_TYPE_LABELS else "year"
    )
    default_kind_label = _PERIOD_TYPE_LABELS[default_kind]

    st.subheader("Confirm intent")
    st.caption(
        "The guided form is authoritative - nothing runs until you confirm "
        "this exact scope. Periods outside coverage are never silently "
        "reduced."
    )
    extra_products = [
        value for value in prefill.get("product_ids", [])
        if value not in product_ids
    ]
    sel_products = st.multiselect(
        "Products", product_ids + extra_products,
        default=[
            v for v in prefill.get("product_ids", [])
            if v in product_ids or v in extra_products
        ],
        format_func=lambda pid: product_names.get(pid, pid) + (
            " (outside coverage)" if pid in extra_products else ""
        ),
        key=_widget_key("product_ids"),
    )
    cols = st.columns(2)
    with cols[0]:
        type_label = st.selectbox(
            "Period type", [label for label, _ in _PERIOD_TYPES],
            index=[label for label, _ in _PERIOD_TYPES].index(
                default_kind_label
            ),
            key=_widget_key("period_kind"),
        )
    sel_kind = _PERIOD_TYPE_KINDS[type_label]
    period_options = [
        p["period_id"] for p in periods
        if p.get("period_kind") == sel_kind
    ]
    extras = [
        value for value in prefill.get("months", [])
        if value not in period_options
    ]
    with cols[1]:
        sel_periods = st.multiselect(
            "Reporting periods", period_options + extras,
            default=[
                v for v in prefill.get("months", [])
                if v in period_options or v in extras
            ] if prefill.get("grain") in (None, sel_kind) else [],
            format_func=lambda pid: (
                (period_by_id.get(pid) or {}).get("label") or pid
            ) + (" (outside coverage)" if pid in extras else ""),
            key=_widget_key("periods"),
        )
    st.caption(
        f"Confirm measure and market for this report: "
        f"{metric.get('name', 'Reported Sales')} "
        f"({metric.get('unit', 'EUR million')}) | Global - the only "
        "published scope; this is your explicit form confirmation, not "
        "inferred from your text."
    )

    unsupported_notes = list(state.get("unsupported") or [])
    for note in unsupported_notes:
        st.warning(f"Unsupported requirement flagged by the parser: {note}")
    for value in extra_products:
        st.warning(
            f"Extracted product not in the published selection: {value}"
        )
    for value in extras:
        st.warning(
            f"Extracted period not in coverage or the selected period "
            f"type: {value}"
        )
    prefill_markets = prefill.get("market_ids") or []
    if prefill_markets and sorted(prefill_markets) != ["GLOBAL"]:
        st.warning(
            "Extracted market scope is not Global: "
            + ", ".join(sorted(prefill_markets))
            + ". Only global reported sales are published here."
        )
    prefill_metrics = prefill.get("metric_ids") or []
    if prefill_metrics and prefill_metrics != [metric.get("metric_id")]:
        st.warning(
            "Extracted measures are not the published Reported Sales: "
            + ", ".join(sorted(prefill_metrics))
            + ". Only Reported Sales (EUR million) is available."
        )
    prefill_grain = prefill.get("grain")
    if prefill_grain and prefill_grain not in _PERIOD_TYPE_LABELS:
        st.warning(
            f"Extracted grain '{prefill_grain}' is not supported: choose "
            "Annual, Quarterly or Half-year."
        )
    needs_ack = bool(
        unsupported_notes or extras or extra_products
        or (prefill_markets and sorted(prefill_markets) != ["GLOBAL"])
        or (prefill_metrics and prefill_metrics != [metric.get("metric_id")])
        or (prefill_grain and prefill_grain not in _PERIOD_TYPE_LABELS)
    )
    ack = True
    if needs_ack:
        ack = st.checkbox(
            "Replace unsupported requirements with the selections above",
            key=_widget_key("ack"),
        )
    complete = bool(sel_products and sel_periods)
    if not complete:
        st.caption(
            "Select at least one product and one reporting period to "
            "enable confirmation."
        )
    if st.button(
        "Confirm intent", key=_widget_key("confirm"),
        disabled=not complete or (needs_ack and not ack),
    ):
        intent = {
            "product_ids": sel_products,
            "market_ids": market_ids,
            "metric_ids": [metric.get("metric_id")],
            "months": sel_periods,
            "grain": sel_kind,
        }
        try:
            response = api_post(
                f"/api/sessions/{st.session_state.session_id}/intent",
                {"user_id": user_id, "intent": intent},
            )
        except httpx.HTTPError:
            _api_problem()
            return
        if response.status_code == 200:
            st.session_state.state = response.json()
            st.session_state.preview_open = False
            st.session_state.prefill = intent
            st.rerun()
        else:
            st.error(f"API error {response.status_code}: {_detail(response)}")

    outcome = state.get("outcome")
    if outcome in (None, "CLARIFY", "CONFIRM_INTENT"):
        if state.get("questions"):
            st.info("Open questions: " + " ".join(state["questions"]))
        return
    if outcome == "ACCESS_DENIED":
        st.error(
            "Access denied for this simulated identity. No report details "
            "or values were returned."
        )
        return
    if outcome == "NEEDS_REVIEW":
        st.warning(
            "This request needs review before it can proceed: "
            + ", ".join(state.get("review_reasons") or [])
        )
        return

    proposal = state.get("proposal") or {}
    spec = proposal.get("spec") or {}
    selected_intent = {
        "product_ids": sorted(sel_products),
        "market_ids": sorted(market_ids),
        "metric_ids": sorted([metric.get("metric_id")]),
        "months": sorted(sel_periods),
        "grain": sel_kind,
    }
    if spec.get("intent") and selected_intent != spec["intent"]:
        st.warning(
            "Draft changed - confirm intent again. The decision below is "
            "stale and its approval/preview is hidden until you reconfirm."
        )
        return

    headings = {
        "REUSE": "Reuse an existing governed report",
        "PROPOSE_CHANGE": "Propose a change to an existing report",
        "PROPOSE_BUILD": "Propose building a new report",
    }
    st.subheader(headings.get(outcome, outcome))
    for note in state.get("candidate_explanations") or []:
        st.caption(note)
    st.caption(
        "Source: frozen public financial disclosure snapshot | Governance "
        "(approver, endorsement, registry) is simulated."
    )

    approval_status = proposal.get("approval_status")
    if approval_status == "pending":
        st.info(
            "Next action: a separate simulated approver must approve or "
            "reject this proposal before any preview."
        )
        actor_id = _approval_actor(
            (spec.get("intent") or {}).get("market_ids") or []
        )
        cols = st.columns(2)
        if cols[0].button("Approve proposal", type="primary",
                          key=_widget_key("approve")):
            _decide("approve", actor_id, user_id)
            st.rerun()
        if cols[1].button("Reject proposal", key=_widget_key("reject")):
            _decide("reject", actor_id, user_id)
            st.rerun()
    elif approval_status == "approved":
        st.success("Proposal approved for this session (simulated approval).")
    elif approval_status == "rejected":
        st.error("Proposal rejected. The report cannot be rendered.")
        return
    else:
        st.info("Exact coverage already exists - no approval required.")

    with st.expander("Evidence & specification", expanded=False):
        for item in state.get("evidence") or []:
            st.markdown(
                "<div class='card'><span class='card-title'>"
                + html.escape(str(item.get("evidence_id"))) + " - "
                + html.escape(str(item.get("kind"))) + "</span><br/>"
                + html.escape(str(item.get("detail"))) + "<br/>"
                + "<span class='small-muted'>"
                + html.escape(str(item.get("ref_path"))) + " -> "
                + html.escape(str(item.get("record_id"))) + " | "
                + html.escape(str(item.get("status")))
                + "</span></div>",
                unsafe_allow_html=True,
            )
        st.code(json.dumps(spec, indent=2), language="json")
        st.code(f"spec_hash: {proposal.get('spec_hash')}", language="text")

    if approval_status in ("approved", "not_required"):
        if st.button("Open report preview", key=_widget_key("preview")):
            st.session_state.preview_open = True
        if st.session_state.get("preview_open"):
            try:
                response = api_get(
                    f"/api/sessions/{st.session_state.session_id}/report",
                    {"user_id": user_id},
                )
            except httpx.HTTPError:
                _api_problem()
                return
            if response.status_code == 200:
                _render_report(response.json(), user_id)
            else:
                st.session_state.preview_open = False
                st.error(
                    f"Report unavailable ({response.status_code}): "
                    f"{_detail(response)}"
                )

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
                        f"{json.dumps(event.get('detail'))}"
                    )
            else:
                st.caption("Audit unavailable.")
        except httpx.HTTPError:
            st.caption("Audit unavailable (API offline).")


def _page_explorer(user_id):
    st.header("Performance explorer")
    st.caption(
        "Browse the frozen published figures directly. Values below come "
        "verbatim from the snapshot - nothing is aggregated, rescaled or "
        "derived."
    )
    try:
        response = api_get("/api/public-financials")
    except httpx.HTTPError:
        _api_problem()
        return
    if response.status_code != 200:
        st.error(f"Snapshot unavailable ({response.status_code}): "
                 f"{_detail(response)}")
        return
    payload = response.json()
    rows = payload.get("rows") or []
    periods = {p["period_id"]: p for p in payload.get("periods") or []}
    products = sorted({row["product_name"] for row in rows})
    cols = st.columns(2)
    with cols[0]:
        kind_label = st.selectbox(
            "Period type",
            [label for label, _ in _PERIOD_TYPES],
            key="explorer_period_kind",
        )
    with cols[1]:
        sel_products = st.multiselect(
            "Products", products, default=[], key="explorer_products"
        )
    sel_kind = _PERIOD_TYPE_KINDS[kind_label]
    kind_periods = [
        pid for pid, meta in periods.items()
        if meta.get("period_kind") == sel_kind
    ]
    sel_periods = st.multiselect(
        "Reporting periods", kind_periods, default=kind_periods,
        format_func=lambda pid: (periods.get(pid) or {}).get("label") or pid,
        key="explorer_periods",
    )
    filtered = [
        row for row in rows
        if row.get("period_kind") == sel_kind
        and row.get("period") in sel_periods
        and (not sel_products or row["product_name"] in sel_products)
    ]
    if not filtered:
        st.info("No rows match the selected filters.")
        return
    frame = pd.DataFrame(filtered)
    frame["period_label"] = frame["period"].map(
        lambda pid: (periods.get(pid) or {}).get("label") or pid
    )
    metric_id = next(
        (key for key in frame.columns if key.startswith("PUBLIC-")),
        "PUBLIC-REPORTED-SALES",
    )
    figure = go.Figure()
    for product, group in frame.groupby("product_name", sort=True):
        group = group.sort_values("period")
        figure.add_trace(go.Bar(
            x=group["period_label"], y=group[metric_id], name=product,
        ))
    figure.update_layout(
        barmode="group", xaxis_title="Reporting period",
        yaxis_title=payload.get("unit") or "EUR million",
        template="simple_white", font_family="Segoe UI",
    )
    st.plotly_chart(figure, use_container_width=True)
    st.dataframe(
        frame.rename(columns={
            "product_name": "Product",
            "period_label": "Reporting period",
            metric_id: (
                f"Reported sales ({payload.get('unit') or 'EUR million'})"
            ),
        })[["Product", "Reporting period",
            f"Reported sales ({payload.get('unit') or 'EUR million'})"]],
        use_container_width=True, hide_index=True,
    )
    with st.expander("Source rows", expanded=False):
        st.dataframe(frame.drop(columns=["period_label"]),
                     use_container_width=True, hide_index=True)
    if _EXPORTS_AVAILABLE:
        headers = [
            h for h in (
                "product_id", "product_name", "market_id", "market_name",
                "period", "period_kind", metric_id, "source_id",
                "source_table", "source_row_label", "source_column",
                "source_row",
            )
            if h in frame.columns
        ]
        st.download_button(
            "Download filtered rows (CSV)",
            data=serialize_rows_csv(filtered, headers),
            file_name="public_financials_rows.csv",
            mime="text/csv",
            on_click="ignore",
        )


def _page_saved(user_id):
    st.header("Saved reports")
    st.caption(
        "Local registry records only - these are simulated published assets, "
        "not BI workspace artifacts."
    )
    try:
        response = api_get(
            "/api/assets", {"user_id": user_id, "domain_id": "public_sales"}
        )
    except httpx.HTTPError:
        _api_problem()
        return
    if response.status_code != 200:
        st.error(f"Assets unavailable ({response.status_code}): "
                 f"{_detail(response)}")
        return
    assets = response.json().get("assets") or []
    if not assets:
        st.caption("No registered reports yet for this identity.")
    for asset in assets:
        coverage = asset.get("coverage") or {}
        st.markdown(
            "<div class='card'><span class='card-title'>"
            + html.escape(str(asset.get("name"))) + "</span> `"
            + html.escape(str(asset.get("asset_id"))) + "`<br/>"
            + "<span class='small-muted'>scope: "
            + html.escape(
                f"{len(coverage.get('product_ids') or [])} product(s) | "
                f"{len(coverage.get('months') or [])} period(s) | "
                f"grain {asset.get('grain')}"
            )
            + " | owner: "
            + html.escape(
                str(asset.get("owner_name") or asset.get("owner_id"))
            )
            + " | " + html.escape(str(asset.get("endorsement")))
            + " | " + html.escape(str(asset.get("lifecycle_status")))
            + "</span></div>",
            unsafe_allow_html=True,
        )
        if st.button("Open / reuse", key=f"reuse_{asset.get('asset_id')}"):
            try:
                reuse = api_post(
                    f"/api/assets/{asset.get('asset_id')}/reuse",
                    {"user_id": user_id},
                )
            except httpx.HTTPError:
                _api_problem()
                return
            if reuse is not None and reuse.status_code == 200:
                payload = reuse.json()
                for key in ("state", "prefill", "preview_open"):
                    st.session_state.pop(key, None)
                st.session_state.session_id = payload["session_id"]
                st.query_params["session_id"] = payload["session_id"]
                st.session_state.state = payload["state"]
                st.session_state.prefill = (
                    payload["state"].get("partial_intent") or {}
                )
                st.session_state.form_rev += 1
                st.session_state.pending_workspace = "Report builder"
                st.rerun()
            else:
                detail = (
                    _detail(reuse) if reuse is not None else "API offline"
                )
                st.error(f"Reuse failed: {detail}")


def _page_sources():
    st.header("Sources & coverage")
    try:
        response = api_get("/api/public-financials")
    except httpx.HTTPError:
        _api_problem()
        return
    if response.status_code != 200:
        st.error(f"Snapshot unavailable ({response.status_code}): "
                 f"{_detail(response)}")
        return
    payload = response.json()
    st.caption(
        "Every figure in this demo traces to one of the frozen publisher "
        "sources below. Governance (approvals, endorsement, registry) is "
        "simulated for demonstration only."
    )
    st.markdown(
        f"**Snapshot scope:** {len(payload.get('products') or [])} products/"
        f"product families | {len(payload.get('periods') or [])} reporting "
        f"periods | unit: {payload.get('unit')} | grain: "
        f"{payload.get('grain')} | retrieved: "
        f"{payload.get('retrieved_at_utc')}"
    )
    if payload.get("disclaimer"):
        st.info(payload["disclaimer"])
    st.caption(
        "Not available from this source: country or regional splits, "
        "monthly figures, forecasts, currency-adjusted growth, or any "
        "product outside the reviewed selection."
    )
    for source in payload.get("sources") or []:
        source_url = str(source.get("source_url") or "")
        if source_url.startswith("https://"):
            url_markup = (
                f'<a href="{html.escape(source_url, quote=True)}">'
                f"{html.escape(source_url)}</a>"
            )
        else:
            url_markup = html.escape(source_url)
        st.markdown(
            "<div class='card'><span class='card-title'>"
            + html.escape(str(source.get("source_title")))
            + "</span><br/>"
            + url_markup + "<br/>"
            + "<span class='small-muted'>sha256: "
            + html.escape(str(source.get("source_sha256"))) + "<br/>"
            + "retrieved (UTC): "
            + html.escape(str(source.get("retrieved_at_utc"))) + "<br/>"
            + "snapshot: "
            + html.escape(str(source.get("source_snapshot"))) + "<br/>"
            + html.escape(str(source.get("notes") or ""))
            + "</span></div>",
            unsafe_allow_html=True,
        )


def main():
    st.set_page_config(
        page_title="Smart Librarian - public sales (demo)", layout="wide"
    )
    st.markdown(_CSS, unsafe_allow_html=True)
    st.title("Smart Librarian")
    st.markdown(
        "<div class='tagline'>Published actuals, governed answers.</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Governed reporting over published actual sales figures. Identities, "
        "approvals and the asset registry are simulated - not authentication "
        "or enterprise access control."
    )

    try:
        domains_response = api_get("/api/domains")
        capabilities_response = api_get("/api/capabilities")
        users_response = api_get("/api/demo-users")
    except httpx.HTTPError:
        _api_problem()
        return
    if domains_response.status_code != 200 \
            or users_response.status_code != 200:
        _api_problem()
        return
    capabilities = (
        capabilities_response.json()
        if capabilities_response.status_code == 200
        else {"configured": False}
    )
    users = users_response.json().get("users") or []
    if not users:
        st.error("No simulated identities are available from the API.")
        return
    user_options = {u["user_id"]: u for u in users}

    pending_workspace = st.session_state.pop("pending_workspace", None)
    if pending_workspace:
        st.session_state["workspace_select"] = pending_workspace

    with st.sidebar:
        st.markdown("<div class='badge'>Real data only</div>",
                    unsafe_allow_html=True)
        st.caption("Published actual sales | Simulated approval & registry")
        workspace = st.radio(
            "Workspace",
            options=[
                "Report builder",
                "Performance explorer",
                "Saved reports",
                "Sources & coverage",
            ],
            key="workspace_select",
        )
        provider_label = capabilities.get("label") or "provider"
        if capabilities.get("configured"):
            llm_note = (
                f"{provider_label} configured "
                f"({capabilities.get('model')})"
            )
        elif capabilities.get("error"):
            llm_note = f"config error - {capabilities.get('error')}"
        else:
            llm_note = "not configured - offline parser will be used"
        llm_selected = st.checkbox(
            "Use LLM intent extraction (opt-in)",
            value=False,
            key="use_llm",
            disabled=not capabilities.get("configured"),
            help=(
                f"Sends your request text plus catalog metadata choices "
                f"to the configured provider ({provider_label}). Catalog "
                "metadata contains no source business figures, but your "
                "request text may contain confidential information - do "
                "not enter secrets. Checking this box is your permission "
                "for that transmission."
            ),
        )
        use_llm = bool(llm_selected) and bool(
            capabilities.get("configured")
        )
        st.caption(
            f"LLM provider: {llm_note}. No provider call happens unless "
            "this box is checked."
        )
        with st.expander("Demo settings", expanded=False):
            sticky_user = st.session_state.get("sticky_user_id")
            if (sticky_user in user_options
                    and "identity_select" not in st.session_state):
                st.session_state["identity_select"] = sticky_user
            user_id = st.selectbox(
                "Simulated user",
                options=list(user_options),
                format_func=lambda uid: (
                    f"{user_options[uid].get('name')} ({uid})"
                ),
                key="identity_select",
            )
            st.session_state.sticky_user_id = user_id
            st.caption(f"API: {API_URL}")

    if "form_rev" not in st.session_state:
        st.session_state.form_rev = 0
    if st.session_state.get("user_id") != user_id:
        for key in ("state", "catalog", "prefill", "preview_open", "actors",
                    "chat_text", "resume_attempted"):
            st.session_state.pop(key, None)
        st.session_state.user_id = user_id
        st.session_state.session_id = None
        st.session_state.form_rev += 1

    requested = st.query_params.get("session_id")
    if requested \
            and requested != st.session_state.get("session_id") \
            and requested != st.session_state.get("resume_attempted"):
        st.session_state.resume_attempted = requested
        _try_resume(requested, user_id)

    if not st.session_state.get("session_id"):
        if not _new_session(user_id):
            return

    resume_notice = st.session_state.pop("resume_notice", None)
    if resume_notice:
        st.warning(resume_notice)

    if st.session_state.get("catalog") is None:
        st.session_state.catalog = _load_catalog(user_id)
        if st.session_state.catalog is None:
            _api_problem()
            return

    if workspace == "Report builder":
        if "state" not in st.session_state:
            _refresh_state(user_id)
        _page_builder(user_id, st.session_state.catalog, capabilities,
                      use_llm)
    elif workspace == "Performance explorer":
        _page_explorer(user_id)
    elif workspace == "Saved reports":
        _page_saved(user_id)
    else:
        _page_sources()
