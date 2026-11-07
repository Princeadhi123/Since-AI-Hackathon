"""Conservative offline extractor for the challenge builder pack.

Deterministic keyword/alias matching only - it resolves explicit product,
market and field names/IDs from the domain choices payload, plus explicit
calendar months for monthly/event grains. Snapshot sources have no time
dimension: any dated language there is unsupported. Missing scope always
becomes a clarification question; nothing is silently defaulted and no
extraction ever creates a plan.
"""

import re

from smart_librarian.domain.parser import _extract_months, _find_phrases


def _norm(value: str) -> str:
    return re.sub(r"[-_]+", " ", value.lower())

_LIMITATIONS = (
    "Offline extraction is keyword matching over explicit names and IDs, "
    "not general language understanding. Review the guided form; the "
    "confirmed form governs scope, not this text."
)

_QUESTIONS = {
    "product_ids": "Which product(s)? Name an explicit product or product ID.",
    "market_ids": "Which market(s)? Name an explicit market or market ID.",
    "metric_ids": "Which field(s) from this domain's source sheet?",
    "months": "Which month(s) with an explicit year (for example January 2026)?",
    "months_year": "Which year does that month range refer to?",
    "owner_id": "Which active accountable owner should own this report?",
}


def _product_aliases(choices: dict) -> dict[str, str]:
    aliases = {}
    for product in choices["products"]:
        aliases[_norm(product["product_id"])] = product["product_id"]
        aliases[_norm(product["product_name"])] = product["product_id"]
    return aliases


def _market_aliases(choices: dict) -> dict[str, str]:
    aliases = {}
    for market in choices["markets"]:
        aliases[_norm(market["market_id"])] = market["market_id"]
        aliases[_norm(market["market_name"])] = market["market_id"]
    return aliases


def _metric_aliases(choices: dict) -> dict[str, str]:
    aliases = {}
    for metric in choices["metrics"]:
        names = [metric["metric_id"], metric.get("name") or "",
                 *(metric.get("aliases") or [])]
        for name in names:
            if not name:
                continue
            aliases[_norm(name)] = metric["metric_id"]
            stripped = re.sub(
                r"^(monthly\s+|snapshot\s+)*synthetic\s+", "", name.lower()
            ).strip()
            if stripped and stripped != name.lower():
                aliases[_norm(stripped)] = metric["metric_id"]
    return aliases


def parse_challenge_message(text: str, domain_id: str, choices: dict) -> dict:
    lowered = text.lower()
    normalized = re.sub(r"[-_]+", " ", lowered)

    product_ids, normalized = _find_phrases(normalized, _product_aliases(choices))
    market_ids, normalized = _find_phrases(normalized, _market_aliases(choices))
    metric_ids, normalized = _find_phrases(normalized, _metric_aliases(choices))

    if re.search(r"\ball\s+(the\s+)?products\b", lowered):
        product_ids = [p["product_id"] for p in choices["products"]]
    if re.search(r"\ball\s+(the\s+)?markets\b", lowered):
        market_ids = [m["market_id"] for m in choices["markets"]]

    months, period_ambiguous, saw_period = _extract_months(
        lowered, choices.get("months") or []
    )
    if re.search(r"\ball demo months\b", lowered):
        years = set(re.findall(r"\b(?:19|20)\d{2}\b", lowered))
        coverage_years = {
            m[:4] for m in (choices.get("months") or [])
        }
        if years - coverage_years:
            months = []
            period_ambiguous = True

    grain = choices.get("grain")
    unsupported: list[str] = []
    if grain == "snapshot":
        if months or saw_period or period_ambiguous or re.search(
            r"\b(trend|over time|history|growth)\b", lowered
        ):
            unsupported.append(
                "This domain is a snapshot source with no time dimension; "
                "dated periods or trends cannot be satisfied."
            )
        months = []
    else:
        if period_ambiguous:
            unsupported.append(
                "The requested period is ambiguous; restate it with a "
                "single explicit year."
            )
        unknown_months = [
            m for m in months if m not in (choices.get("months") or [])
        ]
        if unknown_months:
            unsupported.append(
                "Months outside source coverage: " + ", ".join(unknown_months)
            )
            months = [m for m in months if m not in unknown_months]

    for word in ("weekly", "daily", "quarterly", "yearly", "annual"):
        if re.search(rf"\b{word}\b", lowered):
            unsupported.append(
                f"Requested '{word}' grain is not available; this source is "
                f"{grain} grain only."
            )

    unresolved: list[str] = []
    if not product_ids:
        unresolved.append("product_ids")
    if not market_ids:
        unresolved.append("market_ids")
    if not metric_ids:
        unresolved.append("metric_ids")
    if grain != "snapshot" and not months:
        unresolved.append("months")

    return {
        "domain_id": domain_id,
        "partial_intent": {
            "product_ids": product_ids,
            "market_ids": market_ids,
            "metric_ids": metric_ids,
            "months": months,
            "grain": grain,
        },
        "unresolved": sorted(set(unresolved)),
        "questions": [_QUESTIONS[f] for f in sorted(set(unresolved))],
        "unsupported": unsupported,
        "invalid_ids": [],
        "limitations": _LIMITATIONS,
    }
