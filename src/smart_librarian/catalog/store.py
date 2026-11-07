"""Read-only access to the demo fixture catalog.

Everything returned here is metadata: catalog records, simulated identities,
model coverage and choice lists for the guided intent form. Business values
are only produced by smart_librarian.reporting.calculations.
"""

import csv
import hashlib
import json
from pathlib import Path


class CatalogError(Exception):
    """Raised when required fixture files are missing or unreadable."""


class SnapshotDrift(Exception):
    """Raised when source files change after the catalog snapshot was loaded."""


_SOURCE_FILES = ("catalog.json", "demo.sqlite", "products.csv",
                 "markets.csv", "calendar.csv")


def _hash_files(demo_dir: Path) -> str:
    """SHA-256 over all runtime source files, in fixed order."""
    digest = hashlib.sha256()
    for name in _SOURCE_FILES:
        path = demo_dir / name
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise CatalogError(f"{name} unavailable: {exc}") from exc
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


class DemoCatalog:
    def __init__(self, demo_dir: Path):
        self.demo_dir = Path(demo_dir)
        self.catalog_path = self.demo_dir / "catalog.json"
        self.db_path = self.demo_dir / "demo.sqlite"
        # Read and hash, then hash again: any concurrent mutation during the
        # load produces a different fingerprint and fails closed here.
        self._fingerprint = _hash_files(self.demo_dir)
        try:
            self.catalog = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CatalogError(f"catalog.json unavailable: {exc}") from exc
        self._dimensions = self._load_dimensions()
        if _hash_files(self.demo_dir) != self._fingerprint:
            raise CatalogError(
                "Demo source files changed while loading; retry startup."
            )

    def _load_dimensions(self) -> dict:
        dimensions = {}
        for name in ("products", "markets", "calendar"):
            path = self.demo_dir / f"{name}.csv"
            try:
                with path.open(encoding="utf-8", newline="") as handle:
                    dimensions[name] = list(csv.DictReader(handle))
            except OSError as exc:
                raise CatalogError(f"{name}.csv unavailable: {exc}") from exc
        return dimensions

    def fingerprint(self) -> str:
        """Fingerprint captured when this coherent snapshot was loaded."""
        return self._fingerprint

    def assert_current(self) -> None:
        """Fail closed if any source file changed after load.

        The cached metadata and this fingerprint describe the loaded snapshot;
        drift means they can no longer be trusted together. Callers must
        restart/reload rather than auto-reload mid-session.
        """
        if _hash_files(self.demo_dir) != self._fingerprint:
            raise SnapshotDrift(
                "Demo source files changed after load; restart the service to "
                "reload a coherent snapshot."
            )

    @property
    def dataset_id(self) -> str:
        return self.catalog["dataset_id"]

    def model(self) -> dict:
        models = self.catalog.get("models") or []
        return models[0] if models else {}

    def users(self) -> list[dict]:
        return self.catalog.get("users") or []

    def user(self, user_id: str) -> dict | None:
        for user in self.users():
            if user.get("user_id") == user_id:
                return user
        return None

    def metrics(self) -> list[dict]:
        return self.catalog.get("metrics") or []

    def metric(self, metric_id: str) -> dict | None:
        for metric in self.metrics():
            if metric.get("metric_id") == metric_id:
                return metric
        return None

    def reports(self) -> list[dict]:
        return self.catalog.get("reports") or []

    def owner(self, owner_id: str) -> dict | None:
        for owner in self.catalog.get("owners") or []:
            if owner.get("owner_id") == owner_id:
                return owner
        return None

    def has_model_lineage(self, report_asset_id: str, model_id: str) -> bool:
        for edge in self.catalog.get("lineage") or []:
            if (
                edge.get("relationship") == "model_to_report"
                and edge.get("target_id") == report_asset_id
                and edge.get("source_id") == model_id
            ):
                return True
        return False

    def allowed_reports(self, user: dict) -> list[dict]:
        allowed = set(user.get("allowed_market_ids") or [])
        return [
            report
            for report in self.reports()
            if set((report.get("coverage") or {}).get("market_ids") or []).issubset(
                allowed
            )
        ]

    def choices(self) -> dict:
        """Metadata for the guided intent form and the optional LLM payload.

        Contains no business values.
        """
        model = self.model()
        coverage = model.get("coverage") or {}
        products = {
            row["product_id"]: row["product_name"]
            for row in self._dimensions["products"]
        }
        markets = {
            row["market_id"]: row["market_name"] for row in self._dimensions["markets"]
        }
        return {
            "dataset_id": self.dataset_id,
            "domain_id": self.catalog.get("domain_id", "sales"),
            "dimension_labels": self.catalog.get(
                "dimension_labels",
                {"products": "Products", "markets": "Markets"},
            ),
            "synthetic_record": True,
            "products": [
                {"product_id": pid, "product_name": products.get(pid, pid)}
                for pid in coverage.get("product_ids") or []
            ],
            "markets": [
                {"market_id": mid, "market_name": markets.get(mid, mid)}
                for mid in coverage.get("market_ids") or []
            ],
            "months": coverage.get("months") or [],
            "grain_options": model.get("supported_grains") or [],
            "metrics": [
                {
                    "metric_id": metric["metric_id"],
                    "name": metric.get("name"),
                    "unit": metric.get("unit"),
                    "approval_status": metric.get("approval_status"),
                    "supported_by_model": metric["metric_id"]
                    in (model.get("supported_metric_ids") or []),
                    "unsupported_reason": metric.get("unsupported_reason"),
                }
                for metric in self.metrics()
            ],
            "model": {
                "model_id": model.get("model_id"),
                "name": model.get("name"),
                "contract_version": model.get("contract_version"),
                "endorsement": model.get("endorsement"),
                "snapshot_as_of": model.get("snapshot_as_of"),
            },
        }


def report_record_to_metadata(record: dict) -> dict:
    """Shape a generated_reports row like a catalog report entry."""
    return {
        "asset_id": record["asset_id"],
        "name": record["name"],
        "model_id": record["model_id"],
        "owner_id": record["owner_id"],
        "metric_ids": list(record["metric_ids"]),
        "coverage": dict(record["coverage"]),
        "grain": record["grain"],
        "endorsement": record["endorsement"],
        "lifecycle_status": record["lifecycle_status"],
        "destination": dict(record["destination"]),
        "origin": "generated",
        "created_by": record["created_by"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }


class GovernedCatalog:
    """Runtime catalog view: the read-only fixture plus generated assets.

    Delegates every metadata lookup to the base DemoCatalog and overlays
    runtime-generated reports (filtered to the current dataset fingerprint
    and active lifecycle) on top of reports() and lineage. The fixture is
    never mutated.
    """

    def __init__(self, base: DemoCatalog, store):
        self._base = base
        self._store = store

    def __getattr__(self, name):
        return getattr(self._base, name)

    def _generated_reports(self) -> list[dict]:
        fingerprint = self._base.fingerprint()
        return [
            report_record_to_metadata(record)
            for record in self._store.list_generated_reports()
            if record["dataset_fingerprint"] == fingerprint
            and record["lifecycle_status"] == "active"
        ]

    def reports(self) -> list[dict]:
        reports = []
        for report in self._base.reports():
            merged = dict(report)
            merged.setdefault("origin", "seed")
            reports.append(merged)
        return reports + self._generated_reports()

    def report(self, asset_id: str) -> dict | None:
        for report in self.reports():
            if report.get("asset_id") == asset_id:
                return report
        return None

    def has_model_lineage(self, report_asset_id: str, model_id: str) -> bool:
        if self._base.has_model_lineage(report_asset_id, model_id):
            return True
        record = self._store.get_generated_report(report_asset_id)
        return (
            record is not None
            and record["model_id"] == model_id
            and record["dataset_fingerprint"] == self._base.fingerprint()
        )

    def allowed_reports(self, user: dict) -> list[dict]:
        allowed = set(user.get("allowed_market_ids") or [])
        return [
            report
            for report in self.reports()
            if set((report.get("coverage") or {}).get("market_ids") or []).issubset(
                allowed
            )
        ]
