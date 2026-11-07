"""Opt-in synthetic Aitta workflow checks, not an accuracy benchmark.

Uses an isolated runtime DB; never treats offline fallback as live success.
Run with PYTHONPATH=src python tests/live_aitta_e2e.py --allow-provider-call.
"""

import argparse
import csv
import io
import json
import math
import os
import sys
import uuid
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from smart_librarian.llm.providers import resolve_provider
from smart_librarian.reporting.exports import build_report_bundle
from smart_librarian.settings import load_settings

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("product_ids", "market_ids", "metric_ids", "months", "grain")
MONTHS = ["2026-01-01", "2026-02-01", "2026-03-01"]
SALES = json.loads(
    (ROOT / "tests/fixtures/demo_scenarios.json").read_text(encoding="utf-8")
)["cases"]
CASES = [dict(case, domain="sales") for case in SALES]
CASES.extend([
    {
        "case_id": "logistics_build", "domain": "logistics",
        "user_id": "DEMO-USER-GLOBAL",
        "request_text": (
            "For the Cold Chain lane to Germany, give me monthly Delivered Orders, "
            "On Time Delivery %, and Average Lead Time, January through March 2026."
        ),
        "confirmed_intent": {
            "product_ids": ["DEMO-L-COLD"], "market_ids": ["DE"],
            "metric_ids": ["DEMO-DELIVERED", "DEMO-ON-TIME-PCT", "DEMO-LEAD-DAYS"],
            "months": MONTHS, "grain": "month",
        },
        "expected": {"outcome": "PROPOSE_BUILD"},
        "totals": {"DEMO-DELIVERED": 300, "DEMO-ON-TIME-PCT": 28000 / 300,
                   "DEMO-LEAD-DAYS": 800 / 300},
    },
    {
        "case_id": "quality_build", "domain": "quality",
        "user_id": "DEMO-USER-GLOBAL",
        "request_text": (
            "Show monthly Inspected Units and Rejection Rate % for Tablet Line A "
            "in Finland in the first quarter (Q1) of 2026."
        ),
        "confirmed_intent": {
            "product_ids": ["DEMO-Q-TAB"], "market_ids": ["FI"],
            "metric_ids": ["DEMO-INSPECTED", "DEMO-REJECT-PCT"],
            "months": MONTHS, "grain": "month",
        },
        "expected": {"outcome": "PROPOSE_BUILD"},
        "totals": {"DEMO-INSPECTED": 4500, "DEMO-REJECT-PCT": 4800 / 4500},
    },
])


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def same_intent(actual, expected):
    for field in FIELDS:
        value = actual.get(field)
        target = expected[field]
        require(
            sorted(value or []) == sorted(target) if isinstance(target, list)
            else value == target,
            f"Extracted {field} differs: {value!r} != {target!r}",
        )


def request(client, method, path, status=200, **kwargs):
    response = client.request(method, path, **kwargs)
    require(response.status_code == status,
            f"{method} {path}: expected {status}, got {response.status_code}")
    return response.json()


def run_case(client, case, output, runtime, saved_intake=None):
    user = case["user_id"]
    sid = request(client, "POST", "/api/sessions", json={
        "user_id": user, "domain_id": case["domain"],
    })["session_id"]
    base = f"/api/sessions/{sid}"
    params = {"user_id": user}
    state = saved_intake if saved_intake is not None else request(
        client, "POST", base + "/messages", json={
            "user_id": user, "text": case["request_text"], "use_llm": True,
        },
    )
    (output / "intake.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    require(state["extraction_mode"] == "llm",
            "Aitta unavailable: offline fallback is NOT a live pass")
    require(state.get("proposal") is None, "Chat must not bypass confirmation")
    if case["case_id"] == "unsupported_metric":
        require(state["outcome"] == "CLARIFY", "Unsupported metric must stop intake")
        require(any("gross sales" in str(note).lower() for note in state["unsupported"]),
                "Unsupported Gross Sales requirement was silently dropped")
        require(state["partial_intent"].get("metric_ids", []) in ([], ["DEMO-GROSS-SALES"]),
                "Unsupported metric was silently replaced with a supported metric")
        request(client, "GET", base + "/report", status=409, params=params)
        # A user can still select the catalog's draft metric in the form;
        # that explicit confirmation must also be blocked deterministically.
        blocked = request(client, "POST", base + "/intent", json={
            "user_id": user, "intent": case["confirmed_intent"],
        })
        require(blocked["outcome"] == "NEEDS_REVIEW", "Draft metric escaped review")
        request(client, "GET", base + "/report", status=409, params=params)
        return {"session_id": sid, "outcome": "CLARIFY -> NEEDS_REVIEW", "mode": "llm"}
    if case["confirmed_intent"] is None:
        require(state["outcome"] == "CLARIFY", "Ambiguous request must clarify")
        require(all(not state["partial_intent"].get(key) for key in FIELDS[:-1]),
                "Ambiguous request invented scope")
        require(bool(state["questions"]), "Missing clarification questions")
        state = request(client, "POST", base + "/messages", json={
            "user_id": user, "use_llm": True,
            "text": "Monthly Nubeqa Net Sales in Germany for January through March 2026.",
        })
        require(state["extraction_mode"] == "llm", "Follow-up fell back offline")
        same_intent(state["partial_intent"], SALES[0]["confirmed_intent"])
        state = request(client, "POST", base + "/intent", json={
            "user_id": user, "intent": {k: state["partial_intent"][k] for k in FIELDS},
        })
        require(state["outcome"] == "REUSE", "Clarified request must resolve to REUSE")
        request(client, "GET", base + "/report", params=params)
        return {"session_id": sid, "outcome": "CLARIFY -> REUSE", "mode": "llm"}

    same_intent(state["partial_intent"], case["confirmed_intent"])
    state = request(client, "POST", base + "/intent", json={
        "user_id": user, "intent": {k: state["partial_intent"][k] for k in FIELDS},
    })
    require(state["outcome"] == case["expected"]["outcome"],
            f"Unexpected decision: {state['outcome']}")
    (output / "decision.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    if case["expected"].get("must_not_generate_report"):
        require(state.get("proposal") is None, "Blocked request has a proposal")
        request(client, "GET", base + "/report", status=409, params=params)
        return {"session_id": sid, "outcome": state["outcome"], "mode": "llm"}

    require(bool(state["evidence"]), "Decision lacks evidence")
    proposal = state["proposal"]
    approval = {
        "user_id": user, "proposal_id": proposal["proposal_id"],
        "spec_hash": proposal["spec_hash"], "decision": "approve",
        "actor_user_id": "DEMO-APPROVER",
    }
    if proposal["approval_status"] == "pending":
        request(client, "GET", base + "/report", status=409, params=params)
        request(client, "POST", base + "/approval", status=403,
                json={**approval, "actor_user_id": user})
        request(client, "POST", base + "/approval", status=409,
                json={**approval, "spec_hash": "0" * 64})
        request(client, "POST", base + "/approval", json=approval)
    report = request(client, "GET", base + "/report", params=params)
    require(len(report["rows"]) == 3, "Expected one row per requested month")
    expected_totals = dict(case.get("totals", {}))
    for metric, key in (("DEMO-NET-SALES", "net_sales_eur"),
                        ("DEMO-FORECAST", "forecast_eur")):
        if key in case["expected"]:
            require([row[metric] for row in report["rows"]] == case["expected"][key],
                    f"Wrong monthly {metric}")
        if "total_" + key in case["expected"]:
            expected_totals[metric] = case["expected"]["total_" + key]
    for metric, expected in expected_totals.items():
        require(math.isclose(report["totals"][metric], expected, rel_tol=1e-9),
                f"Wrong total {metric}")
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    bundle = build_report_bundle(report)
    (output / "report.zip").write_bytes(bundle)
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        require(set(archive.namelist()) == {
            "report.html", "report.csv", "specification.json", "README.txt",
        }, "Unexpected bundle contents")
        for name in archive.namelist():
            (output / name).write_bytes(archive.read(name))
        spec = json.loads(archive.read("specification.json"))
        require(spec["spec_hash"] == report["spec_hash"], "Export hash differs")
        rows = list(csv.DictReader(io.StringIO(archive.read("report.csv").decode())))
        require(len(rows) == len(report["rows"]), "CSV row count differs")
        require("Synthetic demo data" in archive.read("report.html").decode(),
                "HTML lacks synthetic-data label")
    audit = request(client, "GET", base + "/audit", params=params)
    require(any(e["event_type"] == "report_rendered" for e in audit["events"]),
            "Missing rendering audit")
    request(client, "GET", base + "/report", status=403, params={
        "user_id": "DEMO-USER-FI" if user == "DEMO-USER-GLOBAL" else "DEMO-USER-GLOBAL",
    })
    # Reopen the same persisted DB through a new app, without another model call.
    from smart_librarian.api.app import create_app

    with TestClient(create_app(include_synthetic=True, runtime_db=runtime)) as resumed:
        request(resumed, "GET", base, params=params)
        asset = request(resumed, "GET", f"/api/assets/{report['registered_asset_id']}",
                        params={**params, "domain_id": case["domain"]})
        require(bool(asset["owner_id"]), "Persisted asset lacks owner")
        new_sid = request(resumed, "POST", "/api/sessions", json={
            "user_id": user, "domain_id": case["domain"],
        })["session_id"]
        reused = request(resumed, "POST", f"/api/sessions/{new_sid}/intent", json={
            "user_id": user, "intent": report["spec"]["intent"],
        })
        require(reused["outcome"] == "REUSE", "Persisted scope not reusable")
        replay = request(resumed, "GET",
                         f"/api/sessions/{new_sid}/report", params=params)
        require(replay["rows"] == report["rows"], "Reused report values differ")
    if proposal["approval_status"] == "pending":
        changed = {**case["confirmed_intent"], "grain": "day"}
        request(client, "POST", base + "/intent", json={"user_id": user, "intent": changed})
        request(client, "POST", base + "/approval", status=409, json=approval)
        request(client, "GET", base + "/report", status=409, params=params)
    return {"session_id": sid, "outcome": state["outcome"], "mode": "llm",
            "totals": report["totals"], "asset_id": report["registered_asset_id"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-provider-call", action="store_true")
    parser.add_argument("--case", action="append", choices=[c["case_id"] for c in CASES])
    parser.add_argument("--saved-intake-run", type=Path,
                        help="Replay frozen live intake; no new inference for selected cases")
    args = parser.parse_args()
    if not args.allow_provider_call:
        print("No provider call made: --allow-provider-call required.")
        return 2
    load_settings()
    provider = resolve_provider()
    require(provider.provider == "aitta" and provider.configured,
            "Configured Aitta token required; no other provider is allowed")
    output = ROOT / "artifacts/live_aitta" / ("e2e-" + uuid.uuid4().hex[:12])
    output.mkdir(parents=True)
    runtime = output / "runtime.sqlite"
    os.environ["RUNTIME_DB_PATH"] = str(runtime)
    from smart_librarian.api.app import create_app

    results = []
    cases = [case for case in CASES if not args.case or case["case_id"] in args.case]
    with TestClient(create_app(include_synthetic=True, runtime_db=runtime)) as client:
        for case in cases:
            directory = output / case["case_id"]
            directory.mkdir()
            try:
                saved = None
                if args.saved_intake_run:
                    require(case["case_id"] in ("reuse", "unsupported_metric"),
                            "Saved-intake replay supports only the two corrected checks")
                    saved = json.loads((args.saved_intake_run / case["case_id"]
                                        / "intake.json").read_text(encoding="utf-8"))
                result = run_case(client, case, directory, runtime, saved)
                results.append({"id": case["case_id"], "status": "pass", **result})
            except AssertionError as exc:
                results.append({"id": case["case_id"], "status": "fail", "detail": str(exc)})
                if "fallback" in str(exc) or "fell back" in str(exc):
                    break
            print(json.dumps(results[-1]), flush=True)
    summary = {"provider": provider.provider, "model": provider.model,
               "scope": "Eight synthetic paths, not a general accuracy benchmark",
               "intake_source": str(args.saved_intake_run) if args.saved_intake_run else "live",
               "results": results}
    (output / "results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Evidence: {output}")
    return 0 if len(results) == len(cases) and all(
        item["status"] == "pass" for item in results
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
