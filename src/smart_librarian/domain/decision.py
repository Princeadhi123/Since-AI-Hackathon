"""Deterministic decision engine.

Evaluates a confirmed intent against the demo catalog contract. Produces one
of: ACCESS_DENIED, NEEDS_REVIEW, REUSE, PROPOSE_CHANGE, PROPOSE_BUILD.
No numeric scoring, no LLM policy, no silently adjusted scope.
"""

import calendar
import hashlib
import json
import uuid

from smart_librarian.domain.executable_contract import calculation_contract_gaps

APPROVAL_ENDORSEMENTS = {"certified", "promoted"}
SPEC_VERSION = "1.0.0"
SUPPORTED_VISUALS = ["line", "totals", "table"]
CATALOG_MODELS_REF = "catalog.json#/models"
CATALOG_REPORTS_REF = "catalog.json#/reports"
SNAPSHOT_STATUS = "simulated snapshot as of 2026-11-06"


def _sorted_unique(values) -> list[str]:
    return sorted(set(values or []))


def _valid_month_start(value: str) -> bool:
    try:
        year, month, day = map(int, value.split("-"))
        calendar.monthrange(year, month)
        return day == 1 and value == f"{year:04d}-{month:02d}-01"
    except (TypeError, ValueError, AttributeError):
        return False


def canonical_intent(intent: dict) -> dict:
    return {
        "product_ids": _sorted_unique(intent.get("product_ids")),
        "market_ids": _sorted_unique(intent.get("market_ids")),
        "metric_ids": _sorted_unique(intent.get("metric_ids")),
        "months": _sorted_unique(intent.get("months")),
        "grain": intent.get("grain"),
    }


def spec_hash(spec: dict) -> str:
    payload = json.dumps(spec, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def asset_identity(spec: dict) -> tuple[str, str]:
    """Deterministic asset identity for a rendered report.

    Binds the canonical intent, dataset fingerprint and model only - not the
    user, proposal id or spec hash - so the same approved scope rendered by
    any session resolves to the same asset.
    """
    payload = json.dumps(
        {
            "intent": canonical_intent(spec.get("intent") or {}),
            "dataset_fingerprint": spec.get("dataset_fingerprint"),
            "model_id": spec.get("model_id"),
        },
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    identity_key = hashlib.sha256(payload).hexdigest()
    return f"GEN-{identity_key[:16].upper()}", identity_key


def _evidence(catalog, model, candidate, metrics) -> list[dict]:
    if model.get("model_id") == "PUBLIC-MODEL-FINANCIALS":
        from smart_librarian.domain.public_financials import (
            financial_evidence_items,
        )
        return financial_evidence_items(catalog, model, candidate, metrics)
    if model.get("model_id") == "PUBLIC-MODEL-ANNUAL":
        from smart_librarian.domain.public_annual import (
            public_evidence_items,
        )
        return public_evidence_items(catalog, model, candidate, metrics)
    items = []

    def add(kind, ref_path, record_id, detail, status):
        items.append(
            {
                "evidence_id": f"EV-{len(items) + 1:02d}",
                "kind": kind,
                "ref_path": ref_path,
                "record_id": record_id,
                "detail": detail,
                "status": status,
            }
        )

    add(
        "model_endorsement",
        CATALOG_MODELS_REF,
        model.get("model_id"),
        f"Model '{model.get('name')}' endorsement: {model.get('endorsement')} "
        f"(contract {model.get('contract_version')}).",
        SNAPSHOT_STATUS,
    )
    owner = catalog.owner(model.get("owner_id")) or {}
    add(
        "owner",
        "catalog.json#/owners",
        owner.get("owner_id"),
        f"Owner '{owner.get('name')}' status: {owner.get('status')}.",
        SNAPSHOT_STATUS,
    )
    add(
        "refresh",
        CATALOG_MODELS_REF,
        model.get("model_id"),
        f"Refresh status '{model.get('refresh_status')}', snapshot as of "
        f"{model.get('snapshot_as_of')} (simulated, not live freshness).",
        SNAPSHOT_STATUS,
    )
    for metric in metrics:
        add(
            "metric",
            "catalog.json#/metrics",
            metric.get("metric_id"),
            f"Metric '{metric.get('name')}' approval_status: "
            f"{metric.get('approval_status')}, unit: {metric.get('unit')}.",
            SNAPSHOT_STATUS,
        )
    add(
        "coverage",
        CATALOG_MODELS_REF,
        model.get("model_id"),
        "Requested products, markets and months are inside model coverage; "
        "grain 'month' is supported.",
        SNAPSHOT_STATUS,
    )
    if candidate is not None:
        generated = candidate.get("origin") == "generated"
        registry_ref = (
            "runtime.sqlite#/generated_reports" if generated
            else CATALOG_REPORTS_REF
        )
        add(
            "candidate_report",
            registry_ref,
            candidate.get("asset_id"),
            f"Candidate report '{candidate.get('name')}' covers the requested "
            f"scope; endorsement {candidate.get('endorsement')}, status "
            f"{candidate.get('lifecycle_status')}; model lineage recorded.",
            SNAPSHOT_STATUS,
        )
        add(
            "lineage",
            registry_ref if generated else "catalog.json#/lineage",
            f"{model.get('model_id')}->{candidate.get('asset_id')}",
            "model_to_report lineage links the candidate to the model.",
            SNAPSHOT_STATUS,
        )
        if generated:
            add(
                "destination",
                registry_ref,
                candidate.get("asset_id"),
                "Generated asset lives in the local runtime registry and is "
                "reachable via its /api/assets/{asset_id} route; there is no "
                "Power BI publish or external deployment.",
                SNAPSHOT_STATUS,
            )
            return items
    add(
        "destination",
        CATALOG_REPORTS_REF,
        (candidate or {}).get("asset_id"),
        "The catalog destination has no deployed URL or BI export; this "
        "application provides a local preview only.",
        SNAPSHOT_STATUS,
    )
    return items


def _shape_gaps(intent: dict) -> list[str]:
    """Empty or duplicated selection lists."""
    reasons = []
    for field in ("product_ids", "market_ids", "metric_ids", "months"):
        values = intent.get(field)
        if not values:
            reasons.append(f"empty_{field}")
        elif len(set(values)) != len(values):
            reasons.append(f"duplicate_{field}")
    return reasons


def _month_gaps(coverage_months, months) -> list[str]:
    reasons = []
    for month in months:
        if not _valid_month_start(month):
            reasons.append("invalid_month")
        elif month not in coverage_months:
            reasons.append("month_out_of_coverage")
    return reasons


def _scope_gaps(model: dict, intent: dict) -> list[str]:
    """Grain plus product/market/month coverage checks."""
    if model.get("model_id") == "PUBLIC-MODEL-FINANCIALS":
        from smart_librarian.domain.public_financials import (
            financial_scope_gaps,
        )
        return financial_scope_gaps(model, intent)
    if model.get("model_id") == "PUBLIC-MODEL-ANNUAL":
        from smart_librarian.domain.public_annual import public_scope_gaps
        return public_scope_gaps(model, intent)
    reasons = []
    coverage = model.get("coverage") or {}
    supported_grains = model.get("supported_grains") or []
    if intent.get("grain") not in supported_grains:
        reasons.append("unsupported_grain")

    reasons.extend(_month_gaps(coverage.get("months") or [], intent["months"]))
    for field, reason in (
        ("product_ids", "unknown_product_id"),
        ("market_ids", "unknown_market_id"),
    ):
        for value in intent[field]:
            if value not in (coverage.get(field) or []):
                reasons.append(reason)
    return reasons


def _metric_gaps(catalog, model: dict, intent: dict) -> list[str]:
    """Unknown, unapproved or model-unsupported metrics."""
    reasons = []
    supported_metrics = set(model.get("supported_metric_ids") or [])
    for metric_id in intent["metric_ids"]:
        metric = catalog.metric(metric_id)
        if metric is None:
            reasons.append("unknown_metric_id")
            continue
        if metric.get("approval_status") != "approved":
            reasons.append("metric_not_approved")
        if metric_id not in supported_metrics:
            reasons.append("metric_not_supported")
    return reasons


def _model_gaps(catalog, model: dict) -> list[str]:
    """Model trust evidence plus the fixed-execution contract."""
    reasons = []
    coverage = model.get("coverage") or {}
    if model.get("endorsement") not in APPROVAL_ENDORSEMENTS:
        reasons.append("model_not_endorsed")
    owner = catalog.owner(model.get("owner_id"))
    if not owner or owner.get("status") != "active":
        reasons.append("owner_not_active")
    if model.get("refresh_status") != "healthy":
        reasons.append("refresh_not_healthy")
    if not coverage.get("months") or not coverage.get("product_ids"):
        reasons.append("coverage_evidence_missing")
    if not model.get("schema") or not model.get("grain"):
        reasons.append("schema_evidence_missing")
    reasons.extend(calculation_contract_gaps(catalog))
    return reasons


def _gaps(catalog, model, intent) -> list[str]:
    """Return NEEDS_REVIEW reasons for scope/shape problems (post-access)."""
    shape = _shape_gaps(intent)
    if shape:
        return shape
    reasons = (
        _scope_gaps(model, intent)
        + _metric_gaps(catalog, model, intent)
        + _model_gaps(catalog, model)
    )
    return sorted(set(reasons))


def _full_scope(report: dict, intent: dict) -> bool:
    coverage = report.get("coverage") or {}
    return (
        set(intent["product_ids"]).issubset(coverage.get("product_ids") or [])
        and set(intent["market_ids"]).issubset(coverage.get("market_ids") or [])
        and set(intent["months"]).issubset(coverage.get("months") or [])
        and report.get("grain") == intent.get("grain")
    )


def _candidates(catalog, model, intent, user) -> list[dict]:
    # Only reports fully visible to this user may surface as candidates;
    # a generated report spanning markets the requester cannot see must not
    # leak through candidate evidence.
    allowed = set(user.get("allowed_market_ids") or [])
    candidates = []
    for report in catalog.reports():
        coverage = report.get("coverage") or {}
        if not set(coverage.get("market_ids") or []).issubset(allowed):
            continue
        if not _full_scope(report, intent):
            continue
        if report.get("lifecycle_status") != "active":
            continue
        if report.get("endorsement") not in APPROVAL_ENDORSEMENTS:
            continue
        owner = catalog.owner(report.get("owner_id"))
        if not owner or owner.get("status") != "active":
            continue
        if report.get("model_id") != model.get("model_id"):
            continue
        if not catalog.has_model_lineage(report["asset_id"], model["model_id"]):
            continue
        candidates.append(report)
    return sorted(candidates, key=lambda item: item["asset_id"])


def evaluate(catalog, user: dict, intent: dict, fingerprint: str,
             domain_id: str = "sales") -> dict:
    """Evaluate a confirmed intent. Never returns business values."""
    allowed = set(user.get("allowed_market_ids") or [])
    requested_markets = _sorted_unique(intent.get("market_ids"))
    if not requested_markets or not set(requested_markets).issubset(allowed):
        return {
            "outcome": "ACCESS_DENIED",
            "reasons": ["market_not_permitted"],
            "evidence": [],
            "proposal": None,
            "candidate_explanations": [],
        }

    model = catalog.model()
    reasons = _gaps(catalog, model, intent)
    if reasons:
        return {
            "outcome": "NEEDS_REVIEW",
            "reasons": reasons,
            "evidence": [],
            "proposal": None,
            "candidate_explanations": [],
        }

    intent = canonical_intent(intent)
    requested_metrics = set(intent["metric_ids"])
    exact_matches, extension_candidates = [], []
    for report in _candidates(catalog, model, intent, user):
        if requested_metrics.issubset(report.get("metric_ids") or []):
            exact_matches.append(report)
        else:
            extension_candidates.append(report)

    explanations: list[str] = []
    if exact_matches:
        candidate = exact_matches[0]
        outcome, approval_status = "REUSE", "not_required"
        source_asset_id = candidate["asset_id"]
        explanations = [
            f"Exact match {item['asset_id']} also covers all requested "
            "metrics and scope; first asset_id selected by deterministic "
            "tie-break."
            for item in exact_matches[1:]
        ]
    elif extension_candidates:
        candidate = extension_candidates[0]
        outcome, approval_status = "PROPOSE_CHANGE", "pending"
        source_asset_id = candidate["asset_id"]
        explanations = [
            f"Extension candidate {item['asset_id']} covers the scope but "
            "not all requested metrics; first asset_id selected by "
            "deterministic tie-break."
            for item in extension_candidates[1:]
        ]
    else:
        candidate = None
        outcome, approval_status = "PROPOSE_BUILD", "pending"
        source_asset_id = None
    metrics = [catalog.metric(mid) for mid in intent["metric_ids"]]

    evidence = _evidence(catalog, model, candidate, metrics)
    spec = {
        "spec_version": SPEC_VERSION,
        "user_id": user["user_id"],
        "domain_id": domain_id,
        "dataset_id": catalog.dataset_id,
        "model_id": model.get("model_id"),
        "contract_version": model.get("contract_version"),
        "dataset_fingerprint": fingerprint,
        "intent": intent,
        "requested_metrics": [
            {"metric_id": m["metric_id"], "name": m.get("name"), "unit": m.get("unit")}
            for m in metrics
        ],
        "supported_visuals": list(SUPPORTED_VISUALS),
        "source_asset_id": source_asset_id,
        "evidence_ids": [item["evidence_id"] for item in evidence],
        "synthetic_record": True,
        "snapshot_as_of": model.get("snapshot_as_of"),
        "status_note": (
            "Simulated snapshot as of 2026-11-06; not freshly retrieved live data."
        ),
    }
    if model.get("model_id") == "PUBLIC-MODEL-FINANCIALS":
        from smart_librarian.domain.public_financials import (
            financial_spec_metadata,
        )
        spec.update(financial_spec_metadata(catalog))
    elif model.get("model_id") == "PUBLIC-MODEL-ANNUAL":
        from smart_librarian.domain.public_annual import (
            public_spec_metadata,
        )
        spec.update(public_spec_metadata(catalog))
    proposal = {
        "proposal_id": str(uuid.uuid4()),
        "spec": spec,
        "spec_hash": spec_hash(spec),
        "approval_status": approval_status,
    }
    return {
        "outcome": outcome,
        "reasons": [],
        "evidence": evidence,
        "proposal": proposal,
        "candidate_explanations": explanations,
    }
