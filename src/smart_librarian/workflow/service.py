"""Workflow orchestration: chat intake, intent confirmation, approval, render.

Sessions bind to a simulated identity. Any new chat message or new confirmed
intent invalidates the previous proposal and approval. Business values are
produced only by smart_librarian.reporting.calculations.compute_monthly and
only after the deterministic gates pass.
"""

from smart_librarian.catalog.store import DemoCatalog
from smart_librarian.domain import decision, governance, parser
from smart_librarian.persistence.store import (
    PublicationRejected,
    RevisionConflict,
    RuntimeStore,
)
from smart_librarian.domain.operational_contracts import CONTRACTS
from smart_librarian.reporting.calculations import compute_monthly
from smart_librarian.reporting.operational import compute_operational


class SessionNotFound(Exception):
    pass


class Forbidden(Exception):
    pass


class Conflict(Exception):
    pass


class LLMUnavailable(Exception):
    pass


MAX_UPDATE_ATTEMPTS = 3

CONCURRENT_UPDATE_MESSAGE = "Session is being updated concurrently; retry."
_DECISION_STATUS = {"approve": "approved", "reject": "rejected"}


def _message_outcome(llm_error, unsupported, unresolved, questions,
                     grain="month"):
    """Map an extraction result to the session outcome and reply text."""
    if llm_error is not None:
        return "CLARIFY", (
            f"LLM extraction unavailable ({llm_error}); fell back to "
            "the offline parser. Please confirm the guided form."
        )
    if unsupported:
        return "CLARIFY", "Unsupported requirements detected: " + "; ".join(
            unsupported
        )
    if unresolved:
        return "CLARIFY", "I need a few more details: " + " ".join(questions)
    if grain == "period":
        return "CONFIRM_INTENT", (
            "I extracted a complete reporting-period intent. Confirm it "
            "in the guided form before any decision is made."
        )
    if grain == "year":
        return "CONFIRM_INTENT", (
            "I extracted a complete annual intent. Confirm it in the "
            "guided form before any decision is made."
        )
    return "CONFIRM_INTENT", (
        "I extracted a complete monthly intent. Confirm it in the "
        "guided form before any decision is made."
    )


def _resolve_approval(proposal, proposal_id, spec_hash, decision_value):
    """Validate the referenced proposal; returns (proposal, idempotent)."""
    if (
        proposal is None
        or proposal["proposal_id"] != proposal_id
        or proposal["spec_hash"] != spec_hash
    ):
        raise Conflict("Stale or unknown proposal reference.")
    current = proposal["approval_status"]
    if current == "not_required":
        raise Conflict("This proposal does not require approval.")
    if current == _DECISION_STATUS[decision_value]:
        return proposal, True
    if current != "pending":
        raise Conflict("Proposal already decided; cannot change decision.")
    return proposal, False


class WorkflowService:
    def __init__(self, catalog: DemoCatalog, store: RuntimeStore, llm=None,
                 domain_id: str = "sales"):
        self.catalog = catalog
        self.store = store
        self.llm = llm
        self.domain_id = domain_id

    # -- identity / metadata -------------------------------------------------

    def demo_users(self) -> dict:
        self.catalog.assert_current()
        return {
            "simulated": True,
            "users": [
                {
                    "user_id": user["user_id"],
                    "name": user.get("name"),
                    "allowed_market_ids": user.get("allowed_market_ids") or [],
                }
                for user in self.catalog.users()
            ],
        }

    def _require_user(self, user_id: str) -> dict:
        user = self.catalog.user(user_id)
        if user is None:
            raise Forbidden("Unknown simulated identity.")
        return user

    def catalog_for_user(self, user_id: str) -> dict:
        self.catalog.assert_current()
        user = self._require_user(user_id)
        reports = [
            {
                key: report.get(key)
                for key in (
                    "asset_id", "name", "metric_ids", "coverage", "grain",
                    "endorsement", "lifecycle_status", "destination",
                )
            }
            for report in self.catalog.allowed_reports(user)
        ]
        return {
            "user": {
                "user_id": user["user_id"],
                "name": user.get("name"),
                "allowed_market_ids": user.get("allowed_market_ids") or [],
            },
            "choices": self.catalog.choices(),
            "reports": reports,
            "simulated": True,
        }

    # -- session helpers -----------------------------------------------------

    def _load(self, session_id: str, user_id: str) -> tuple[dict, int]:
        state = self.store.get_session(session_id)
        if state is None:
            raise SessionNotFound(session_id)
        if state["user_id"] != user_id:
            raise Forbidden("Session belongs to a different simulated identity.")
        revision = state.pop("revision")
        return state, revision

    def create_session(self, user_id: str) -> dict:
        self.catalog.assert_current()
        self._require_user(user_id)
        state = self.store.create_session(user_id, self.domain_id)
        self.store.append_audit(
            state["session_id"], user_id, "session_created", {"user_id": user_id}
        )
        return state

    def get_state(self, session_id: str, user_id: str) -> dict:
        self.catalog.assert_current()
        state, _ = self._load(session_id, user_id)
        return state

    def list_audit(self, session_id: str, user_id: str) -> list[dict]:
        self.catalog.assert_current()
        self._load(session_id, user_id)
        return self.store.list_audit(session_id)

    # -- chat intake ----------------------------------------------------------

    def post_message(self, session_id: str, user_id: str, text: str,
                     use_llm: bool) -> dict:
        self.catalog.assert_current()
        self._require_user(user_id)
        for _ in range(MAX_UPDATE_ATTEMPTS):
            state, revision = self._load(session_id, user_id)
            state["messages"].append({"role": "user", "text": text})
            # Any new chat message invalidates a previous proposal/approval.
            state["proposal"] = None
            state["evidence"] = []

            extraction, mode, llm_error = self._extract_message(
                state["messages"], text, use_llm
            )

            state["extraction_mode"] = mode
            state["limitations"] = extraction.get("limitations")
            merged = parser.merge_partial(
                state.get("partial_intent"), extraction
            )
            # Explicit unresolvable mentions replace earlier selections;
            # merely absent fields retain them.
            for field in extraction.get("invalidated") or []:
                merged.pop(field, None)
            state["partial_intent"] = merged
            unresolved = parser.missing_fields(merged)
            unsupported = extraction.get("unsupported") or []
            state["unsupported"] = unsupported
            model_id = self.catalog.model().get("model_id")
            if model_id == "PUBLIC-MODEL-FINANCIALS":
                grain = "period"
            elif self.domain_id == "public_sales":
                grain = "year"
            else:
                grain = "month"
            questions = parser.questions_for(unresolved, grain=grain)
            if grain == "period":
                period_questions = {
                    "product_ids": (
                        "Which published product(s) or product families? "
                        "Choose from the reviewed selection."
                    ),
                    "market_ids": (
                        "Only global reported sales are available. Confirm "
                        "Global or revise your request."
                    ),
                    "metric_ids": (
                        "Reported Sales (EUR million) is the only published "
                        "measure; forecasts are unavailable."
                    ),
                    "months": (
                        "Which reporting period(s), for example FY 2025, "
                        "Q1 2026 or H1 2026?"
                    ),
                    "grain": (
                        "Which period type: Annual, Quarterly or Half-year?"
                    ),
                }
                questions = [
                    period_questions.get(field, question)
                    for field, question in zip(unresolved, questions)
                ]
            state["questions"] = questions

            state["outcome"], reply = _message_outcome(
                llm_error, unsupported, unresolved, state["questions"],
                grain=grain,
            )
            state["messages"].append({"role": "assistant", "text": reply})
            try:
                self.store.update_state(
                    session_id, revision, state,
                    audit={
                        "user_id": user_id,
                        "event_type": "message",
                        "detail": {"mode": mode, "outcome": state["outcome"]},
                    },
                )
                return state
            except RevisionConflict:
                continue
        raise Conflict(CONCURRENT_UPDATE_MESSAGE)

    def _extract_offline(self, text: str) -> dict:
        if self.catalog.model().get("model_id") == "PUBLIC-MODEL-FINANCIALS":
            from smart_librarian.domain.public_financials import (
                parse_financial_message,
            )
            return parse_financial_message(
                text, self.catalog.choices(), self.catalog
            )
        if self.domain_id == "public_sales":
            from smart_librarian.domain.public_annual import (
                parse_public_message,
            )
            return parse_public_message(
                text, self.catalog.choices(), self.catalog
            )
        return parser.parse_message(text, self.catalog.choices(), self.catalog)

    def _extract_message(self, messages: list[dict], text: str,
                         use_llm: bool) -> tuple[dict, str, str | None]:
        """Choose provider vs offline extraction; returns (extraction, mode, error)."""
        if not use_llm:
            return self._extract_offline(text), "offline", None
        try:
            return self._extract_llm(messages), "llm", None
        except LLMUnavailable as exc:
            extraction = self._extract_offline(text)
            return extraction, "offline_fallback_after_llm_unavailable", str(exc)

    def _extract_llm(self, messages: list[dict]) -> dict:
        if self.llm is None:
            from smart_librarian.llm.client import OpenAIIntentExtractor

            self.llm = OpenAIIntentExtractor()
        extraction = self.llm.extract_intent(
            conversation=[m["text"] for m in messages if m["role"] == "user"],
            catalog_choices=self.catalog.choices(),
        )
        extraction["limitations"] = (
            "LLM extraction is a proposal only; confirm via the guided form."
        )
        return extraction

    # -- intent confirmation --------------------------------------------------

    def confirm_intent(self, session_id: str, user_id: str, intent: dict) -> dict:
        self.catalog.assert_current()
        user = self._require_user(user_id)
        for _ in range(MAX_UPDATE_ATTEMPTS):
            state, revision = self._load(session_id, user_id)
            result = decision.evaluate(
                self.catalog, user, intent, self.catalog.fingerprint(),
                self.domain_id,
            )
            state["outcome"] = result["outcome"]
            state["evidence"] = result["evidence"]
            state["proposal"] = result["proposal"]
            state["questions"] = []
            state["candidate_explanations"] = result["candidate_explanations"]
            if result["outcome"] == "ACCESS_DENIED":
                reply = (
                    "This request is not permitted for the selected simulated "
                    "identity. No report details are returned."
                )
            elif result["outcome"] == "NEEDS_REVIEW":
                reply = "Cannot proceed: " + ", ".join(result["reasons"])
                state["review_reasons"] = result["reasons"]
            else:
                state.pop("review_reasons", None)
                reply = f"Decision: {result['outcome']}."
                if result["proposal"]["approval_status"] == "pending":
                    reply += " Approve or reject the proposal to continue."
                state["partial_intent"] = result["proposal"]["spec"]["intent"]
            state["messages"].append({"role": "assistant", "text": reply})
            try:
                self.store.update_state(
                    session_id, revision, state,
                    audit={
                        "user_id": user_id,
                        "event_type": "intent_confirmed",
                        "detail": {
                            "outcome": result["outcome"],
                            "reasons": result["reasons"],
                        },
                    },
                )
                return state
            except RevisionConflict:
                continue
        raise Conflict(CONCURRENT_UPDATE_MESSAGE)

    # -- approval --------------------------------------------------------------

    def record_approval(self, session_id: str, user_id: str, proposal_id: str,
                        spec_hash: str, decision_value: str,
                        actor_user_id: str = governance.DEFAULT_APPROVER_ID
                        ) -> dict:
        self.catalog.assert_current()
        user = self._require_user(user_id)
        actor = governance.actor(actor_user_id)
        if actor is None:
            raise Forbidden("Unknown simulated governance actor.")
        for _ in range(MAX_UPDATE_ATTEMPTS):
            state, revision = self._load(session_id, user_id)
            proposal, idempotent = _resolve_approval(
                state.get("proposal"), proposal_id, spec_hash, decision_value
            )
            spec = proposal["spec"]
            # Actor role/scope and requester scope/fingerprint are verified
            # even on a repeated decision: an approver must not be able to
            # replay an earlier approval after losing scope.
            gaps = governance.approval_gaps(
                actor, user_id, spec["intent"]["market_ids"]
            )
            if gaps:
                raise Forbidden(
                    "Simulated governance actor cannot decide this proposal: "
                    + ", ".join(gaps)
                )
            if spec["dataset_fingerprint"] != self.catalog.fingerprint():
                raise Conflict(
                    "Catalog files changed since the proposal was issued; "
                    "the approval is no longer valid."
                )
            allowed = set(user.get("allowed_market_ids") or [])
            if not set(spec["intent"]["market_ids"]).issubset(allowed):
                raise Forbidden("Requested markets are no longer permitted.")

            if idempotent:
                # Repeat of the same decision by a still-permitted actor.
                return state

            proposal["approval_status"] = _DECISION_STATUS[decision_value]
            state["messages"].append(
                {"role": "assistant", "text": f"Proposal {proposal['approval_status']}."}
            )
            try:
                self.store.update_state(
                    session_id, revision, state,
                    audit={
                        "user_id": actor["actor_id"],
                        "event_type": f"approval_{decision_value}",
                        "detail": {
                            "proposal_id": proposal_id,
                            "spec_hash": spec_hash,
                            "decision": decision_value,
                            "requester_user_id": user_id,
                            "actor_roles": list(actor.get("roles") or []),
                        },
                    },
                )
                return state
            except RevisionConflict:
                continue
        raise Conflict(CONCURRENT_UPDATE_MESSAGE)

    # -- report -----------------------------------------------------------------

    # -- governed asset registry ----------------------------------------------

    _ASSET_KEYS = (
        "asset_id", "name", "owner_id", "metric_ids", "coverage", "grain",
        "endorsement", "lifecycle_status", "destination", "origin",
        "created_at", "updated_at",
    )

    def _asset_metadata(self, report: dict) -> dict:
        """Public metadata only; no spec payload or requester identity."""
        metadata = {key: report.get(key) for key in self._ASSET_KEYS}
        owner = self.catalog.owner(report.get("owner_id")) or {}
        metadata["owner_name"] = owner.get("name")
        metadata["domain_id"] = self.domain_id
        return metadata

    def list_assets(self, user_id: str) -> list[dict]:
        self.catalog.assert_current()
        user = self._require_user(user_id)
        return [
            self._asset_metadata(report)
            for report in self.catalog.allowed_reports(user)
            if report.get("lifecycle_status") == "active"
        ]

    def get_asset(self, user_id: str, asset_id: str) -> dict:
        self.catalog.assert_current()
        user = self._require_user(user_id)
        for report in self.catalog.allowed_reports(user):
            if (
                report.get("asset_id") == asset_id
                and report.get("lifecycle_status") == "active"
            ):
                return self._asset_metadata(report)
        # Out-of-market, retired or unknown assets all look identical.
        raise SessionNotFound(asset_id)

    def reuse_asset(self, user_id: str, asset_id: str) -> dict:
        """Open a fresh session and confirm the asset's scope normally."""
        report = self.get_asset(user_id, asset_id)
        coverage = report.get("coverage") or {}
        intent = {
            "product_ids": list(coverage.get("product_ids") or []),
            "market_ids": list(coverage.get("market_ids") or []),
            "metric_ids": list(report.get("metric_ids") or []),
            "months": list(coverage.get("months") or []),
            "grain": report.get("grain"),
        }
        state = self.create_session(user_id)
        confirmed = self.confirm_intent(state["session_id"], user_id, intent)
        return {"session_id": state["session_id"], "state": confirmed}

    def _build_generated_asset(self, spec: dict, proposal: dict,
                               user_id: str) -> dict:
        model = self.catalog.model()
        asset_id, identity_key = decision.asset_identity(spec)
        metric_names = ", ".join(
            item.get("name") or item["metric_id"]
            for item in spec.get("requested_metrics") or []
        )
        return {
            "asset_id": asset_id,
            "identity_key": identity_key,
            "name": f"Generated {metric_names} ({spec['intent'].get('grain')})",
            "owner_id": model.get("owner_id"),
            "created_by": user_id,
            "dataset_fingerprint": spec["dataset_fingerprint"],
            "model_id": spec["model_id"],
            "spec": spec,
            "spec_hash": proposal["spec_hash"],
            "source_proposal_id": proposal["proposal_id"],
            "metric_ids": list(spec["intent"].get("metric_ids") or []),
            "coverage": {
                "product_ids": list(spec["intent"].get("product_ids") or []),
                "market_ids": list(spec["intent"].get("market_ids") or []),
                "months": list(spec["intent"].get("months") or []),
            },
            "grain": spec["intent"].get("grain"),
            "lifecycle_status": "active",
            "endorsement": "promoted",
            "destination": {
                "kind": "local_asset",
                "route": f"/api/assets/{asset_id}?domain_id={self.domain_id}",
                "required_params": ["user_id"],
                "implemented": True,
                "mock": False,
                "simulated_governance": True,
            },
        }

    # -- report -----------------------------------------------------------------

    def render_report(self, session_id: str, user_id: str) -> dict:
        self.catalog.assert_current()
        user = self._require_user(user_id)
        state, revision = self._load(session_id, user_id)
        proposal = state.get("proposal")
        if proposal is None:
            raise Conflict("No proposal exists for this session.")
        if proposal["approval_status"] not in ("approved", "not_required"):
            raise Conflict(
                f"Report is not available: approval status is "
                f"'{proposal['approval_status']}'."
            )
        spec = proposal["spec"]
        if spec["dataset_fingerprint"] != self.catalog.fingerprint():
            raise Conflict("Catalog files changed after approval; refusing to render.")
        allowed = set(user.get("allowed_market_ids") or [])
        intent = spec["intent"]
        if not set(intent["market_ids"]).issubset(allowed):
            raise Forbidden("Requested markets are no longer permitted.")
        if decision._gaps(self.catalog, self.catalog.model(), intent):
            raise Conflict("Catalog governance evidence no longer satisfied.")
        try:
            if self.catalog.model().get("model_id") == "PUBLIC-MODEL-FINANCIALS":
                from smart_librarian.reporting.public_financials import (
                    compute_public_financials,
                )
                result = compute_public_financials(
                    self.catalog.public_evidence,
                    product_ids=intent["product_ids"],
                    market_ids=intent["market_ids"],
                    months=intent["months"],
                    metric_ids=intent["metric_ids"],
                    grain=intent["grain"],
                )
            elif self.domain_id == "public_sales":
                from smart_librarian.reporting.public_annual import (
                    compute_public_annual,
                )
                result = compute_public_annual(
                    self.catalog.public_evidence,
                    product_ids=intent["product_ids"],
                    market_ids=intent["market_ids"],
                    months=intent["months"],
                    metric_ids=intent["metric_ids"],
                )
            elif self.domain_id in CONTRACTS:
                result = compute_operational(
                    self.catalog.db_path,
                    domain_id=self.domain_id,
                    product_ids=intent["product_ids"],
                    market_ids=intent["market_ids"],
                    months=intent["months"],
                    metric_ids=intent["metric_ids"],
                )
            else:
                result = compute_monthly(
                    self.catalog.db_path,
                    product_ids=intent["product_ids"],
                    market_ids=intent["market_ids"],
                    months=intent["months"],
                    metric_ids=intent["metric_ids"],
                )
        except ValueError as exc:
            raise Conflict(f"Calculation refused the confirmed scope: {exc}") from exc
        # The snapshot could have drifted during the calculation; re-verify
        # before publishing anything against it.
        self.catalog.assert_current()

        asset_metadata = None
        registered_asset_id = None
        if state["outcome"] in ("PROPOSE_BUILD", "PROPOSE_CHANGE"):
            # Register only after a successful calculation, atomically
            # re-verifying the live session proposal/approval.
            asset = self._build_generated_asset(spec, proposal, user_id)
            try:
                record, _created = self.store.publish_report(
                    session_id, revision, user_id, asset
                )
            except PublicationRejected as exc:
                raise Conflict(
                    "Session changed while rendering; the result was not "
                    "published. Render again."
                ) from exc
            registered_asset_id = record["asset_id"]
            asset_metadata = self._asset_metadata(
                self.catalog.report(record["asset_id"])
            )
        elif spec.get("source_asset_id"):
            # REUSE resolves to the already-registered asset; no republish.
            registered_asset_id = spec["source_asset_id"]
            existing = self.catalog.report(registered_asset_id)
            if existing is not None:
                asset_metadata = self._asset_metadata(existing)

        self.store.append_audit(
            session_id, user_id, "report_rendered",
            {
                "proposal_id": proposal["proposal_id"],
                "registered_asset_id": registered_asset_id,
            },
        )
        result.update(
            {
                "proposal_id": proposal["proposal_id"],
                "spec_hash": proposal["spec_hash"],
                "approval_status": proposal["approval_status"],
                "outcome": state["outcome"],
                "source_asset_id": spec["source_asset_id"],
                "registered_asset_id": registered_asset_id,
                "asset": asset_metadata,
                "spec": spec,
            }
        )
        return result
