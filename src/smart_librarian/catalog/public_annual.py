import copy
import hashlib
import json
from pathlib import Path

from smart_librarian.catalog.store import CatalogError, DemoCatalog, SnapshotDrift
from smart_librarian.evidence import (
    EVIDENCE_DIR,
    EvidenceError,
    _check_metadata,
    _check_public,
)
from smart_librarian.reporting.public_annual import (
    METRIC_CONTRACT,
    MODEL_CONTRACT,
    PRODUCT_IDS,
    compute_public_annual,
    source_provenance,
)


class PublicAnnualCatalog(DemoCatalog):
    def __init__(self, evidence_path: Path | None = None):
        self.source_path = Path(evidence_path or EVIDENCE_DIR / "public_financials.json")
        self.demo_dir = self.source_path.parent
        self.catalog_path = self.source_path
        self.db_path = self.source_path
        try:
            raw = self.source_path.read_bytes()
            evidence = json.loads(raw.decode("utf-8"))
            if not isinstance(evidence, dict):
                raise EvidenceError("Public source must be an object.")
            _check_metadata("public", self.source_path.name, evidence)
            _check_public(evidence)
            compute_public_annual(
                evidence, product_ids=list(PRODUCT_IDS.values()), market_ids=["GLOBAL"],
                months=["2024", "2025"], metric_ids=[METRIC_CONTRACT["metric_id"]],
            )
        except (OSError, UnicodeError, ValueError, EvidenceError) as exc:
            raise CatalogError(f"Public annual source unavailable or invalid: {exc}") from exc
        self.public_evidence = evidence
        self._source_hash = hashlib.sha256(raw).hexdigest()
        self._dimensions = {
            "products": [
                {"product_id": identifier, "product_name": name}
                for name, identifier in PRODUCT_IDS.items()
            ],
            "markets": [{"market_id": "GLOBAL", "market_name": "Global", "currency": "EUR"}],
            "calendar": [
                {"month": year, "year": year} for year in ("2024", "2025")
            ],
        }
        model = copy.deepcopy(MODEL_CONTRACT) | {
            "name": "Bayer Published Annual Product Sales",
            "owner_id": "DEMO-OWNER-PUBLIC",
            "endorsement": "promoted",
            "certification_is_simulated": True,
            "coverage": {
                "product_ids": list(PRODUCT_IDS.values()),
                "market_ids": ["GLOBAL"],
                "months": ["2024", "2025"],
            },
            "snapshot_as_of": evidence["retrieved_at_utc"],
            "refresh_status": "healthy",
            "refresh_is_simulated": True,
            "time_semantics": "Fiscal-year labels YYYY; no monthly or country data.",
            "amount_semantics": "Published reported sales, integer EUR million, no conversion.",
        }
        self.catalog = {
            "dataset_id": "PUBLIC-BAYER-ANNUAL-2025",
            "domain_id": "public_sales",
            "synthetic_record": False,
            "data_classification": "public_reported_actual",
            "owners": [{
                "owner_id": "DEMO-OWNER-PUBLIC", "name": "Demo Public-data Steward",
                "status": "active", "simulated": True,
            }],
            "users": [
                {
                    "user_id": "DEMO-USER-GLOBAL", "name": "Demo Global Analyst",
                    "allowed_market_ids": ["GLOBAL"], "simulated": True,
                },
                {
                    "user_id": "DEMO-USER-FI", "name": "Demo Finland-only Analyst",
                    "allowed_market_ids": ["FI"], "simulated": True,
                },
            ],
            "models": [model],
            "metrics": [copy.deepcopy(METRIC_CONTRACT)],
            "reports": [],
            "lineage": [],
            "policy": {
                "scope": "Local demo governance over real public financial disclosure.",
                "default_access": "deny",
                "governance_is_simulated": True,
            },
        }
        metadata = json.dumps(self.catalog, sort_keys=True, separators=(",", ":")).encode()
        self._fingerprint = hashlib.sha256(raw + b"\0" + metadata).hexdigest()
        self.assert_current()

    def assert_current(self) -> None:
        try:
            current = hashlib.sha256(self.source_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise SnapshotDrift("Public evidence snapshot is unavailable.") from exc
        if current != self._source_hash:
            raise SnapshotDrift("Public evidence changed after load; reload before rendering.")

    def choices(self) -> dict:
        return super().choices() | {
            "synthetic_record": False,
            "data_classification": "public_reported_actual",
            "period_label": "Fiscal years",
            "time_column": "fiscal_year",
            "period_field_semantics": (
                "For this annual domain the legacy months field contains fiscal-year "
                "labels YYYY, not calendar months or dates."
            ),
            "source_provenance": source_provenance(self.public_evidence),
        }
