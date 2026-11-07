"""Conservative offline intent parser.

Deterministic keyword/alias extraction over a fixed month vocabulary. This is
NOT general language understanding: anything it cannot resolve becomes a
clarification question or an explicit unsupported note, and the user always
confirms the extracted scope through the guided intent form.
"""

import calendar
import re

_MONTH_NAMES = {name.lower(): number for number, name in enumerate(calendar.month_name) if number}
_MONTH_NAMES.update(
    {name.lower(): number for number, name in enumerate(calendar.month_abbr) if number}
)

_LIMITATIONS = (
    "Limited offline keyword parser: it resolves catalog aliases and "
    "explicit calendar periods, but it may miss unfamiliar requirements. "
    "Always inspect the exact guided form before confirming - nothing "
    "parsed from chat executes until you confirm it."
)


def _product_aliases(choices: dict) -> dict[str, str]:
    aliases = {}
    for product in choices["products"]:
        aliases[product["product_name"].lower()] = product["product_id"]
        aliases[product["product_id"].lower()] = product["product_id"]
    return aliases


def _market_aliases(choices: dict) -> dict[str, str]:
    aliases = {}
    for market in choices["markets"]:
        aliases[market["market_name"].lower()] = market["market_id"]
        aliases[market["market_id"].lower()] = market["market_id"]
    return aliases


def _metric_aliases(catalog) -> tuple[dict[str, str], dict[str, str]]:
    supported = set(catalog.model().get("supported_metric_ids") or [])
    supported_aliases, unsupported_aliases = {}, {}
    for metric in catalog.metrics():
        target = supported_aliases if metric["metric_id"] in supported else unsupported_aliases
        for alias in [metric.get("name") or "", *(metric.get("aliases") or [])]:
            if alias:
                target[alias.lower()] = metric["metric_id"]
    return supported_aliases, unsupported_aliases


def _find_phrases(text: str, aliases: dict[str, str]) -> tuple[list[str], str]:
    found = []
    for alias, identifier in sorted(aliases.items(), key=lambda item: -len(item[0])):
        if re.search(rf"(?<![\w-]){re.escape(alias)}(?![\w-])", text):
            found.append(identifier)
            text = re.sub(rf"(?<![\w-]){re.escape(alias)}(?![\w-])", " ", text)
    return sorted(set(found)), text


def _extract_months(text: str, coverage_months: list[str]) -> tuple[list[str], bool, bool]:
    """Return (months, period_ambiguous, saw_period).

    Ranges expand only across an explicit through/to/dash connector; bare
    month lists select only the named months. An explicit single year is
    required - multiple or missing years make the period ambiguous, never
    silently resolved.
    """
    if re.search(r"\ball demo months\b", text):
        years = re.findall(r"\b(?:19|20)\d{2}\b", text)
        if not years or len(set(years)) == 1:
            return sorted(coverage_months), False, True

    years = re.findall(r"\b((?:19|20)\d{2})\b", text)
    quarter = re.search(r"\bq([1-4])\b", text)

    range_match = re.search(
        r"([a-zA-Z]+)\s*(?:through|thru|to|-)\s*([a-zA-Z]+)", text
    )
    month_numbers: list[int] = []
    if range_match and range_match.group(1).lower() in _MONTH_NAMES \
            and range_match.group(2).lower() in _MONTH_NAMES:
        lo = _MONTH_NAMES[range_match.group(1).lower()]
        hi = _MONTH_NAMES[range_match.group(2).lower()]
        if lo <= hi:
            month_numbers = list(range(lo, hi + 1))
    elif quarter:
        first = (int(quarter.group(1)) - 1) * 3 + 1
        month_numbers = [first, first + 1, first + 2]
    else:
        tokens = re.findall(r"[a-zA-Z]+", text)
        month_numbers = sorted({
            _MONTH_NAMES[token.lower()]
            for token in tokens
            if token.lower() in _MONTH_NAMES
        })

    saw_period = bool(month_numbers)
    if not saw_period:
        return [], False, bool(years)
    if len(set(years)) != 1:
        # Missing or multiple distinct years: the period cannot be resolved.
        return [], True, bool(years)
    year = int(years[0])
    return (
        sorted({f"{year:04d}-{number:02d}-01" for number in month_numbers}),
        False,
        True,
    )


def parse_message(text: str, choices: dict, catalog) -> dict:
    lowered = text.lower()
    normalized = re.sub(r"[-_]+", " ", lowered)

    product_ids, normalized = _find_phrases(normalized, _product_aliases(choices))
    market_ids, normalized = _find_phrases(normalized, _market_aliases(choices))
    metric_supported, metric_unsupported_names = _metric_aliases(catalog)
    metric_ids, normalized = _find_phrases(normalized, metric_supported)
    unsupported_metric_ids, normalized = _find_phrases(normalized, metric_unsupported_names)

    unsupported = []
    for metric_id in unsupported_metric_ids:
        metric = catalog.metric(metric_id) or {}
        reason = metric.get("unsupported_reason") or "metric not supported"
        unsupported.append(f"{metric.get('name', metric_id)}: {reason}")

    months, period_ambiguous, _saw_year = _extract_months(
        lowered, choices.get("months") or []
    )
    unresolved: list[str] = []
    invalidated: list[str] = []
    if period_ambiguous:
        # An explicitly stated but unresolvable period replaces any earlier
        # selection - the user must restate it.
        unresolved.append("months")
        invalidated.append("months")

    grain = None
    if re.search(r"\b(monthly|month|months|per month|each month)\b", lowered):
        grain = "month"
    grain_unsupported = False
    for word, label in (("weekly", "weekly grain"), ("daily", "daily grain")):
        if re.search(rf"\b{word}\b", lowered):
            unsupported.append(f"Requested {label} is not supported by the model.")
            grain_unsupported = True
    if re.search(r"\b(gross\s+)?(margin|profit(ability)?)\b", lowered):
        unsupported.append("Margin/profit metrics are not supported by the model.")

    grain_options = choices.get("grain_options") or []
    if grain is None and not grain_unsupported and len(grain_options) == 1:
        # The model supports exactly one grain; propose it for confirmation.
        grain = grain_options[0]

    # Ambiguous bare "sales"/"performance" language with no resolved metric
    # invalidates any earlier metric selection rather than merging with it.
    if not metric_ids and not unsupported_metric_ids:
        if re.search(r"\b(sales|performance|revenue|forecast|variance)\b", normalized):
            unresolved.append("metric_ids")
            invalidated.append("metric_ids")

    if not product_ids:
        unresolved.append("product_ids")
    if not market_ids:
        unresolved.append("market_ids")
    if not metric_ids:
        unresolved.append("metric_ids")
    if not months and "months" not in unresolved:
        unresolved.append("months")

    return {
        "product_ids": product_ids,
        "market_ids": market_ids,
        "metric_ids": metric_ids,
        "months": months,
        "grain": grain,
        "unresolved": sorted(set(unresolved)),
        "invalidated": sorted(set(invalidated)),
        "unsupported": unsupported,
        "limitations": _LIMITATIONS,
        "mode": "offline",
    }


def merge_partial(partial: dict, extraction: dict) -> dict:
    """Merge a new extraction into the retained partial intent."""
    merged = dict(partial) if partial else {}
    for field in ("product_ids", "market_ids", "metric_ids", "months"):
        if extraction.get(field):
            merged[field] = extraction[field]
    if extraction.get("grain"):
        merged["grain"] = extraction["grain"]
    return merged


def missing_fields(partial: dict) -> list[str]:
    missing = [field for field in ("product_ids", "market_ids", "metric_ids", "months") if not partial.get(field)]
    if not partial.get("grain"):
        missing.append("grain")
    return sorted(missing)


_FIELD_QUESTIONS = {
    "product_ids": "Which product(s)? Choose from the catalog list.",
    "market_ids": "Which market(s)? Your identity may limit available markets.",
    "metric_ids": "Which measure(s)? For example Net Sales or Sales Forecast.",
    "months": "Which month period, with an explicit year (for example January through March 2026)?",
    "grain": "Which grain? This model supports monthly only.",
    "months_year": "Which year does that month range refer to?",
}

_ANNUAL_FIELD_QUESTIONS = {
    "product_ids": "Which product(s)? Choose the published product list.",
    "market_ids": "Only global reported sales are available. Confirm Global or revise your request.",
    "metric_ids": "Choose Reported Sales; forecasts and other metrics are unavailable.",
    "months": "Which fiscal year(s): 2024 and/or 2025?",
    "grain": "This source supports annual fiscal-year reporting only.",
    "months_year": "Which fiscal year does that range refer to?",
}


def questions_for(unresolved: list[str], grain: str = "month") -> list[str]:
    mapping = _ANNUAL_FIELD_QUESTIONS if grain == "year" else _FIELD_QUESTIONS
    return [mapping.get(field, f"Clarify {field}.") for field in unresolved]
