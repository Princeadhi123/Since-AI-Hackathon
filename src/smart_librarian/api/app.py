"""FastAPI transport for the Smart Librarian local demo.

Loopback demonstration only: simulated identities and approvals, not real
authentication or production authorization. No arbitrary SQL, formulas or
metric definitions are accepted - intents resolve against the fixed catalog
contract and lead-authored calculations.
"""

from typing import Literal

from fastapi import FastAPI, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from pathlib import Path

from smart_librarian.catalog.store import (
    CatalogError,
    DemoCatalog,
    GovernedCatalog,
    SnapshotDrift,
)
from smart_librarian.domain.governance import actors as governance_actors
from smart_librarian.evidence import EvidenceError, load_evidence
from smart_librarian.persistence.store import RuntimeStore
from smart_librarian.settings import load_settings, provider_status
from smart_librarian.workflow.service import (
    Conflict,
    Forbidden,
    SessionNotFound,
    WorkflowService,
)

MAX_IDS = 100


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionCreate(_Body):
    user_id: str = Field(min_length=1, max_length=200)
    domain_id: Literal["sales", "logistics", "quality",
                       "public_sales"] | None = None


class MessageIn(_Body):
    user_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=4000)
    use_llm: bool = False


class Intent(_Body):
    product_ids: list[str] = Field(default_factory=list, max_length=MAX_IDS)
    market_ids: list[str] = Field(default_factory=list, max_length=MAX_IDS)
    metric_ids: list[str] = Field(default_factory=list, max_length=MAX_IDS)
    months: list[str] = Field(default_factory=list, max_length=MAX_IDS)
    grain: str = Field(default="", max_length=50)


class IntentIn(_Body):
    user_id: str = Field(min_length=1, max_length=200)
    intent: Intent


class ApprovalIn(_Body):
    user_id: str = Field(min_length=1, max_length=200)
    proposal_id: str = Field(min_length=1, max_length=200)
    spec_hash: str = Field(min_length=1, max_length=128)
    decision: Literal["approve", "reject"]
    actor_user_id: str = "DEMO-APPROVER"


class ReuseIn(_Body):
    user_id: str = Field(min_length=1, max_length=200)
    domain_id: Literal["sales", "logistics", "quality",
                       "public_sales"] | None = None


def _public_state(state: dict) -> dict:
    state.pop("revision", None)
    return state


class ConfigurationError(Exception):
    """Raised when configured paths would endanger fixture data."""


def _assert_safe_runtime_db(demo_dir: Path, runtime_db: Path) -> None:
    demo_root = Path(demo_dir).resolve()
    db_path = Path(runtime_db).resolve()
    if db_path == demo_root / "demo.sqlite" or demo_root in db_path.parents:
        raise ConfigurationError(
            f"RUNTIME_DB_PATH {db_path} resolves inside the demo fixture "
            f"directory {demo_root}; refusing to open it."
        )


_DOMAIN_DISPLAY = {
    "sales": "Sales",
    "logistics": "Logistics / Distribution",
    "quality": "Manufacturing Quality",
    "public_sales": "Bayer public sales (real data)",
}
_OPTIONAL_DOMAINS = {"logistics": "demo_logistics_v1",
                     "quality": "demo_quality_v1"}


def _domain_order(services: dict) -> list[str]:
    order = sorted(
        d for d in services if d not in ("sales", "public_sales")
    )
    if "sales" in services:
        order = ["sales"] + order
    if "public_sales" in services:
        return ["public_sales"] + order
    return order


def create_app(*, demo_dir=None, runtime_db=None, include_synthetic=False,
               public_snapshot=None, challenge_mode=False) -> FastAPI:
    settings = load_settings()
    sales_dir = Path(demo_dir or settings.demo_dir)
    db_path = Path(runtime_db or settings.runtime_db)
    real_only = not include_synthetic and demo_dir is None

    # Discover every fixture BEFORE opening the runtime store, then validate
    # the runtime path against each one - pointing RUNTIME_DB_PATH at any
    # fixture's own demo.sqlite (or inside its directory) must fail closed.
    demo_dirs = {"sales": sales_dir}
    for domain_id, dirname in _OPTIONAL_DOMAINS.items():
        candidate = sales_dir.parent / dirname
        if (candidate / "catalog.json").exists():
            demo_dirs[domain_id] = candidate
    for fixture_dir in demo_dirs.values():
        _assert_safe_runtime_db(fixture_dir, db_path)
    public_base = None
    if real_only:
        from smart_librarian.catalog.public_financials import (
            SNAPSHOT_PATH,
            PublicFinancialCatalog,
        )
        from smart_librarian.settings import REPO_ROOT

        snapshot_path = (
            Path(public_snapshot) if public_snapshot else SNAPSHOT_PATH
        )
        _assert_safe_runtime_db(REPO_ROOT / "data" / "evidence", db_path)
        _assert_safe_runtime_db(snapshot_path.parent, db_path)
        public_base = PublicFinancialCatalog(snapshot_path)
    elif demo_dir is None:
        # Normal launcher: mount the governed public-actuals domain from
        # the frozen evidence file. A missing/invalid evidence file fails
        # loudly - there is no fallback to synthetic data for this domain.
        from smart_librarian.catalog.public_annual import PublicAnnualCatalog
        from smart_librarian.settings import REPO_ROOT

        evidence_dir = REPO_ROOT / "data" / "evidence"
        _assert_safe_runtime_db(evidence_dir, db_path)
        public_base = PublicAnnualCatalog(
            evidence_dir / "public_financials.json"
        )
    if challenge_mode:
        from smart_librarian.challenge import WORKBOOK
        from smart_librarian.settings import REPO_ROOT as _ROOT

        _assert_safe_runtime_db(_ROOT / "data", db_path)
        if db_path.resolve() == Path(WORKBOOK).resolve():
            raise ConfigurationError(
                "RUNTIME_DB_PATH resolves to the source builder workbook; "
                "refusing to open it."
            )
    store = RuntimeStore(db_path)

    catalogs: dict[str, GovernedCatalog] = {}
    services: dict[str, WorkflowService] = {}
    if not real_only:
        for domain_id, path in demo_dirs.items():
            base = DemoCatalog(path)
            catalogs[domain_id] = GovernedCatalog(base, store)
            services[domain_id] = WorkflowService(
                catalogs[domain_id], store, domain_id=domain_id
            )
    if public_base is not None:
        catalogs["public_sales"] = GovernedCatalog(public_base, store)
        services["public_sales"] = WorkflowService(
            catalogs["public_sales"], store, domain_id="public_sales"
        )
    default_domain = "public_sales" if real_only else "sales"

    def service_for(domain_id: str) -> WorkflowService:
        service = services.get(domain_id)
        if service is None:
            raise SessionNotFound(f"unknown domain '{domain_id}'")
        return service

    def session_service(session_id: str) -> WorkflowService:
        """Session-bound routes derive the domain from stored state only."""
        state = store.get_session(session_id)
        if state is None:
            raise SessionNotFound(session_id)
        return service_for(state.get("domain_id") or default_domain)

    app = FastAPI(title="Smart Librarian (local demo)")
    app.state.services = services
    app.state.service = services[default_domain]
    app.state.real_data_only = real_only
    app.state.default_domain = default_domain
    app.state.challenge_mode = challenge_mode
    if challenge_mode:
        from smart_librarian.api.challenge import build_challenge_router
        from smart_librarian.workflow.challenge import ChallengeService

        challenge_service = ChallengeService(store)
        app.state.challenge_service = challenge_service
        app.include_router(
            build_challenge_router(challenge_service),
            prefix="/api/challenge",
        )

    @app.exception_handler(SessionNotFound)
    async def _not_found(request, exc):
        return JSONResponse({"detail": "session not found"}, status_code=404)

    @app.exception_handler(Forbidden)
    async def _forbidden(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=403)

    @app.exception_handler(Conflict)
    async def _conflict(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(SnapshotDrift)
    async def _drift(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(CatalogError)
    async def _catalog_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(RequestValidationError)
    async def _validation(request, exc):
        return JSONResponse({"detail": exc.errors()}, status_code=422)

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "dataset_id": catalogs[default_domain].dataset_id,
            "domains": _domain_order(services),
            "real_data_only": real_only,
            "challenge_mode": challenge_mode,
            "simulated": True,
        }

    @app.get("/api/domains")
    def domains():
        return {
            "domains": [
                {
                    "domain_id": domain_id,
                    "display_name": _DOMAIN_DISPLAY.get(domain_id, domain_id),
                    "dimension_labels": catalogs[domain_id].choices()[
                        "dimension_labels"
                    ],
                    "data_classification": catalogs[domain_id].choices().get(
                        "data_classification", "synthetic_demo"
                    ),
                }
                for domain_id in _domain_order(services)
            ],
            "real_data_only": real_only,
            "challenge_mode": challenge_mode,
            "simulated": True,
        }

    @app.get("/api/capabilities")
    def capabilities():
        # Boolean/model only; the API key itself is never exposed.
        return provider_status()

    @app.get("/api/evidence/{kind}")
    def evidence(kind: Literal["challenge", "public"]):
        if real_only and kind == "challenge":
            return JSONResponse(
                {"detail": "challenge estate is not mounted in "
                           "real-data-only mode"},
                status_code=404,
            )
        try:
            return load_evidence(kind)
        except EvidenceError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.get("/api/public-financials")
    def public_financials():
        if not real_only:
            return JSONResponse(
                {"detail": "public financials snapshot is only mounted in "
                           "real-data-only mode"},
                status_code=404,
            )
        base = catalogs["public_sales"]
        base.assert_current()
        return base.financial_snapshot()

    @app.get("/api/governance-actors")
    def governance():
        actors = governance_actors()
        if real_only:
            actors = [
                actor for actor in actors
                if actor["actor_id"] == "DEMO-PUBLIC-APPROVER"
            ]
        return {"actors": actors, "simulated": True}

    @app.get("/api/demo-users")
    def demo_users(domain_id: str | None = None):
        return service_for(domain_id or default_domain).demo_users()

    @app.get("/api/catalog")
    def catalog_view(user_id: str = Query(min_length=1, max_length=200),
                     domain_id: str | None = None):
        return service_for(domain_id or default_domain).catalog_for_user(
            user_id
        )

    @app.post("/api/sessions")
    def create_session(body: SessionCreate):
        state = service_for(
            body.domain_id or default_domain
        ).create_session(body.user_id)
        return {"session_id": state["session_id"]}

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str, user_id: str = Query(min_length=1, max_length=200)):
        return _public_state(
            session_service(session_id).get_state(session_id, user_id)
        )

    @app.post("/api/sessions/{session_id}/messages")
    def post_message(session_id: str, body: MessageIn):
        return _public_state(
            session_service(session_id).post_message(
                session_id, body.user_id, body.text, body.use_llm
            )
        )

    @app.post("/api/sessions/{session_id}/intent")
    def confirm_intent(session_id: str, body: IntentIn):
        return _public_state(
            session_service(session_id).confirm_intent(
                session_id, body.user_id, body.intent.model_dump()
            )
        )

    @app.post("/api/sessions/{session_id}/approval")
    def approval(session_id: str, body: ApprovalIn):
        return _public_state(
            session_service(session_id).record_approval(
                session_id, body.user_id, body.proposal_id,
                body.spec_hash, body.decision, body.actor_user_id,
            )
        )

    @app.get("/api/sessions/{session_id}/report")
    def report(session_id: str, user_id: str = Query(min_length=1, max_length=200)):
        return session_service(session_id).render_report(session_id, user_id)

    @app.get("/api/sessions/{session_id}/audit")
    def audit(session_id: str, user_id: str = Query(min_length=1, max_length=200)):
        return {
            "session_id": session_id,
            "events": session_service(session_id).list_audit(session_id, user_id),
        }

    @app.get("/api/assets")
    def assets(user_id: str = Query(min_length=1, max_length=200),
               domain_id: str | None = None):
        return {
            "assets": service_for(
                domain_id or default_domain
            ).list_assets(user_id),
            "simulated": True,
        }

    @app.get("/api/assets/{asset_id}")
    def asset(asset_id: str, user_id: str = Query(min_length=1, max_length=200),
              domain_id: str | None = None):
        return service_for(domain_id or default_domain).get_asset(
            user_id, asset_id
        )

    @app.post("/api/assets/{asset_id}/reuse")
    def reuse_asset(asset_id: str, body: ReuseIn):
        result = service_for(
            body.domain_id or default_domain
        ).reuse_asset(body.user_id, asset_id)
        return {
            "session_id": result["session_id"],
            "state": _public_state(result["state"]),
        }

    return app


def create_legacy_app() -> FastAPI:
    """Full synthetic + public demo app (no challenge routes)."""
    return create_app(include_synthetic=True)


def create_challenge_app() -> FastAPI:
    """Demo app with the challenge builder-pack routes mounted."""
    return create_app(include_synthetic=True, challenge_mode=True)


app = create_app()
