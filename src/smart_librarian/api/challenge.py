"""Challenge builder-pack API router (mounted only in challenge mode).

Loopback demonstration only: fixed simulated identities and approvals, not
real authentication. All business values come from the read-only challenge
engine; plans persist in the shared runtime store with CAS transitions.
"""

from typing import Annotated, Literal, Union

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from smart_librarian.reporting.challenge_pbip import build_challenge_pbip_bundle
from smart_librarian.reporting.challenge_exports import (
    challenge_bundle,
    challenge_import_kit,
    challenge_report_html,
    challenge_rows_csv,
)

MAX_IDS = 100
DomainId = Literal["commercial", "market_access", "supply", "launch"]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChallengeIntent(_Body):
    product_ids: list[str] = Field(default_factory=list, max_length=MAX_IDS)
    market_ids: list[str] = Field(default_factory=list, max_length=MAX_IDS)
    metric_ids: list[str] = Field(default_factory=list, max_length=MAX_IDS)
    months: list[str] = Field(default_factory=list, max_length=MAX_IDS)
    grain: str = Field(default="", max_length=50)


class ExtractIn(_Body):
    user_id: str = Field(min_length=1, max_length=200)
    domain_id: DomainId
    text: str = Field(min_length=1, max_length=4000)
    use_llm: bool = False


class ReportPlanIn(_Body):
    kind: Literal["report"]
    user_id: str = Field(min_length=1, max_length=200)
    domain_id: DomainId
    intent: ChallengeIntent
    owner_id: str = Field(min_length=1, max_length=200)
    rationale: str = Field(default="", max_length=4000)


class LifecyclePlanIn(_Body):
    kind: Literal["lifecycle"]
    user_id: str = Field(min_length=1, max_length=200)
    asset_id: str = Field(min_length=1, max_length=200)
    action: Literal["reuse", "repair", "consolidate", "retire", "migrate"]
    target_asset_id: str | None = Field(default=None, max_length=200)
    owner_id: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=4000)


PlanIn = Annotated[
    Union[ReportPlanIn, LifecyclePlanIn], Field(discriminator="kind")
]


class ApprovalIn(_Body):
    user_id: str = Field(min_length=1, max_length=200)
    actor_user_id: str = Field(min_length=1, max_length=200)
    spec_hash: str = Field(min_length=1, max_length=128)
    decision: Literal["approve", "reject"]
    expected_revision: int = Field(ge=0)


class RenderIn(_Body):
    user_id: str = Field(min_length=1, max_length=200)
    spec_hash: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=0)


_EXPORT_FORMATS = {
    "html": ("text/html", "challenge_report.html"),
    "csv": ("text/csv", "challenge_report.csv"),
    "zip": ("application/zip", "challenge_report_bundle.zip"),
    "kit": ("application/zip", "challenge_powerbi_import_kit.zip"),
    "pbip": ("application/zip", "challenge_report_pbip.zip"),
}


def build_challenge_router(service) -> APIRouter:
    router = APIRouter()

    @router.get("/catalog")
    def catalog(domain_id: DomainId):
        return service.catalog(domain_id)

    @router.get("/requests")
    def requests():
        return service.requests()

    @router.get("/actors")
    def actors():
        return service.actors()

    @router.get("/estate")
    def estate(user_id: str = Query(min_length=1, max_length=200),
               q: str = Query(default="", max_length=200)):
        return service.estate(user_id, q)

    @router.get("/estate/{asset_id}")
    def estate_asset(asset_id: str,
                     user_id: str = Query(min_length=1, max_length=200)):
        return service.estate_asset(user_id, asset_id)

    @router.post("/extract")
    def extract(body: ExtractIn):
        return service.extract(
            body.user_id, body.domain_id, body.text, body.use_llm
        )

    @router.post("/plans")
    def create_plan(body: PlanIn):
        if body.kind == "report":
            return service.create_report_plan(
                body.user_id, body.domain_id, body.intent.model_dump(),
                body.owner_id, body.rationale,
            )
        return service.create_lifecycle_plan(
            body.user_id, body.asset_id, body.action,
            body.target_asset_id, body.owner_id, body.rationale,
        )

    @router.get("/plans")
    def list_plans(user_id: str = Query(min_length=1, max_length=200)):
        return service.list_plans(user_id)

    @router.get("/plans/{plan_id}")
    def get_plan(plan_id: str,
                 user_id: str = Query(min_length=1, max_length=200)):
        return service.get_plan(user_id, plan_id)

    @router.post("/plans/{plan_id}/approval")
    def approval(plan_id: str, body: ApprovalIn):
        return service.record_approval(
            body.user_id, plan_id, body.actor_user_id, body.spec_hash,
            body.decision, body.expected_revision,
        )

    @router.post("/plans/{plan_id}/render")
    def render(plan_id: str, body: RenderIn):
        return service.render(
            body.user_id, plan_id, body.spec_hash, body.expected_revision,
        )

    @router.get("/plans/{plan_id}/report")
    def report(plan_id: str,
               user_id: str = Query(min_length=1, max_length=200)):
        return service.get_report(user_id, plan_id)

    @router.get("/plans/{plan_id}/export")
    def export(plan_id: str,
               user_id: str = Query(min_length=1, max_length=200),
               format: Literal["html", "csv", "zip", "kit", "pbip"] = "html"):
        result = service.get_report(user_id, plan_id)
        frozen = result["report"]
        audit = result["audit"]
        if format == "html":
            content = challenge_report_html(frozen, audit)
        elif format == "csv":
            content = challenge_rows_csv(frozen)
        elif format == "zip":
            content = challenge_bundle(frozen, audit)
        elif format == "pbip":
            content = build_challenge_pbip_bundle(frozen)
        else:
            content = challenge_import_kit(frozen)
        media, filename = _EXPORT_FORMATS[format]
        return Response(
            content=content, media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return router
