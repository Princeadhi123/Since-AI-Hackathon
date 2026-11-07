"""Live smoke for the real-data-only demo UI (AppTest + running API).

Requires a real-data-only API (default create_app) reachable at
SMART_LIBRARIAN_API_URL (default http://127.0.0.1:8011). Exercises annual,
quarterly and half-year scopes, approval, preview, downloads, saved-report
reuse, workspace roundtrip, session URL and stale-edit gating. No numeric
gold answers - assertions cover outcomes, labels and controls only.

Run:  PYTHONPATH=src python tests/ui_real_demo_smoke.py
"""

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
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
                 "subheader", "header"):
        parts.extend(e.value for e in getattr(at, kind, []))
    return " ".join(parts)


def workspace_radio(at):
    return next(
        r for r in list(at.sidebar.radio) + list(at.radio)
        if r.label == "Workspace"
    )


def fill_and_confirm(at, products, periods, period_type="Annual"):
    by_label(at.multiselect, "Products").set_value(products)
    by_label(at.selectbox, "Period type").set_value(period_type)
    at.run()
    by_label(at.multiselect, "Reporting periods").set_value(periods)
    at.run()
    by_label(at.button, "Confirm intent").click()
    at.run()


def approve_and_preview(at):
    approve = by_label(at.button, "Approve proposal")
    if approve is not None:
        actor = by_label(at.selectbox, "Simulated approval actor")
        if actor is not None:
            actor.set_value("DEMO-PUBLIC-APPROVER")
            at.run()
        by_label(at.button, "Approve proposal").click()
        at.run()
        text = all_text(at)
        check("approved", "approved" in text.lower())
        if "approved" not in text.lower():
            for marker in ("rejected", "error", "Decision"):
                idx = text.find(marker)
                if idx >= 0:
                    print("DEBUG:", text[max(0, idx - 200):idx + 400])
                    break
    preview = by_label(at.button, "Open report preview")
    if preview is None:
        check("preview button exists", False)
        return
    preview.click()
    at.run()


def catalog_products(at):
    widget = by_label(at.multiselect, "Products")
    return list(widget.options or [])


def main():
    at = AppTest.from_file(str(ROOT / "apps" / "streamlit_app.py"),
                           default_timeout=60)
    at.run()
    check("app runs without exception", not at.exception)

    check("no synthetic domain selector", not any(
        s.label == "Domain"
        for s in list(at.sidebar.selectbox) + list(at.selectbox)
    ))
    radio = workspace_radio(at)
    check("four workspaces", set(radio.options) == {
        "Report builder", "Performance explorer", "Saved reports",
        "Sources & coverage",
    })
    check("real data badge", "Real data only" in all_text(at))
    check("session url written",
          bool(at.query_params.get("session_id")))
    check("new request button prominent",
          by_label(at.button, "New request") is not None)
    options = catalog_products(at)
    check("products listed", len(options) >= 1)
    nubeqa = next((o for o in options if "NUBEQA" in o.upper()), options[0])
    other = next((o for o in options if o != nubeqa), nubeqa)

    fill_and_confirm(at, [nubeqa], ["2025"], "Annual")
    check("annual decision shown",
          "Propose" in all_text(at) or "Reuse" in all_text(at))
    approve_and_preview(at)
    check("annual preview renders", len(at.dataframe) >= 1)
    check("public caption", "Published actual" in all_text(at))
    downloads = {b.label for b in at.get("download_button")}
    check("zip download", "Download report bundle (ZIP)" in downloads)
    check("powerbi download",
          "Download Power BI import kit (ZIP)" in downloads)
    with_expander = [e.label for e in at.expander]
    check("source rows expander", "Source rows" in with_expander)

    by_label(at.button, "New request").click()
    at.run()
    check("new request resets", not at.exception)

    fill_and_confirm(at, [nubeqa], ["2025-Q2", "2026-Q2"], "Quarterly")
    check("quarterly decision shown",
          "Propose" in all_text(at) or "Reuse" in all_text(at))
    stale_target = by_label(at.multiselect, "Products")
    approve = by_label(at.button, "Approve proposal")
    check("approval visible before edit", approve is not None
          or "Reuse an existing governed report" in all_text(at))
    if approve is not None:
        stale_target.set_value([nubeqa, other])
        at.run()
        check("edit hides stale approval",
              by_label(at.button, "Approve proposal") is None)
        stale_target.set_value([nubeqa])
        at.run()
        by_label(at.button, "Confirm intent").click()
        at.run()
    approve_and_preview(at)
    check("quarterly preview renders", len(at.dataframe) >= 1)

    by_label(at.button, "New request").click()
    at.run()
    fill_and_confirm(at, [nubeqa], ["2025-H1"], "Half-year")
    check("half-year decision shown",
          "Propose" in all_text(at) or "Reuse" in all_text(at))
    approve_and_preview(at)
    check("half-year preview renders", len(at.dataframe) >= 1)

    workspace_radio(at).set_value("Performance explorer")
    at.run()
    check("explorer renders", not at.exception)
    check("explorer defaults annual",
          by_label(at.selectbox, "Period type").value == "Annual")
    check("explorer table", len(at.dataframe) >= 1)

    workspace_radio(at).set_value("Sources & coverage")
    at.run()
    check("sources page", "reports.bayer.com" in all_text(at))

    workspace_radio(at).set_value("Saved reports")
    at.run()
    reuse = by_label(at.button, "Open / reuse")
    check("saved report listed", reuse is not None)
    if reuse is not None:
        reuse.click()
        at.run()
        check("reuse returns to builder", not at.exception
              and workspace_radio(at).value == "Report builder")
        check("reuse shows governed state",
              "Reuse" in all_text(at) or "Propose" in all_text(at))

    workspace_radio(at).set_value("Report builder")
    at.run()
    check("workspace roundtrip keeps session",
          bool(at.query_params.get("session_id")))
    check("no exceptions overall", not at.exception)

    print("FAILURES:", FAILURES or "none")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
