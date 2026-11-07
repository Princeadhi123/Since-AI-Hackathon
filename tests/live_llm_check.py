"""Opt-in real-provider smoke, not a benchmark or proof of general accuracy.

Run manually only after authorizing provider transmission and cost:
    PYTHONPATH=src python tests/live_llm_check.py --allow-provider-call
Never reads business facts; sends only these fictional requests and choices.
"""

import argparse
import json
import sys
from pathlib import Path

from smart_librarian.catalog.store import DemoCatalog
from smart_librarian.llm.client import OpenAIIntentExtractor
from smart_librarian.llm.providers import ProviderConfigurationError, resolve_provider
from smart_librarian.settings import load_settings
from smart_librarian.workflow.service import LLMUnavailable

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    {
        "id": "sales_paraphrase", "fixture": "demo_v1",
        "text": "Please chart monthly Net Sales for Nubeqa in Germany for Q1 2026.",
        "expected": {
            "product_ids": ["DEMO-P-NUB"], "market_ids": ["DE"],
            "metric_ids": ["DEMO-NET-SALES"],
            "months": ["2026-01-01", "2026-02-01", "2026-03-01"], "grain": "month",
        },
    },
    {
        "id": "logistics_paraphrase", "fixture": "demo_logistics_v1",
        "text": (
            "For the Cold Chain lane to Germany, give me monthly Delivered Orders, "
            "On Time Delivery %, and Average Lead Time, January through March 2026."
        ),
        "expected": {
            "product_ids": ["DEMO-L-COLD"], "market_ids": ["DE"],
            "metric_ids": ["DEMO-DELIVERED", "DEMO-ON-TIME-PCT", "DEMO-LEAD-DAYS"],
            "months": ["2026-01-01", "2026-02-01", "2026-03-01"], "grain": "month",
        },
    },
    {
        "id": "quality_paraphrase", "fixture": "demo_quality_v1",
        "text": (
            "Show monthly Inspected Units and Rejection Rate % for Tablet Line A "
            "in Finland in the first quarter (Q1) of 2026."
        ),
        "expected": {
            "product_ids": ["DEMO-Q-TAB"], "market_ids": ["FI"],
            "metric_ids": ["DEMO-INSPECTED", "DEMO-REJECT-PCT"],
            "months": ["2026-01-01", "2026-02-01", "2026-03-01"], "grain": "month",
        },
    },
    {
        "id": "ambiguous_sales_clarification", "fixture": "demo_v1",
        "text": "Show sales performance.",
        "must_be_empty": ["product_ids", "market_ids", "metric_ids", "months"],
    },
]


def assess(case, extraction):
    problems = []
    for key, expected in case.get("expected", {}).items():
        actual = extraction.get(key)
        if isinstance(expected, list):
            if not isinstance(actual, list) or sorted(actual) != sorted(expected):
                problems.append(key)
        elif actual != expected:
            problems.append(key)
    if "expected" in case:
        if extraction.get("unresolved"):
            problems.append("unexpected_unresolved")
        if extraction.get("unsupported"):
            problems.append("unexpected_unsupported")
    for key in case.get("must_be_empty", []):
        if extraction.get(key):
            problems.append("invented_" + key)
        if key not in (extraction.get("unresolved") or []):
            problems.append("missing_clarification_" + key)
    return problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-provider-call", action="store_true")
    args = parser.parse_args()
    if not args.allow_provider_call:
        print("No provider call made. Explicit --allow-provider-call is required.")
        return 2
    try:
        settings = load_settings()
        provider = resolve_provider()
    except ProviderConfigurationError as exc:
        print(f"NOT RUN: {exc} No provider call made.")
        return 2
    if not provider.configured:
        print(
            f"NOT RUN: {provider.credential_env} is not configured. "
            "No provider call made."
        )
        return 2
    extractor = OpenAIIntentExtractor(model=settings.llm_model)
    results = []
    for case in CASES:
        catalog = DemoCatalog(ROOT / "data" / case["fixture"])
        try:
            extraction = extractor.extract_intent([case["text"]], catalog.choices())
        except LLMUnavailable as exc:
            results.append({"id": case["id"], "status": "provider_unavailable",
                            "detail": str(exc)})
            # Avoid repeated calls on credential, billing, connectivity or SDK errors.
            break
        problems = assess(case, extraction)
        results.append({
            "id": case["id"], "status": "pass" if not problems else "fail",
            "problems": problems, "extraction": extraction,
        })
    print(json.dumps({
        "provider": provider.provider,
        "model": settings.llm_model, "synthetic_requests_only": True,
        "scope_note": "Four hand-authored smoke cases, not a general accuracy benchmark.",
        "results": results,
    }, indent=2))
    return 0 if len(results) == len(CASES) and all(
        result["status"] == "pass" for result in results
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
