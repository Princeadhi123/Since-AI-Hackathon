"""Challenge builder-pack demo UI (Streamlit), HTTP-only against the API.

Shows only values returned by /api/challenge endpoints; no workbook access
and no business arithmetic in the UI. Approvals and renders are distinct
explicit clicks bound to spec_hash + plan revision.
"""

import html
import os

import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from smart_librarian.reporting.challenge_pbip import PBIP_STATUS

API_URL = os.environ.get("SMART_LIBRARIAN_API_URL", "http://127.0.0.1:8000")
BASE = "/api/challenge"

_CSS = """
<style>
.stApp { background-color: #f5f8fa; }
h1, h2, h3 { color: #0f3557; font-family: 'Segoe UI', sans-serif; }
.status-strip { background: #0f3557; color: #e8f0f4; padding: 6px 14px;
  border-radius: 6px; font-size: 0.85rem; margin-bottom: 12px; }
</style>
"""

_DOMAINS = ["commercial", "market_access", "supply", "launch"]

_PREFILLS = {
    "commercial": {
        "product_ids": ["P-NUB"], "market_ids": ["DE"],
        "metric_ids": ["net_sales_m_eur_syn", "forecast_m_eur_syn"],
        "months": ["2026-01-01", "2026-02-01", "2026-03-01"],
        "grain": "month",
    },
    "market_access": {
        "product_ids": ["P-NUB"], "market_ids": ["DE"],
        "metric_ids": ["coverage_pct_syn", "reimbursement_status"],
        "months": [], "grain": "snapshot",
    },
    "supply": {
        "product_ids": ["P-NUB"], "market_ids": ["DE"],
        "metric_ids": ["otif_pct_syn", "inventory_weeks_syn", "risk_status"],
        "months": [], "grain": "snapshot",
    },
    "launch": {
        "product_ids": ["P-NUB"], "market_ids": ["JP"],
        "metric_ids": ["milestone_id", "milestone_type", "status"],
        "months": ["2026-01-01"], "grain": "event",
    },
}

_PAGES = ["Builder pack reports", "Estate decisions", "Saved plans",
          "Ownership & deployment"]

_IDENTITY_KEYS = [
    "ch_plan", "estate_plan", "ch_saved", "ch_extraction", "ch_catalog",
    "ch_form_rev", "ch_plan_outcome", "saved_audit", "ch_text",
    "ch_req_context", "saved_plan",
]


def api_get(path, params=None):
    return httpx.get(f"{API_URL}{path}", params=params, timeout=15)


def api_post(path, payload, timeout=30):
    return httpx.post(f"{API_URL}{path}", json=payload, timeout=timeout)


def _detail(response):
    try:
        return response.json().get("detail", response.text)
    except Exception:
        return response.text


def _show_error(response):
    st.error(f"API error {response.status_code}: {_detail(response)}")


def _safe_get(path, params=None):
    try:
        return api_get(path, params)
    except httpx.HTTPError:
        st.error(f"Cannot reach the API at {API_URL}.")
        return None


def _safe_post(path, payload, timeout=30):
    try:
        return api_post(path, payload, timeout=timeout)
    except httpx.HTTPError:
        st.error(f"Cannot reach the API at {API_URL}.")
        return None


def _actors():
    response = _safe_get(f"{BASE}/actors")
    if response is not None and response.status_code == 200:
        return {a["user_id"]: a for a in response.json()["actors"]}
    return {}


def _banner(user_id, provenance=None):
    fingerprint = (provenance or {}).get("source_sha256", "")
    st.markdown(
        "<div class='status-strip'>OFFICIAL SYNTHETIC CHALLENGE BUILDER "
        "PACK - not real Bayer performance | native units, source rows, "
        "no aggregation | source fingerprint "
        + html.escape(str(fingerprint))[:16] + "... | Simulated identity: "
        + html.escape(user_id) + "</div>",
        unsafe_allow_html=True,
    )


def _load_catalog(domain_id):
    response = _safe_get(f"{BASE}/catalog", {"domain_id": domain_id})
    if response is None:
        return None
    if response.status_code != 200:
        _show_error(response)
        return None
    return response.json()


def _invalidate_saved():
    st.session_state.pop("ch_saved", None)


def _set_plan(key, plan):
    st.session_state[key] = plan
    _invalidate_saved()


def _plan_badge(plan):
    st.caption(
        f"Plan `{plan['plan_id']}` | kind: {plan['kind']} | status: "
        f"**{plan['status']}** | revision {plan['revision']} | spec_hash "
        f"`{plan['spec_hash'][:16]}...`"
    )


def _audit_view(audit):
    with st.expander("Audit trail", expanded=False):
        st.dataframe(pd.DataFrame(audit), use_container_width=True,
                     hide_index=True)


def _report_view(report, audit=None):
    spec = report.get("spec") or {}
    intent = spec.get("intent") or {}
    grain = intent.get("grain")
    rows = report.get("rows") or []
    units = report.get("units") or {}
    metric_ids = list(intent.get("metric_ids") or [])
    frame = pd.DataFrame(rows)
    st.caption(
        "Frozen source rows - no aggregation, native units, value_type "
        "preserved. KPI IDs are contextual references, not certified "
        "executable model bindings."
    )
    numeric = [
        m for m in metric_ids
        if units.get(m) not in ("category", "identifier")
        and m in frame.columns
    ]
    by_unit: dict[str, list[str]] = {}
    for metric in numeric:
        by_unit.setdefault(units.get(metric) or "value", []).append(metric)
    if not frame.empty and grain == "month":
        for unit, metrics in sorted(by_unit.items()):
            figure = go.Figure()
            for (product, market), group in frame.groupby(
                ["product_name", "market_name"], sort=True
            ):
                group = group.sort_values("month")
                for metric in metrics:
                    figure.add_trace(go.Scatter(
                        x=group["month"], y=group[metric],
                        mode="lines+markers",
                        name=f"{product} {market} {metric}",
                    ))
            figure.update_layout(template="simple_white",
                                 font_family="Segoe UI",
                                 yaxis_title=unit)
            st.plotly_chart(figure, use_container_width=True)
    elif not frame.empty and grain == "snapshot":
        labels = frame["product_name"] + " " + frame["market_name"]
        for unit, metrics in sorted(by_unit.items()):
            figure = go.Figure()
            for metric in metrics:
                figure.add_trace(
                    go.Bar(x=labels, y=frame[metric], name=metric))
            figure.update_layout(barmode="group", template="simple_white",
                                 font_family="Segoe UI", yaxis_title=unit)
            st.plotly_chart(figure, use_container_width=True)
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _download_exports(plan_id, user_id):
    st.caption("Downloads serialize the frozen approved render only.")
    cols = st.columns(5)
    specs = [
        ("HTML", "html", "text/html", "challenge_report.html"),
        ("CSV", "csv", "text/csv", "challenge_report.csv"),
        ("ZIP bundle", "zip", "application/zip",
         "challenge_report_bundle.zip"),
        ("Power Query kit (CSV+M)", "kit", "application/zip",
         "challenge_powerbi_kit.zip"),
        ("Power BI project (PBIP ZIP)", "pbip", "application/zip",
         "challenge_report_pbip.zip"),
    ]
    for col, (label, fmt, mime, filename) in zip(cols, specs):
        response = _safe_get(
            f"{BASE}/plans/{plan_id}/export",
            {"user_id": user_id, "format": fmt},
        )
        if response is not None and response.status_code == 200:
            col.download_button(
                label, data=response.content, file_name=filename,
                mime=mime, on_click="ignore",
                key=f"dl_{plan_id}_{fmt}",
            )
    st.caption(PBIP_STATUS)
    with st.expander("Power BI Desktop handoff steps", expanded=False):
        st.markdown(
            "1. Download the **Power BI project (PBIP ZIP)** and extract "
            "the full archive, keeping the `.Report` and `.SemanticModel` "
            "folders beside `GovernedReport.pbip`.\n"
            "2. Open `GovernedReport.pbip` in Power BI Desktop with "
            "project (PBIP) support.\n"
            "3. Run **Refresh** if Desktop prompts - it loads the "
            "embedded frozen snapshot, not new business data.\n"
            "4. Use the **Dashboard**, **Source Evidence** and "
            "**Ownership & Evidence** tabs; chart measures return BLANK "
            "on multi-row contexts - never summed or averaged."
        )


def _approval_block(plan, user_id, state_key):
    if plan["requester"] != user_id:
        st.caption(
            "This plan belongs to a different requester; you can read the "
            "scoped specification but cannot decide it."
        )
        return
    actors = _actors()
    approvers = [
        aid for aid, a in actors.items()
        if "approver" in (a.get("roles") or [])
    ]
    stewards = [
        aid for aid, a in actors.items()
        if "steward" in (a.get("roles") or [])
    ]
    options = approvers + stewards
    actor_id = st.selectbox(
        "Simulated decision actor (steward selection is refused by the "
        "API)",
        options=options or ["DEMO-CHALLENGE-APPROVER"],
        key=f"{state_key}_actor",
    )
    cols = st.columns(2)
    for col, decision in zip(cols, ("approve", "reject")):
        if col.button(decision.capitalize(), key=f"{state_key}_{decision}"):
            response = _safe_post(
                f"{BASE}/plans/{plan['plan_id']}/approval",
                {
                    "user_id": user_id,
                    "actor_user_id": actor_id,
                    "spec_hash": plan["spec_hash"],
                    "decision": decision,
                    "expected_revision": plan["revision"],
                },
            )
            if response is None:
                return
            if response.status_code == 200:
                body = response.json()
                _set_plan(state_key, body["plan"])
                if body.get("outcome") == "REUSE":
                    st.query_params["plan_id"] = body["plan"]["plan_id"]
                    st.info(
                        "An equivalent approved report already exists; "
                        f"plan {body.get('superseded_plan_id')} was "
                        "superseded and the approved plan is reused."
                    )
                elif body.get("outcome"):
                    st.info(body["outcome"])
                st.rerun()
            else:
                _show_error(response)


def _do_render(plan, user_id, state_key):
    response = _safe_post(
        f"{BASE}/plans/{plan['plan_id']}/render",
        {"user_id": user_id, "spec_hash": plan["spec_hash"],
         "expected_revision": plan["revision"]},
    )
    if response is None:
        return
    if response.status_code == 200:
        _set_plan(state_key, response.json()["plan"])
        st.rerun()
    else:
        _show_error(response)


def _frozen_report(plan_id, user_id):
    response = _safe_get(f"{BASE}/plans/{plan_id}/report",
                         {"user_id": user_id})
    if response is None:
        return None
    if response.status_code != 200:
        _show_error(response)
        return None
    return response.json()


def _page_builder(user_id):
    st.header("Builder pack reports")
    domain = st.selectbox(
        "Source domain", _DOMAINS,
        format_func=lambda d: d.replace("_", " ").title(),
        key="ch_domain",
    )
    catalog = st.session_state.get("ch_catalog")
    if catalog is None or catalog["choices"]["domain_id"] != domain:
        domain_changed = (
            catalog is not None
            and catalog["choices"]["domain_id"] != domain
        )
        catalog = _load_catalog(domain)
        if catalog is None:
            return
        st.session_state.ch_catalog = catalog
        if domain_changed:
            st.session_state.pop("ch_extraction", None)
            plan = st.session_state.get("ch_plan")
            if not plan or plan.get("domain_id") != domain:
                st.session_state.pop("ch_plan", None)
                st.session_state.pop("ch_plan_outcome", None)
    choices = catalog["choices"]
    _banner(user_id, choices)

    with st.expander("Source business requests (original rows)",
                     expanded=False):
        response = _safe_get(f"{BASE}/requests")
        if response is not None and response.status_code == 200:
            st.caption(
                "Original source rows. Context fields may contradict the "
                "request text; they are shown verbatim and are NOT "
                "auto-truth - the text and your confirmed form govern."
            )
            frame = pd.DataFrame(response.json()["requests"])
            pick = st.selectbox(
                "Sample request", ["(none)"] + list(frame["request_id"]),
                key="ch_req_pick",
            )
            if st.button("Load request text", key="ch_req_load",
                         disabled=pick == "(none)"):
                row = frame[frame["request_id"] == pick].iloc[0]
                st.session_state.ch_text = row["request_text"]
                st.session_state.ch_req_context = (
                    f"Context labels (possibly contradictory): product "
                    f"'{row['product_context']}', market "
                    f"'{row['market_context']}'"
                )
                st.rerun()
            if st.session_state.get("ch_req_context"):
                st.caption(st.session_state.ch_req_context)
            st.dataframe(frame, use_container_width=True, hide_index=True)
        elif response is not None:
            _show_error(response)

    st.subheader("Natural-language intake (optional)")
    use_llm = st.checkbox(
        "Send request text + catalog metadata to the LLM (opt-in). Do not "
        "enter secrets or confidential text - the app sends no source "
        "facts, usage or owner emails.",
        key="ch_use_llm",
    )
    text = st.text_input("Describe the report", key="ch_text")
    if st.button("Extract intent", key="ch_extract",
                 disabled=not (text or "").strip()):
        response = _safe_post(
            f"{BASE}/extract",
            {"user_id": user_id, "domain_id": domain,
             "text": text, "use_llm": use_llm},
            timeout=240 if use_llm else 30,
        )
        if response is None:
            return
        if response.status_code == 200:
            st.session_state.ch_extraction = response.json()
            st.session_state.ch_form_rev = (
                st.session_state.get("ch_form_rev", 0) + 1
            )
            st.rerun()
        else:
            _show_error(response)
    extraction = st.session_state.get("ch_extraction") or {}
    mode = extraction.get("extraction_mode")
    if use_llm:
        st.caption(f"Selected mode: live LLM | last extraction: {mode}")
    elif mode:
        st.caption(f"Selected mode: offline | last extraction: {mode}")
    if mode == "offline_fallback_after_llm_unavailable":
        st.warning("Extraction used the offline fallback - live LLM "
                   "unavailable.")
    if extraction.get("limitations"):
        st.caption(extraction["limitations"])
    for note in extraction.get("unsupported") or []:
        st.warning(f"Unsupported: {note}")
    for value in extraction.get("invalid_ids") or []:
        st.warning(f"Unrecognized ID preserved for review: {value}")
    for question in extraction.get("questions") or []:
        st.info(question)
    proposed = extraction.get("proposed_intent") or {}
    if proposed.get("grain") and proposed["grain"] != choices["grain"]:
        st.warning(
            f"Proposed grain '{proposed['grain']}' does not match this "
            f"source ({choices['grain']}); the guided form uses the "
            "source grain."
        )

    st.subheader("Guided confirmation (authoritative)")
    st.caption(
        "Nothing is inferred silently. The prefill button fills the exact "
        "example scope only when you press it; you still confirm "
        "explicitly."
    )
    if st.button(f"Prefill {domain} example", key="ch_prefill"):
        st.session_state.ch_extraction = {
            "partial_intent": dict(_PREFILLS[domain]),
        }
        st.session_state.ch_form_rev = (
            st.session_state.get("ch_form_rev", 0) + 1
        )
        st.rerun()

    partial = (extraction.get("partial_intent") or {})
    rev = st.session_state.get("ch_form_rev", 0)

    def key(name):
        return f"ch_form_{domain}_{name}_{rev}"

    product_opts = {p["product_id"]: p["product_name"]
                    for p in choices["products"]}
    market_opts = {m["market_id"]: m["market_name"]
                   for m in choices["markets"]}
    metric_opts = {m["metric_id"]: f"{m['name']} ({m['unit']})"
                   for m in choices["metrics"]}
    sel_products = st.multiselect(
        "Products", list(product_opts),
        default=[v for v in partial.get("product_ids", [])
                 if v in product_opts],
        format_func=lambda v: f"{product_opts[v]} ({v})",
        key=key("products"),
    )
    sel_markets = st.multiselect(
        "Markets", list(market_opts),
        default=[v for v in partial.get("market_ids", [])
                 if v in market_opts],
        format_func=lambda v: f"{market_opts[v]} ({v})",
        key=key("markets"),
    )
    sel_metrics = st.multiselect(
        "Source fields", list(metric_opts),
        default=[v for v in partial.get("metric_ids", [])
                 if v in metric_opts],
        format_func=lambda v: metric_opts[v], key=key("metrics"),
    )
    grain = choices["grain"]
    if grain == "snapshot":
        sel_months = []
        st.caption("Snapshot source: no period selection applies.")
    else:
        sel_months = st.multiselect(
            "Months (required for this grain)", choices["months"],
            default=[v for v in partial.get("months", [])
                     if v in choices["months"]],
            key=key("months"),
        )
    owners = {o["owner_id"]: o["owner_name"] for o in choices["owners"]}
    sel_owner = st.selectbox(
        "Accountable owner (active - explicit selection required)",
        list(owners), index=None,
        format_func=lambda v: f"{owners[v]} ({v})", key=key("owner"),
        placeholder="Choose an active owner",
    )
    rationale = st.text_input("Rationale", key=key("rationale"))
    complete = bool(
        sel_products and sel_markets and sel_metrics and sel_owner
        and (grain == "snapshot" or sel_months)
    )
    if st.button("Create plan (requires approval)", key="ch_create",
                 disabled=not complete):
        response = _safe_post(
            f"{BASE}/plans",
            {
                "kind": "report", "user_id": user_id,
                "domain_id": domain,
                "intent": {
                    "product_ids": sel_products,
                    "market_ids": sel_markets,
                    "metric_ids": sel_metrics,
                    "months": sel_months,
                    "grain": grain,
                },
                "owner_id": sel_owner, "rationale": rationale,
            },
        )
        if response is None:
            return
        if response.status_code == 200:
            _set_plan("ch_plan", response.json()["plan"])
            st.session_state.ch_plan_outcome = response.json()["outcome"]
            st.query_params["plan_id"] = st.session_state.ch_plan["plan_id"]
            st.rerun()
        else:
            _show_error(response)

    plan = st.session_state.get("ch_plan")
    if plan:
        if st.session_state.get("ch_plan_outcome") == "REUSE":
            st.info("An approved plan with an equivalent confirmed scope "
                    "already exists; the saved plan is reused.")
        _plan_badge(plan)
        with st.expander("Specification", expanded=False):
            st.json(plan["spec"])
        candidates = plan.get("estate_candidates") or []
        if candidates:
            with st.expander(
                "Source estate records in this product/market scope "
                "(metadata only)", expanded=False,
            ):
                st.caption(
                    "Candidate source records for human review - these "
                    "are metadata entries, NOT executable existing "
                    "reports and not certified equivalents of this plan."
                )
                st.dataframe(pd.DataFrame(candidates),
                             use_container_width=True, hide_index=True)
        if plan["status"] == "pending":
            st.subheader("Approval (separate actor)")
            _approval_block(plan, user_id, "ch_plan")
        if plan["status"] == "approved":
            if st.button("Render frozen report", key="ch_render"):
                _do_render(plan, user_id, "ch_plan")
        if plan["status"] == "rendered":
            payload = _frozen_report(plan["plan_id"], user_id)
            if payload:
                _report_view(payload["report"], payload["audit"])
                _download_exports(plan["plan_id"], user_id)
        _audit_view(plan.get("audit") or [])


def _page_estate(user_id):
    st.header("Estate decisions")
    st.caption(
        "Source estate records - proposals only; nothing executes "
        "against the estate or running business systems. Global "
        "requester scope required."
    )
    query = st.text_input(
        "Filter assets (id/name/product/market/platform)",
        key="ch_estate_q")
    response = _safe_get(f"{BASE}/estate",
                         {"user_id": user_id, "q": query})
    if response is None:
        return
    if response.status_code != 200:
        _show_error(response)
        return
    assets = response.json()["assets"]
    if not assets:
        st.info("No assets match.")
        return
    options = {a["asset_id"]: a for a in assets}
    asset_id = st.selectbox(
        "Asset", list(options),
        format_func=lambda a: f"{options[a]['asset_name']} ({a})",
        key="ch_estate_pick",
    )
    detail_response = _safe_get(f"{BASE}/estate/{asset_id}",
                                {"user_id": user_id})
    if detail_response is None:
        return
    if detail_response.status_code != 200:
        _show_error(detail_response)
        return
    evidence = detail_response.json()
    st.subheader(f"{evidence['asset']['asset_name']} ({asset_id})")
    cols = st.columns(3)
    cols[0].markdown("**Asset**")
    cols[0].json(evidence["asset"])
    cols[1].markdown("**Model / owner**")
    cols[1].json({"model": evidence.get("model"),
                  "owner": evidence.get("owner"),
                  "workspace": evidence.get("workspace")})
    cols[2].markdown("**KPIs**")
    cols[2].json(evidence.get("kpis") or [])
    with st.expander("Usage (monthly unique users - not summed)"):
        st.dataframe(pd.DataFrame(evidence.get("usage") or []),
                     use_container_width=True, hide_index=True)
    with st.expander("Lineage / downstream"):
        st.json({"lineage": evidence.get("lineage"),
                 "downstream_ids": evidence.get("downstream_ids")})
    with st.expander("Signals / data quality / migration backlog"):
        st.json({"signals": evidence.get("signals"),
                 "data_quality": evidence.get("data_quality"),
                 "migration_inputs": evidence.get("migration_inputs")})
    with st.expander("Governance rules (source)"):
        st.dataframe(
            pd.DataFrame(evidence.get("governance_rules") or []),
            use_container_width=True, hide_index=True)
    if evidence.get("governance_gaps"):
        st.warning("Governance gaps: "
                   + ", ".join(evidence["governance_gaps"]))
    st.caption(evidence.get("decision_note") or "")
    if evidence.get("consolidation_candidates"):
        with st.expander("Consolidation candidates (equivalence NOT "
                         "verified)"):
            st.caption(
                "Shared product/market scope plus at least one canonical "
                "metric label only - variants, filters, visuals and "
                "model must be reconciled before any replacement."
            )
            st.dataframe(
                pd.DataFrame(evidence["consolidation_candidates"]),
                use_container_width=True, hide_index=True,
            )
    st.caption(
        "KPI context is catalogue metadata, not a certified executable "
        "binding; this evidence cannot prove report equivalence."
    )

    st.subheader("Lifecycle proposal")
    action = st.selectbox(
        "Action", ["reuse", "repair", "consolidate", "retire", "migrate"],
        key="ch_action",
    )
    target = None
    if action == "consolidate":
        candidates = {
            c["asset_id"]: c
            for c in evidence.get("consolidation_candidates") or []
        }
        if not candidates:
            st.warning("No consolidation candidates for this asset.")
        else:
            target = st.selectbox(
                "Target asset (candidate; equivalence not verified)",
                list(candidates), index=None,
                format_func=lambda a: (
                    f"{a} - shared: "
                    f"{', '.join(candidates[a]['shared_canonical_metrics'])}"
                ),
                key="ch_target", placeholder="Choose a candidate",
            )
    owner_opts = {
        o["owner_id"]: o["owner_name"]
        for o in evidence.get("owner_options") or []
    }
    owner = st.selectbox(
        "Accountable owner (active - explicit selection required)",
        list(owner_opts), index=None,
        format_func=lambda v: f"{owner_opts.get(v, '')} ({v})",
        key="ch_lc_owner", placeholder="Choose an active owner",
    )
    rationale = st.text_input("Rationale (required)", key="ch_lc_rationale")
    if st.button("Create lifecycle proposal", key="ch_lc_create",
                 disabled=not (rationale or "").strip() or not owner):
        response = _safe_post(
            f"{BASE}/plans",
            {"kind": "lifecycle", "user_id": user_id,
             "asset_id": asset_id, "action": action,
             "target_asset_id": target, "owner_id": owner,
             "rationale": rationale},
        )
        if response is None:
            return
        if response.status_code == 200:
            _set_plan("estate_plan", response.json()["plan"])
            st.query_params["plan_id"] = response.json()["plan"]["plan_id"]
            st.rerun()
        else:
            _show_error(response)
    plan = st.session_state.get("estate_plan")
    if plan:
        _plan_badge(plan)
        if plan["status"] == "pending":
            _approval_block(plan, user_id, "estate_plan")
        elif plan["status"] == "approved":
            st.success(
                "Approved proposal; not executed. Release requires the "
                "named sign-offs listed in the specification - no estate "
                "change was made."
            )
        _audit_view(plan.get("audit") or [])


def _page_saved(user_id):
    st.header("Saved plans")
    if st.button("Refresh", key="ch_saved_refresh"):
        _invalidate_saved()
    if "ch_saved" not in st.session_state:
        response = _safe_get(f"{BASE}/plans", {"user_id": user_id})
        if response is None:
            return
        if response.status_code != 200:
            _show_error(response)
            return
        st.session_state.ch_saved = response.json()["plans"]
    plans = st.session_state.ch_saved or []
    if not plans:
        st.info("No saved plans for this identity.")
        return
    options = {p["plan_id"]: p for p in plans}
    resume = st.query_params.get("plan_id")
    plan_id = st.selectbox(
        "Plan", list(options),
        index=(list(options).index(resume) if resume in options else 0),
        format_func=lambda p: (
            f"{options[p]['kind']} | {options[p]['status']} | {p[:8]}"
        ),
        key="ch_saved_pick",
    )
    response = _safe_get(f"{BASE}/plans/{plan_id}", {"user_id": user_id})
    if response is None:
        return
    if response.status_code != 200:
        _show_error(response)
        return
    plan = response.json()["plan"]
    st.query_params["plan_id"] = plan_id
    _plan_badge(plan)
    with st.expander("Specification / proposal evidence", expanded=False):
        st.json(plan["spec"])
    if plan["kind"] == "lifecycle":
        st.caption("Lifecycle proposals are never executed by this demo.")
    if plan["status"] == "pending":
        _approval_block(plan, user_id, "saved_plan")
    if plan["kind"] == "report" and plan["status"] == "approved":
        if st.button("Render frozen report", key="ch_saved_render"):
            _do_render(plan, user_id, "saved_plan")
    if plan["kind"] == "report" and plan["status"] == "rendered":
        payload = _frozen_report(plan_id, user_id)
        if payload:
            _report_view(payload["report"], payload["audit"])
            _download_exports(plan_id, user_id)
    _audit_view(plan.get("audit") or [])


def _page_ownership(user_id):
    st.header("Ownership & deployment")
    st.subheader("Simulated roles (this demo)")
    st.dataframe(pd.DataFrame([
        {"actor": "DEMO-CHALLENGE-REQUESTER",
         "roles": "requester", "scope": "all markets",
         "can": "search estate, create plans, request renders"},
        {"actor": "DEMO-CHALLENGE-FI",
         "roles": "requester", "scope": "FI only",
         "can": "create FI-scoped plans; estate and foreign markets "
               "denied; shared FI-scoped approved reports reusable"},
        {"actor": "DEMO-CHALLENGE-APPROVER",
         "roles": "approver", "scope": "all markets",
         "can": "approve/reject pending plans as a separate actor"},
        {"actor": "DEMO-CHALLENGE-STEWARD",
         "roles": "steward", "scope": "all markets",
         "can": "review only - approval attempts are refused"},
    ]), use_container_width=True, hide_index=True)
    st.subheader("Hosting & access boundaries")
    st.markdown(
        "- API and UI run on 127.0.0.1 plain HTTP; there is no TLS, no "
        "login and no real authorization.\n"
        "- The builder workbook is read-only source; plans and renders "
        "persist in a local runtime SQLite under `var/`.\n"
        "- The report registry is this local plan store - not a Power BI "
        "workspace or service publish.\n"
        "- PBIP ZIP export is an offline generated project; Desktop "
        "open/refresh is not verified (see export label)."
    )
    st.subheader("Missing for production")
    st.markdown(
        "- Entra ID authentication and role claims\n"
        "- TLS termination and network hardening\n"
        "- Power BI workspace/Fabric deployment pipeline and service "
        "identities\n"
        "- Real data connections, refresh monitoring and row-level "
        "security"
    )


def _clear_identity_state():
    for key in _IDENTITY_KEYS:
        st.session_state.pop(key, None)
    for key in list(st.session_state):
        if str(key).startswith(("ch_form_", "saved_plan", "builder_")):
            st.session_state.pop(key, None)
    if st.query_params.get("plan_id"):
        del st.query_params["plan_id"]


def _resume_from_query(user_id):
    """Restore a plan referenced by ?plan_id= for the current identity."""
    plan_id = st.query_params.get("plan_id")
    if not plan_id or st.session_state.get("ch_resume_done") == plan_id:
        return
    st.session_state.ch_resume_done = plan_id
    response = _safe_get(f"{BASE}/plans/{plan_id}", {"user_id": user_id})
    if response is None or response.status_code != 200:
        st.session_state.ch_resume_notice = (
            "Unable to open the requested saved plan for this identity."
        )
        if st.query_params.get("plan_id"):
            del st.query_params["plan_id"]
        return
    plan = response.json()["plan"]
    if plan["kind"] == "report":
        st.session_state.ch_domain = plan.get("domain_id") or "commercial"
        st.session_state.pop("ch_catalog", None)
        st.session_state.ch_plan = plan
        st.session_state.ch_page = _PAGES[0]
    else:
        st.session_state.estate_plan = plan
        st.session_state.ch_page = _PAGES[2]


def main():
    st.set_page_config(page_title="Challenge Builder Pack Demo",
                       layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)
    actors = _actors()
    requesters = [
        aid for aid, a in actors.items()
        if "requester" in (a.get("roles") or [])
    ]
    if not requesters:
        st.error(
            f"Cannot reach the challenge API at {API_URL} - start it "
            "with `python run_demo.py --mode challenge` and reload."
        )
        return
    with st.sidebar:
        st.title("Challenge demo")
        user_id = st.selectbox(
            "Simulated requester identity", requesters, key="ch_user"
        )
    previous = st.session_state.get("ch_identity")
    if previous is not None and previous != user_id:
        _clear_identity_state()
        st.session_state.pop("ch_resume_done", None)
        st.session_state.pop("ch_resume_notice", None)
    if previous != user_id:
        st.session_state.ch_identity = user_id
    _resume_from_query(user_id)
    with st.sidebar:
        page = st.radio("Workspace", _PAGES, key="ch_page")
    if st.session_state.get("ch_resume_notice"):
        st.warning(st.session_state.ch_resume_notice)
        st.session_state.pop("ch_resume_notice")
    st.caption(
        "Official SinceAI synthetic builder pack - not real Bayer "
        "performance. Simulated identities and approvals only."
    )
    if page == _PAGES[0]:
        _page_builder(user_id)
    elif page == _PAGES[1]:
        _page_estate(user_id)
    elif page == _PAGES[2]:
        _page_saved(user_id)
    else:
        _page_ownership(user_id)


if __name__ == "__main__":
    main()
