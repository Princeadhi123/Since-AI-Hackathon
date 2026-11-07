import copy
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

from smart_librarian.catalog.store import CatalogError, SnapshotDrift
from smart_librarian.settings import REPO_ROOT


WORKBOOK = REPO_ROOT / "data" / "Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx"
DISCLAIMER = (
    "Official SinceAI synthetic builder pack, not actual Bayer performance. "
    "Reports preserve source rows and native units without aggregation. "
    "Estate decisions are review proposals, not executed migration or retirement."
)
CONTRACTS = {
    "commercial": {
        "name": "Commercial / Finance",
        "sheet": "Product_Market_Monthly",
        "time_column": "month",
        "grain": "month",
        "fields": {
            "net_sales_m_eur_syn": ("Synthetic net sales", "million EUR", "KPI-001"),
            "forecast_m_eur_syn": ("Synthetic sales forecast", "million EUR", None),
            "forecast_variance_pct": ("Published synthetic forecast variance", "%", None),
            "units_shipped_syn": ("Synthetic units shipped", "units", "KPI-014"),
            "market_access_coverage_pct_syn": ("Monthly synthetic market-access coverage", "%", "KPI-027"),
            "otif_pct_syn": ("Monthly synthetic on-time in-full", "%", "KPI-020"),
            "inventory_weeks_syn": ("Monthly synthetic inventory", "weeks", "KPI-016"),
        },
    },
    "market_access": {
        "name": "Market access",
        "sheet": "Market_Access",
        "time_column": None,
        "grain": "snapshot",
        "fields": {
            "reimbursement_status": ("Reimbursement status", "category", None),
            "coverage_model": ("Coverage model", "category", None),
            "coverage_pct_syn": ("Snapshot synthetic coverage", "%", "KPI-027"),
            "trend_status": ("Trend status", "category", None),
            "analytics_priority": ("Analytics priority", "category", None),
        },
    },
    "supply": {
        "name": "Supply / Logistics",
        "sheet": "Supply_Operations",
        "time_column": None,
        "grain": "snapshot",
        "fields": {
            "supply_source": ("Supply source", "category", None),
            "primary_mode": ("Transport mode", "category", None),
            "otif_pct_syn": ("Snapshot synthetic on-time in-full", "%", "KPI-020"),
            "inventory_weeks_syn": ("Snapshot synthetic inventory", "weeks", "KPI-016"),
            "forecast_accuracy_pct_syn": ("Snapshot synthetic forecast accuracy", "%", "KPI-006"),
            "risk_status": ("Supply risk status", "category", None),
        },
    },
    "launch": {
        "name": "Launch planning",
        "sheet": "Launch_Milestones",
        "time_column": "milestone_date",
        "grain": "event",
        "fields": {
            "milestone_id": ("Milestone ID", "identifier", None),
            "milestone_type": ("Milestone type", "category", None),
            "status": ("Milestone status", "category", None),
            "business_impact": ("Business impact", "category", None),
        },
    },
}


def stable_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


class ChallengeData:
    def __init__(self, path=WORKBOOK):
        self.path = Path(path)
        self.fingerprint = self._digest()
        self.tables = {}
        workbook = load_workbook(self.path, read_only=True, data_only=False)
        try:
            for sheet in workbook:
                if sheet.title in {"START_HERE", "Package_Overview"}:
                    continue
                rows = iter(sheet.values)
                headers = next(rows)
                if not all(isinstance(h, str) and h for h in headers):
                    raise CatalogError(f"Invalid builder-pack headers: {sheet.title}")
                if len(set(headers)) != len(headers) or "_source_row" in headers:
                    raise CatalogError(f"Duplicate/reserved headers: {sheet.title}")
                records = []
                for number, values in enumerate(rows, 2):
                    if not any(v is not None for v in values):
                        continue
                    if len(values) != len(headers):
                        raise CatalogError(f"Invalid builder-pack row: {sheet.title}:{number}")
                    record = {"_source_row": number}
                    for key, value in zip(headers, values, strict=True):
                        if isinstance(value, str) and value.startswith("="):
                            raise CatalogError(f"Formula requires reviewed values: {sheet.title}:{number}")
                        record[key] = value.isoformat() if isinstance(value, (date, datetime)) else value
                    records.append(record)
                self.tables[sheet.title] = records
        finally:
            workbook.close()
        for contract in CONTRACTS.values():
            if not self.tables.get(contract["sheet"]):
                raise CatalogError(f"Missing source table: {contract['sheet']}")
        self.assert_current()

    def _digest(self):
        try:
            return hashlib.sha256(self.path.read_bytes()).hexdigest()
        except OSError as exc:
            raise CatalogError("Official builder workbook is unavailable") from exc

    def assert_current(self):
        if self._digest() != self.fingerprint:
            raise SnapshotDrift("Builder pack changed; restart to load a coherent snapshot")

    def provenance(self):
        return {
            "source_file": self.path.name,
            "source_sha256": self.fingerprint,
            "data_classification": "official_synthetic_challenge",
            "disclaimer": DISCLAIMER,
        }

    def choices(self, domain):
        self.assert_current()
        if domain not in CONTRACTS:
            raise ValueError("Unknown builder-pack domain")
        contract = CONTRACTS[domain]
        rows = self.tables[contract["sheet"]]
        column = contract["time_column"]
        months = sorted({r[column][:7] + "-01" for r in rows}) if column else []
        return {
            **self.provenance(),
            "domain_id": domain,
            "products": copy.deepcopy(self.tables["Products"]),
            "markets": copy.deepcopy(self.tables["Markets"]),
            "owners": [copy.deepcopy(r) for r in self.tables["Owners"] if r.get("status") == "active"],
            "metrics": [
                {"metric_id": field, "name": info[0], "unit": info[1],
                 "context_kpi_id": info[2], "aliases": [field.replace("_syn", "").replace("_", " ")]}
                for field, info in contract["fields"].items()
            ],
            "model": {
                "model_id": "CHALLENGE-" + domain.upper(),
                "supported_grains": [contract["grain"]],
                "coverage": {"months": months},
            },
            "months": months,
            "grain": contract["grain"],
            "source_sheet": contract["sheet"],
        }

    def report_spec(self, domain, intent, owner_id):
        choices = self.choices(domain)
        contract = CONTRACTS[domain]
        normalized = {}
        for key, allowed in (
            ("product_ids", {r["product_id"] for r in choices["products"]}),
            ("market_ids", {r["market_id"] for r in choices["markets"]}),
            ("metric_ids", set(contract["fields"])),
        ):
            values = intent.get(key)
            if not isinstance(values, list) or not values or not all(isinstance(v, str) for v in values):
                raise ValueError(f"Explicit {key} are required")
            if not set(values).issubset(allowed):
                raise ValueError(f"Unsupported {key}")
            normalized[key] = sorted(set(values))
        if owner_id not in {r["owner_id"] for r in choices["owners"]}:
            raise ValueError("A named active builder-pack owner is required")
        if intent.get("grain") != contract["grain"]:
            raise ValueError("Unsupported grain; snapshot and event data cannot become monthly totals")
        months = intent.get("months") or []
        if not isinstance(months, list) or not all(isinstance(v, str) for v in months):
            raise ValueError("Invalid period selection")
        if contract["time_column"]:
            if not months or not set(months).issubset(set(choices["months"])):
                raise ValueError("Explicit available months are required")
        elif months:
            raise ValueError("Snapshot sources do not provide dated periods")
        normalized.update(months=sorted(set(months)), grain=contract["grain"])
        rows = self._selected_rows(domain, normalized)
        if not rows:
            raise ValueError("No source rows match the exact confirmed scope")
        if domain != "launch":
            expected = {
                (p, m, month)
                for p in normalized["product_ids"] for m in normalized["market_ids"]
                for month in (normalized["months"] or [None])
            }
            actual = [(r["product_id"], r["market_id"],
                       r["month"][:7] + "-01" if domain == "commercial" else None) for r in rows]
            if set(actual) != expected or len(actual) != len(set(actual)):
                raise ValueError("Incomplete or duplicate product/market/period source coverage")
        return {
            **self.provenance(), "kind": "report", "domain_id": domain,
            "intent": normalized, "owner_id": owner_id, "source_sheet": contract["sheet"],
            "fields": [r for r in choices["metrics"] if r["metric_id"] in normalized["metric_ids"]],
            "aggregation": "none",
            "semantic_note": (
                "KPI IDs are contextual references, not certified executable model bindings. "
                "Native workbook units are preserved (sales in million EUR, not KPI catalog EUR). "
                "Snapshot and monthly sources are distinct and are never joined or averaged. "
                "value_type is preserved; forecast-like rows are not actual performance."
            ),
        }

    def _selected_rows(self, domain, intent):
        contract = CONTRACTS[domain]
        column = contract["time_column"]
        return [
            r for r in self.tables[contract["sheet"]]
            if r["product_id"] in intent["product_ids"] and r["market_id"] in intent["market_ids"]
            and (not column or r[column][:7] + "-01" in intent["months"])
        ]

    def render(self, spec):
        self.assert_current()
        if spec.get("source_sha256") != self.fingerprint:
            raise SnapshotDrift("Report specification belongs to a different builder pack")
        domain = spec["domain_id"]
        checked = self.report_spec(domain, spec["intent"], spec["owner_id"])
        if checked != spec:
            raise ValueError("Specification differs from the executable source contract")
        contract = CONTRACTS[domain]
        products = {r["product_id"]: r["product_name"] for r in self.tables["Products"]}
        markets = {r["market_id"]: r["market_name"] for r in self.tables["Markets"]}
        fields = ["product_id", "market_id", *spec["intent"]["metric_ids"]]
        fields += [f for f in (contract["time_column"], "value_type", "synthetic_record") if f]
        rows = []
        for row in self._selected_rows(domain, spec["intent"]):
            rows.append({
                **{f: row[f] for f in dict.fromkeys(fields) if f in row},
                "product_name": products[row["product_id"]],
                "market_name": markets[row["market_id"]],
                "_source_sheet": contract["sheet"], "_source_row": row["_source_row"],
            })
        self.assert_current()
        return {"spec": copy.deepcopy(spec), "spec_hash": stable_hash(spec), "rows": rows,
                "units": {r["metric_id"]: r["unit"] for r in spec["fields"]},
                "source_provenance": self.provenance(), "totals": {},
                "quality_checks": [
                    "Exact confirmed scope", "Complete non-event coverage",
                    "Source-row-identical values", "No cross-source joins or aggregation",
                    "Fingerprint-bound specification", "Native units and value_type preserved",
                ]}

    def estate_asset(self, asset_id):
        self.assert_current()
        tables = self.tables
        assets = {r["asset_id"]: r for r in tables["Analytics_Assets"]}
        if asset_id not in assets:
            raise ValueError("Unknown estate asset")
        asset = assets[asset_id]
        model = next((r for r in tables["Semantic_Models"] if r["model_id"] == asset.get("model_id")), None)
        owner = next((r for r in tables["Owners"] if r["owner_id"] == asset.get("owner_id")), None)
        mappings = [r for r in tables["Asset_KPI_Map"] if r["asset_id"] == asset_id]
        kpi_ids = {r["kpi_id"] for r in mappings}
        kpis = [r for r in tables["KPI_Catalog"] if r["kpi_id"] in kpi_ids]
        usage = [r for r in tables["Asset_Usage"] if r["asset_id"] == asset_id]
        lineage = [r for r in tables["Lineage_Edges"] if asset_id in (r.get("source_id"), r.get("target_id"))]
        downstream = set()
        frontier = [asset_id]
        while frontier:
            current = frontier.pop()
            for edge in tables["Lineage_Edges"]:
                target = edge.get("target_id")
                if edge.get("source_id") == current and target and target != asset_id and target not in downstream:
                    downstream.add(target)
                    frontier.append(target)
        signals = [r for r in tables["Governance_Signals"] if r["asset_id"] == asset_id]
        related_ids = {asset_id, asset.get("model_id"), asset.get("owner_id"), *kpi_ids}
        quality = [r for r in tables["Data_Quality"] if r.get("record_id") in related_ids]
        gaps = []
        if not owner or owner.get("status") != "active":
            gaps.append("missing_or_inactive_owner")
        if not model:
            gaps.append("missing_semantic_model")
        elif model.get("refresh_status") != "healthy":
            gaps.append("model_refresh_not_healthy")
        if model and (model.get("ai_readiness") != "good" or model.get("ai_issue_pattern") != "clear"):
            gaps.append("model_semantics_need_review")
        if not kpi_ids or len(kpis) != len(kpi_ids):
            gaps.append("missing_kpi_mapping")
        if any(r.get("approval_status") != "approved" or r.get("definition_status") != "canonical" for r in kpis):
            gaps.append("noncanonical_or_unapproved_kpi")
        if not any(r.get("source_id") == asset.get("model_id") and r.get("target_id") == asset_id for r in lineage):
            gaps.append("missing_model_lineage")
        if asset.get("endorsement") not in ("certified", "promoted"):
            gaps.append("asset_not_endorsed")
        if model and model.get("endorsement") not in ("certified", "promoted"):
            gaps.append("model_not_endorsed")
        if asset.get("lifecycle_status") != "active":
            gaps.append("asset_not_active")
        if any(r.get("status") != "resolved" for r in signals):
            gaps.append("unresolved_governance_signals")
        if quality:
            gaps.append("source_data_quality_findings")
        exact_candidates = []
        consolidation_candidates = []
        canonical = {r["kpi_id"]: r.get("canonical_metric") for r in tables["KPI_Catalog"]}
        canonical_metrics = {canonical.get(k) for k in kpi_ids} - {None, ""}
        for other in tables["Analytics_Assets"]:
            if other["asset_id"] == asset_id:
                continue
            other_kpis = {r["kpi_id"] for r in tables["Asset_KPI_Map"] if r["asset_id"] == other["asset_id"]}
            if (kpi_ids and other_kpis == kpi_ids
                    and all(other.get(k) == asset.get(k) for k in ("product_scope", "market_scope", "model_id"))):
                exact_candidates.append(other["asset_id"])
            shared = canonical_metrics & ({canonical.get(k) for k in other_kpis} - {None, ""})
            if shared and all(other.get(k) == asset.get(k) for k in ("product_scope", "market_scope")):
                consolidation_candidates.append({
                    "asset_id": other["asset_id"],
                    "shared_canonical_metrics": sorted(shared),
                    "model_id": other.get("model_id"),
                    "equivalence": "not_verified",
                    "required_review": "Reconcile KPI variants, filters, visuals, model and lineage before replacement",
                })
        return {
            **self.provenance(), "asset": copy.deepcopy(asset), "model": copy.deepcopy(model),
            "owner": copy.deepcopy(owner), "kpis": copy.deepcopy(kpis),
            "usage": copy.deepcopy(usage), "lineage": copy.deepcopy(lineage),
            "downstream_ids": sorted(downstream), "signals": copy.deepcopy(signals),
            "data_quality": copy.deepcopy(quality), "governance_gaps": gaps,
            "exact_metadata_candidates": sorted(exact_candidates),
            "consolidation_candidates": sorted(consolidation_candidates, key=lambda r: r["asset_id"]),
            "migration_inputs": copy.deepcopy([r for r in tables["Migration_Backlog"] if r["source_asset_id"] == asset_id]),
            "decision": "REPAIR_REVIEW" if gaps else "REUSE_CANDIDATE",
            "decision_note": (
                "No weighted score or guessed savings. Exact metadata candidates match model, "
                "product, market and KPI IDs only; consolidation candidates share product/market "
                "and at least one canonical metric label, not necessarily its definition. "
                "Neither kind establishes visual/filter or executable equivalence. "
                "Usage rows retain monthly unique users; these are not summed into distinct users."
            ),
        }

    def lifecycle_spec(self, asset_id, action, owner_id, rationale, target_asset_id=None):
        if action not in {"reuse", "repair", "consolidate", "retire", "migrate"}:
            raise ValueError("Unsupported lifecycle action")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("An explicit human rationale is required")
        evidence = self.estate_asset(asset_id)
        active_owners = {r["owner_id"] for r in self.tables["Owners"] if r.get("status") == "active"}
        if owner_id not in active_owners:
            raise ValueError("An active accountable owner is required")
        if action == "reuse" and evidence["governance_gaps"]:
            raise ValueError("Reuse is blocked until the listed governance gaps are repaired")
        if action == "consolidate":
            candidates = {r["asset_id"] for r in evidence["consolidation_candidates"]}
            if not target_asset_id or target_asset_id not in candidates:
                raise ValueError("Consolidation review requires matching product/market and a shared canonical metric label")
        elif target_asset_id:
            raise ValueError("A target asset is only valid for consolidation")
        if action == "migrate" and evidence["asset"].get("platform") != "Tableau":
            raise ValueError("This migration proposal supports Tableau sources only")
        if action == "retire" and evidence["downstream_ids"]:
            raise ValueError("Retirement proposal blocked by downstream dependencies")
        return {
            **self.provenance(), "kind": "lifecycle", "asset_id": asset_id,
            "action": action, "target_asset_id": target_asset_id,
            "owner_id": owner_id, "rationale": rationale.strip(),
            "evidence": evidence,
            "execution_status": "not_executed",
            "release_requirements": [
                "Named owner sign-off", "KPI steward verifies definitions and source quality",
                "Platform administrator verifies workspace access and lineage impact",
                "Business owner validates replacement equivalence and retention obligations",
                "Separate production release approval; this local plan executes no estate changes",
            ],
        }
