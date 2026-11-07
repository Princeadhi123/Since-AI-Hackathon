"""Opt-in real Aitta through Streamlit AppTest and the running HTTP API."""

import argparse
import json
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

from live_aitta_e2e import CASES, require, same_intent
from ui_smoke import by_label, send

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-provider-call", action="store_true")
    args = parser.parse_args()
    if not args.allow_provider_call:
        print("No provider call made: --allow-provider-call required.")
        return 2
    output = ROOT / "artifacts/live_aitta"
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for identifier in ("reuse", "logistics_build", "quality_build"):
        case = next(c for c in CASES if c["case_id"] == identifier)
        at = AppTest.from_file(str(ROOT / "apps/streamlit_app.py"),
                               default_timeout=210)
        at.run()
        by_label(at.selectbox, "Domain").set_value(case["domain"])
        at.run()
        checkbox = by_label(at.checkbox, "Use LLM intent extraction (opt-in)")
        require(checkbox is not None and not checkbox.disabled, "LLM option unavailable")
        checkbox.set_value(True)
        at.run()
        send(at, case["request_text"])
        require(not at.exception, "UI exception during live intake")
        state = at.session_state["state"]
        require(state["extraction_mode"] == "llm", "UI used offline fallback")
        require(state["outcome"] == "CONFIRM_INTENT", "UI intake not confirmable")
        same_intent(state["partial_intent"], case["confirmed_intent"])
        by_label(at.button, "Confirm intent").click()
        at.run()
        require(bool(at.session_state["state"]["evidence"]), "No UI decision evidence")
        proposal = at.session_state["state"]["proposal"]
        if proposal["approval_status"] == "pending":
            by_label(at.selectbox, "Simulated approval actor").set_value("DEMO-APPROVER")
            at.run()
            by_label(at.button, "Approve proposal").click()
            at.run()
        by_label(at.button, "Open report preview").click()
        at.run()
        require(not at.exception, "UI exception during report preview")
        require(any(len(frame.value) == 3 for frame in at.dataframe),
                "Missing three-month report table")
        labels = {getattr(item, "label", None) for item in at.get("download_button")}
        require({
            "Download specification JSON", "Download rows as CSV",
            "Download standalone HTML report", "Download report bundle (ZIP)",
        }.issubset(labels), "Missing UI download controls")
        result = {"domain": case["domain"], "status": "pass",
                  "extraction_mode": state["extraction_mode"],
                  "session_id": at.session_state["session_id"],
                  "outcome": at.session_state["state"]["outcome"]}
        results.append(result)
        (output / "live_ui_results.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8",
        )
        print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
