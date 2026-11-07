"""Fresh-browser session-resume smoke against a RUNNING local API.

Creates real backend sessions over HTTP, then opens a brand-new AppTest
with ?session_id=... set BEFORE the first run - the same thing a fresh
browser tab does. Asserts the UI actually adopts that session (including
its domain), fails loudly on the wrong identity, and hides stale approval.

Run:  SMART_LIBRARIAN_API_URL=http://127.0.0.1:8001 PYTHONPATH=src \
      python tests/ui_resume_smoke.py
"""

import os
import sys
from pathlib import Path

import httpx
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
API = os.environ.get("SMART_LIBRARIAN_API_URL", "http://127.0.0.1:8001")
FAILURES = []


def check(label, condition):
    print(("PASS" if condition else "FAIL"), label)
    if not condition:
        FAILURES.append(label)


def by_label(widgets, label):
    for widget in widgets:
        if getattr(widget, "label", None) == label:
            return widget
    return None


def all_text(at):
    parts = [m.value for m in at.markdown]
    for kind in ("caption", "info", "warning", "error", "success",
                 "subheader", "code", "text"):
        parts.extend(
            getattr(e, "value", getattr(e, "body", ""))
            for e in getattr(at, kind, [])
        )
    return " ".join(str(p) for p in parts)


def make_session(user_id, domain_id, intent):
    sid = httpx.post(
        f"{API}/api/sessions",
        json={"user_id": user_id, "domain_id": domain_id}, timeout=15,
    ).json()["session_id"]
    state = httpx.post(
        f"{API}/api/sessions/{sid}/intent",
        json={"user_id": user_id, "intent": intent}, timeout=30,
    ).json()
    return sid, state


def fresh_app(session_id=None):
    at = AppTest.from_file(str(ROOT / "apps" / "streamlit_app.py"),
                           default_timeout=30)
    if session_id:
        at.query_params["session_id"] = session_id
    at.run()
    return at


LOGISTICS = {
    "product_ids": ["DEMO-L-COLD"], "market_ids": ["DE"],
    "metric_ids": ["DEMO-DELIVERED", "DEMO-ON-TIME-PCT", "DEMO-LEAD-DAYS"],
    "months": ["2026-01-01", "2026-02-01", "2026-03-01"], "grain": "month",
}
QUALITY = {
    "product_ids": ["DEMO-Q-TAB"], "market_ids": ["DE"],
    "metric_ids": ["DEMO-INSPECTED", "DEMO-REJECTED", "DEMO-REJECT-PCT",
                   "DEMO-BATCHES"],
    "months": ["2026-01-01", "2026-02-01", "2026-03-01"], "grain": "month",
}


def main():
    # 1. Fresh-browser resume of a logistics session under GLOBAL.
    sid, state = make_session("DEMO-USER-GLOBAL", "logistics", LOGISTICS)
    at = fresh_app(sid)
    check("app runs", not at.exception)
    check("adopts requested session id",
          at.session_state["session_id"] == sid)
    check("domain synced to logistics",
          by_label(at.selectbox, "Domain").value == "logistics")
    check("operational entity label present",
          by_label(at.multiselect, "Distribution lanes") is not None)
    prefill = at.session_state["prefill"] or {}
    check("scope rehydrated",
          prefill.get("product_ids") == LOGISTICS["product_ids"]
          and prefill.get("market_ids") == LOGISTICS["market_ids"]
          and prefill.get("months") == LOGISTICS["months"])

    # 2. Fresh-browser resume of a quality session.
    qsid, _ = make_session("DEMO-USER-GLOBAL", "quality", QUALITY)
    at = fresh_app(qsid)
    check("adopts quality session id",
          at.session_state["session_id"] == qsid)
    check("domain synced to quality",
          by_label(at.selectbox, "Domain").value == "quality")
    check("production-lines label present",
          by_label(at.multiselect, "Production lines") is not None)

    # 3. Wrong identity cannot resume an FI-owned session.
    fsi, fstate = make_session("DEMO-USER-FI", "sales", {
        "product_ids": ["DEMO-P-KER"], "market_ids": ["FI"],
        "metric_ids": ["DEMO-NET-SALES", "DEMO-FORECAST"],
        "months": ["2026-01-01"], "grain": "month",
    })
    at = fresh_app(fsi)  # default identity is GLOBAL
    text = all_text(at)
    check("cannot-resume warning shown", "Unable to resume" in text)
    fi_hash = ((fstate.get("proposal") or {}).get("spec_hash"))
    check("foreign proposal never exposed",
          not fi_hash or fi_hash not in text)
    check("did not adopt foreign session",
          at.session_state["session_id"] != fsi)

    # 4. New request replaces the session and blanks the form.
    sid2, _ = make_session("DEMO-USER-GLOBAL", "logistics", LOGISTICS)
    at = fresh_app(sid2)
    check("resumed second session",
          at.session_state["session_id"] == sid2)
    by_label(at.button, "New request").click()
    at.run()
    check("new request changes session id",
          at.session_state["session_id"] != sid2)
    check("new request blanks form",
          by_label(at.button, "Confirm intent").disabled)

    # 5. Editing the confirmed scope hides the stale approval/preview.
    sid3, _ = make_session("DEMO-USER-GLOBAL", "logistics", LOGISTICS)
    at = fresh_app(sid3)
    lanes = by_label(at.multiselect, "Distribution lanes")
    lanes.set_value(["DEMO-L-STD"])
    at.run()
    check("draft-change warning",
          "Draft changed" in all_text(at))
    check("stale approval hidden",
          by_label(at.button, "Approve proposal") is None)
    check("stale preview hidden",
          by_label(at.button, "Open report preview") is None)

    print("FAILURES:", FAILURES or "none")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
