import copy
import hashlib
import json
from pathlib import Path

from smart_librarian.catalog.store import CatalogError, DemoCatalog, SnapshotDrift
from smart_librarian.reporting.public_financials import (
    METRIC_CONTRACT,
    MODEL_CONTRACT,
    source_provenance,
    validate_snapshot,
)
from smart_librarian.settings import REPO_ROOT

SNAPSHOT_PATH = REPO_ROOT / "data" / "public_financials_v2" / "dataset.json"


class PublicFinancialCatalog(DemoCatalog):
    def __init__(self, snapshot_path=None):
        self.source_path = Path(snapshot_path or SNAPSHOT_PATH)
        self.demo_dir = self.source_path.parent
        self.catalog_path = self.db_path = self.source_path
        try:
            raw = self.source_path.read_bytes()
            evidence = json.loads(raw.decode("utf-8"))
            validate_snapshot(evidence)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise CatalogError(f"Public financial source unavailable or invalid: {exc}") from exc
        self.public_evidence = evidence
        self._source_hash = hashlib.sha256(raw).hexdigest()
        self._dimensions = {
            "products": copy.deepcopy(evidence["products"]),
            "markets": [{"market_id": "GLOBAL", "market_name": "Global", "currency": "EUR"}],
            "calendar": [{"month": p["period_id"]} for p in evidence["periods"]],
        }
        model = copy.deepcopy(MODEL_CONTRACT) | {
            "name": "Published Bayer Product Sales", "owner_id": "DEMO-OWNER-PUBLIC",
            "endorsement": "promoted", "certification_is_simulated": True,
            "coverage": {
                "product_ids": [p["product_id"] for p in evidence["products"]],
                "market_ids": ["GLOBAL"],
                "months": [p["period_id"] for p in evidence["periods"]],
                "period_kinds": {p["period_id"]: p["period_kind"] for p in evidence["periods"]},
            },
            "snapshot_as_of": evidence["retrieved_at_utc"],
            "refresh_status": "healthy", "refresh_is_simulated": True,
            "time_semantics": "Explicit fiscal-year, quarter or half-year labels; never mix grains.",
            "amount_semantics": "Published integer EUR million; source-versioned reported sales.",
        }
        self.catalog = {
            "dataset_id": "PUBLIC-BAYER-FINANCIALS-V2", "domain_id": "public_sales",
            "synthetic_record": False, "data_classification": "public_reported_actual",
            "owners": [{
                "owner_id": "DEMO-OWNER-PUBLIC", "name": "Demo Public-data Steward",
                "status": "active", "simulated": True,
            }],
            "users": [
                {"user_id": "DEMO-USER-GLOBAL", "name": "Demo Global Analyst",
                 "allowed_market_ids": ["GLOBAL"], "simulated": True},
                {"user_id": "DEMO-USER-FI", "name": "Demo Finland-only Analyst",
                 "allowed_market_ids": ["FI"], "simulated": True},
            ],
            "models": [model], "metrics": [copy.deepcopy(METRIC_CONTRACT)],
            "reports": [], "lineage": [],
            "policy": {"scope": "Local demo governance over published public financials.",
                       "default_access": "deny", "governance_is_simulated": True},
        }
        metadata = json.dumps(self.catalog, sort_keys=True, separators=(",", ":")).encode()
        self._fingerprint = hashlib.sha256(raw + b"\0" + metadata).hexdigest()
        self.assert_current()

    def assert_current(self):
        try:
            current = hashlib.sha256(self.source_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise SnapshotDrift("Public financial snapshot is unavailable.") from exc
        if current != self._source_hash:
            raise SnapshotDrift("Public financial snapshot changed after load; restart to reload.")

    def choices(self):
        return super().choices() | {
            "synthetic_record": False, "data_classification": "public_reported_actual",
            "period_label": "Reporting periods", "time_column": "period",
            "periods": copy.deepcopy(self.public_evidence["periods"]),
            "period_field_semantics": (
                "The legacy months key holds explicit published reporting-period labels, "
                "not calendar months. Select exactly one period type per report."
            ),
            "source_provenance": source_provenance(self.public_evidence),
        }

    def financial_snapshot(self):
        self.assert_current()
        return copy.deepcopy(self.public_evidence)
