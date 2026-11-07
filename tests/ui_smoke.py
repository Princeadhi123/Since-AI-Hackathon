"""Streamlit AppTest smoke against a RUNNING local API (not part of unittest
discovery - requires `python run_demo.py` or equivalent servers).

Exercises: guided form completing without chat, multi-turn clarification,
REUSE preview, PROPOSE_BUILD approval, identity switching and unsupported
draft-metric rejection. No numeric gold answers beyond the lead fixtures.

Run:  PYTHONPATH=src python tests/ui_smoke.py
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
    for kind in ("caption", "info", "warning", "error", "success", "subheader"):
        parts.extend(e.value for e in getattr(at, kind, []))
    return " ".join(parts)


def send(at, text):
    by_label(at.text_input, "Describe the report you want").set_value(text)
    at.run()  # re-render so Send becomes enabled
    by_label(at.button, "Send").click()
    at.run()


def fill(at, products, markets, metrics, months,
         product_label="Products", market_label="Markets"):
    by_label(at.multiselect, product_label).set_value(products)
    by_label(at.multiselect, market_label).set_value(markets)
    by_label(at.multiselect, "Metrics").set_value(metrics)
    by_label(at.multiselect, "Months").set_value(months)
    at.run()


def main():
    at = AppTest.from_file(str(ROOT / "apps" / "streamlit_app.py"),
                           default_timeout=30)
    at.run()
    check("app runs without exception", not at.exception)
    confirm = by_label(at.button, "Confirm intent")
    check("confirm disabled on blank form", confirm is not None and confirm.disabled)

    domain = by_label(at.selectbox, "Domain")
    check("default domain is public_sales",
          domain is not None and domain.value == "public_sales")
    check("fiscal years selector present",
          by_label(at.multiselect, "Fiscal years") is not None)
    prompt = by_label(at.text_input, "Describe the report you want")
    check("public example placeholder",
          prompt is not None and "Nubeqa" in (prompt.placeholder or ""))
    scenario = by_label(
        at.button, "Public data - Nubeqa Global 2025 Reported Sales"
    )
    check("public scenario button", scenario is not None)
    scenario.click()
    at.run()
    by_label(at.button, "Confirm intent").click()
    at.run()
    text = all_text(at)
    check("public intent confirmed",
          "Propose" in text or "Reuse an existing governed report" in text)
    approve = by_label(at.button, "Approve proposal")
    if approve is not None:
        actor = by_label(at.selectbox, "Simulated approval actor")
        check("public approver widget", actor is not None)
        actor.set_value("DEMO-PUBLIC-APPROVER")
        at.run()
        actor = by_label(at.selectbox, "Simulated approval actor")
        check("public approver selected",
              actor is not None and actor.value == "DEMO-PUBLIC-APPROVER")
        by_label(at.button, "Approve proposal").click()
        at.run()
        check("public approved", "approved" in all_text(at).lower())
    by_label(at.button, "Open report preview").click()
    at.run()
    check("public banner", "Published actual" in all_text(at))
    check("fiscal_year column in preview", any(
        "fiscal_year" in list(getattr(df.value, "columns", []))
        for df in at.dataframe
    ))
    downloads = [b.label for b in at.get("download_button")]
    check("public zip bundle offered",
          "Download report bundle (ZIP)" in downloads)
    check("public powerbi kit offered",
          "Download Power BI import kit (ZIP)" in downloads)
    check("no exceptions during public flow", not at.exception)
    by_label(at.selectbox, "Domain").set_value("sales")
    at.run()
    check("sales domain selected for synthetic steps", not at.exception)

    # 1. Blank form completed without any chat -> REUSE path.
    fill(at, ["DEMO-P-NUB"], ["DE"], ["DEMO-NET-SALES"],
         ["2026-01-01", "2026-02-01", "2026-03-01"])
    confirm = by_label(at.button, "Confirm intent")
    check("confirm enabled once form complete", not confirm.disabled)
    confirm.click()
    at.run()
    check("reuse banner", "Reuse an existing governed report" in all_text(at))
    check("reuse needs no approval",
          "no approval required" in all_text(at).lower())
    by_label(at.button, "Open report preview").click()
    at.run()
    check("preview renders rows", len(at.dataframe) >= 1)
    check("preview totals from engine",
          any(m.value == "327,000 EUR" for m in at.metric))

    # 2. Identity switch -> fresh session, guided form cleared.
    by_label(at.selectbox, "Simulated user").set_value("DEMO-USER-FI")
    at.run()
    check("session cleared on identity switch",
          by_label(at.button, "Confirm intent").disabled)

    # 3. Multi-turn chat on FI identity.
    send(at, "Kerendia Net Sales")
    check("first turn asks for more", "need a few more details" in all_text(at))
    send(at, "Finland January through March 2026")
    check("follow-up reaches confirmable intent",
          "complete monthly intent" in all_text(at))

    # Multi-select extracted plus add forecast -> PROPOSE_BUILD + approval.
    fill(at, ["DEMO-P-KER"], ["FI"],
         ["DEMO-NET-SALES", "DEMO-FORECAST"],
         ["2026-01-01", "2026-02-01", "2026-03-01"])
    by_label(at.button, "Confirm intent").click()
    at.run()
    text = all_text(at)
    # Registry persists across runs: PROPOSE_BUILD first time, REUSE later.
    check("build-or-reuse banner",
          "Propose building a new report" in text
          or "Reuse an existing governed report" in text)
    approve = by_label(at.button, "Approve proposal")
    if approve is not None:
        approve.click()
        at.run()
        check("approved", "approved" in all_text(at).lower())
    by_label(at.button, "Open report preview").click()
    at.run()
    check("build preview renders", len(at.dataframe) >= 1)

    # 4. Unsupported requirement -> ack checkbox gates confirm.
    send(at, "Weekly Nubeqa Net Sales Finland January 2026")
    check("unsupported requirement surfaced",
          "unsupported" in all_text(at).lower())
    fill(at, ["DEMO-P-NUB"], ["FI"], ["DEMO-NET-SALES"], ["2026-01-01"])
    confirm = by_label(at.button, "Confirm intent")
    check("ack required before replacing unsupported", confirm.disabled)
    by_label(at.checkbox,
             "Replace unsupported requirements with the selections above"
             ).set_value(True)
    at.run()
    confirm = by_label(at.button, "Confirm intent")
    check("confirm enabled after ack", not confirm.disabled)
    confirm.click()
    at.run()
    check("proceeds after ack", "Propose" in all_text(at)
          or "Reuse" in all_text(at))

    # 5. Clean turn clears unsupported, then draft metric -> NEEDS_REVIEW.
    send(at, "Show Kerendia Finland")
    check("unsupported notes cleared on new turn",
          not any("weekly" in w.value.lower() for w in at.warning))
    fill(at, ["DEMO-P-NUB"], ["FI"], ["DEMO-GROSS-SALES"], ["2026-01-01"])
    by_label(at.button, "Confirm intent").click()
    at.run()
    check("draft metric needs review", "needs review" in all_text(at).lower())
    check("no exceptions during flow", not at.exception)

    # 6. Operational domain: scenario prefill -> build -> approve -> preview,
    #    then artifact download buttons are offered. The registry persists
    #    across runs, so a repeat may legitimately resolve to REUSE instead.
    by_label(at.selectbox, "Simulated user").set_value("DEMO-USER-GLOBAL")
    at.run()
    by_label(at.selectbox, "Domain").set_value("logistics")
    at.run()
    scenario = by_label(
        at.button, "Logistics - Cold Chain Germany Q1 (all metrics)"
    )
    check("logistics scenario button", scenario is not None)
    scenario.click()
    at.run()
    by_label(at.button, "Confirm intent").click()
    at.run()
    text = all_text(at)
    if "Propose building a new report" in text:
        check("separate approver shown",
              "Simulated approval actor" in
              " ".join(s.label for s in at.selectbox))
        approve = by_label(at.button, "Approve proposal")
        check("logistics pending approval", approve is not None)
        approve.click()
        at.run()
        check("logistics approved", "approved" in all_text(at).lower())
    else:
        check("logistics reuses registered asset on repeat",
              "Reuse an existing governed report" in text)
    by_label(at.button, "Open report preview").click()
    at.run()
    check("logistics preview renders", len(at.dataframe) >= 1)
    check("published asset id shown", "GEN-" in all_text(at))
    downloads = [b.label for b in at.get("download_button")]
    check("html export offered",
          "Download standalone HTML report" in downloads)
    check("zip bundle offered",
          "Download report bundle (ZIP)" in downloads)
    check("no exceptions during logistics flow", not at.exception)

    # 7. Quality domain preview path.
    by_label(at.selectbox, "Domain").set_value("quality")
    at.run()
    scenario = by_label(
        at.button, "Quality - Tablet Line A Germany Q1 (all metrics)"
    )
    check("quality scenario button", scenario is not None)
    scenario.click()
    at.run()
    by_label(at.button, "Confirm intent").click()
    at.run()
    text = all_text(at)
    check("quality build-or-reuse banner",
          "Propose building a new report" in text
          or "Reuse an existing governed report" in text)
    approve = by_label(at.button, "Approve proposal")
    if approve is not None:
        approve.click()
        at.run()
    by_label(at.button, "Open report preview").click()
    at.run()
    check("quality preview renders", len(at.dataframe) >= 1)

    # 8. New request resets; asset library reuse opens a REUSE session.
    by_label(at.button, "New request").click()
    at.run()
    check("new request clears form",
          by_label(at.button, "Confirm intent").disabled)
    reuse_button = None
    for button in at.button:
        if button.label == "Open / reuse":
            reuse_button = button
            break
    check("library reuse button present", reuse_button is not None)
    if reuse_button is not None:
        reuse_button.click()
        at.run()
        check("library reuse resolves to governed reuse",
              "Reuse an existing governed report" in all_text(at)
              or "Propose" in all_text(at))
        if hasattr(at, "query_params"):
            check("url updated with resumed session",
                  bool(at.query_params.get("session_id")))

    print("FAILURES:", FAILURES or "none")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
