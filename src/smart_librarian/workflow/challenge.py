"""Challenge builder-pack workflow: extraction, plans, approvals, renders.

Simulated identities only - not real authentication or authorization. All
business values come from smart_librarian.challenge (the source-of-truth
engine); this service enforces scope, approval binding and frozen-render
persistence against the shared runtime store.
"""

from smart_librarian.catalog.store import SnapshotDrift
from smart_librarian.challenge import CONTRACTS, ChallengeData, stable_hash
from smart_librarian.domain.challenge_parser import parse_challenge_message
from smart_librarian.persistence.store import RevisionConflict
from smart_librarian.workflow.service import (
    CONCURRENT_UPDATE_MESSAGE,
    Conflict,
    Forbidden,
    LLMUnavailable,
    SessionNotFound,
)

ACTORS = {
    "DEMO-CHALLENGE-REQUESTER": {
        "user_id": "DEMO-CHALLENGE-REQUESTER",
        "name": "Global Challenge Requester",
        "roles": ["requester"],
        "allowed_market_ids": None,  # all markets
    },
    "DEMO-CHALLENGE-FI": {
        "user_id": "DEMO-CHALLENGE-FI",
        "name": "Finland Challenge Requester",
        "roles": ["requester"],
        "allowed_market_ids": ["FI"],
    },
    "DEMO-CHALLENGE-APPROVER": {
        "user_id": "DEMO-CHALLENGE-APPROVER",
        "name": "Challenge Approver",
        "roles": ["approver"],
        "allowed_market_ids": None,
    },
    "DEMO-CHALLENGE-STEWARD": {
        "user_id": "DEMO-CHALLENGE-STEWARD",
        "name": "Challenge KPI Steward",
        "roles": ["steward"],
        "allowed_market_ids": None,
    },
}

MAX_UPDATE_ATTEMPTS = 3
_LLM_LIMITATIONS = (
    "LLM extraction is a proposal only; the confirmed guided form governs "
    "scope. Invalid or unrecognised IDs are preserved for review, never "
    "silently dropped."
)


class ChallengeService:
    def __init__(self, store, data: ChallengeData | None = None):
        self.store = store
        self._data = data

    @property
    def data(self) -> ChallengeData:
        if self._data is None:
            self._data = ChallengeData()
        return self._data


    def actors(self) -> dict:
        return {
            "actors": [
                {
                    "user_id": a["user_id"],
                    "name": a["name"],
                    "roles": list(a["roles"]),
                    "allowed_market_ids": (
                        a["allowed_market_ids"]
                        if a["allowed_market_ids"] is not None
                        else "all"
                    ),
                }
                for a in ACTORS.values()
            ],
            "simulated": True,
        }

    def _require_user(self, user_id: str, role: str | None = "requester"):
        actor = ACTORS.get(user_id)
        if actor is None:
            raise Forbidden("Unknown simulated challenge identity.")
        if role is not None and role not in actor["roles"]:
            raise Forbidden(
                f"Simulated identity '{user_id}' lacks the '{role}' role."
            )
        return actor

    def _check_market_scope(self, actor, market_ids):
        allowed = actor["allowed_market_ids"]
        if allowed is not None and not set(market_ids).issubset(set(allowed)):
            raise Forbidden("Requested markets are outside your scope.")


    def catalog(self, domain_id: str) -> dict:
        if domain_id not in CONTRACTS:
            raise SessionNotFound(f"unknown challenge domain '{domain_id}'")
        choices = self.data.choices(domain_id)
        return {
            "choices": choices,
            "domains": [
                {"domain_id": d, "name": c["name"], "grain": c["grain"]}
                for d, c in CONTRACTS.items()
            ],
        }

    def requests(self) -> dict:
        self.data.assert_current()
        return {
            "requests": self.data.tables["Business_Requests"],
            "note": (
                "Original source request rows. Context fields may conflict "
                "with the request text; the text and your confirmed form "
                "govern scope - context is not auto-truth."
            ),
        }

    def estate(self, user_id: str, query: str = "") -> dict:
        actor = self._require_user(user_id)
        if actor["allowed_market_ids"] is not None:
            raise Forbidden(
                "Estate records span all markets; only the global requester "
                "may search them."
            )
        self.data.assert_current()
        needle = (query or "").strip().lower()
        keys = ("asset_id", "asset_name", "product_scope", "market_scope",
                "platform")
        assets = []
        for row in self.data.tables["Analytics_Assets"]:
            if needle and not any(
                needle in str(row.get(k) or "").lower() for k in keys
            ):
                continue
            assets.append(row)
        return {"assets": assets, "count": len(assets), "query": query}

    def estate_asset(self, user_id: str, asset_id: str) -> dict:
        actor = self._require_user(user_id)
        if actor["allowed_market_ids"] is not None:
            raise Forbidden(
                "Estate records span all markets; only the global requester "
                "may inspect them."
            )
        evidence = self.data.estate_asset(asset_id)
        asset = evidence["asset"]
        workspace = next(
            (r for r in self.data.tables["Workspaces"]
             if r.get("workspace_id") == asset.get("workspace_id")),
            None,
        )
        return {
            **evidence,
            "workspace": workspace,
            "governance_rules": self.data.tables["Governance_Rules"],
            "owner_options": [
                {"owner_id": r["owner_id"], "owner_name": r["owner_name"]}
                for r in self.data.tables["Owners"]
                if r.get("status") == "active"
            ],
        }


    def _slim_choices(self, domain_id: str) -> dict:
        """Provider-safe choices: no owners, no source rows, no emails."""
        choices = self.data.choices(domain_id)
        return {
            "domain_id": domain_id,
            "data_classification": choices["data_classification"],
            "disclaimer": choices["disclaimer"],
            "grain": choices["grain"],
            "months": choices["months"],
            "products": [
                {"product_id": p["product_id"],
                 "product_name": p["product_name"]}
                for p in choices["products"]
            ],
            "markets": [
                {"market_id": m["market_id"],
                 "market_name": m["market_name"]}
                for m in choices["markets"]
            ],
            "metrics": [
                {
                    "metric_id": m["metric_id"],
                    "name": m["name"],
                    "unit": m["unit"],
                    "context_kpi_id": m["context_kpi_id"],
                    "aliases": m["aliases"],
                }
                for m in choices["metrics"]
            ],
            "model": choices["model"],
        }

    def extract(self, user_id: str, domain_id: str, text: str,
                use_llm: bool, llm=None) -> dict:
        self._require_user(user_id)
        if domain_id not in CONTRACTS:
            raise SessionNotFound(f"unknown challenge domain '{domain_id}'")
        choices = self.data.choices(domain_id)
        grain = choices["grain"]
        llm_error = None
        mode = "offline"
        if use_llm:
            try:
                extraction = self._extract_llm(domain_id, text, llm)
                mode = "llm"
            except LLMUnavailable as exc:
                llm_error = str(exc)
                extraction = parse_challenge_message(text, domain_id, choices)
                extraction["limitations"] = (
                    f"Live LLM unavailable ({llm_error}); offline fallback "
                    "was used. " + extraction["limitations"]
                )
                mode = "offline_fallback_after_llm_unavailable"
        else:
            extraction = parse_challenge_message(text, domain_id, choices)

        valid = {
            "product_ids": {p["product_id"] for p in choices["products"]},
            "market_ids": {m["market_id"] for m in choices["markets"]},
            "metric_ids": {m["metric_id"] for m in choices["metrics"]},
        }
        raw = dict(extraction.get("partial_intent") or {
            k: extraction.get(k) or [] for k in valid
        })
        raw_grain = raw.get("grain")
        proposed_intent = {
            "product_ids": sorted(set(raw.get("product_ids") or [])),
            "market_ids": sorted(set(raw.get("market_ids") or [])),
            "metric_ids": sorted(set(raw.get("metric_ids") or [])),
            "months": sorted(set(raw.get("months") or [])),
            "grain": raw_grain,
        }

        intent = {}
        invalid_ids = list(extraction.get("invalid_ids") or [])
        unsupported = list(extraction.get("unsupported") or [])
        for field, allowed in valid.items():
            kept, bad = [], []
            for value in proposed_intent[field]:
                (kept if value in allowed else bad).append(value)
            intent[field] = sorted(set(kept))
            for value in sorted(set(bad)):
                invalid_ids.append(f"{field}:{value}")

        coverage = set(choices["months"])
        unknown_months = [
            m for m in proposed_intent["months"] if m not in coverage
        ]
        if grain == "snapshot":
            intent["months"] = []
            if proposed_intent["months"]:
                unsupported.append(
                    "Dated periods cannot be applied to a snapshot source: "
                    + ", ".join(proposed_intent["months"])
                )
        else:
            intent["months"] = sorted(
                m for m in proposed_intent["months"] if m in coverage
            )
            if unknown_months:
                unsupported.append(
                    "Months outside source coverage: "
                    + ", ".join(sorted(set(unknown_months)))
                )
                unresolved_extra = {"months"}
            else:
                unresolved_extra = set()
        if raw_grain and raw_grain != grain:
            unsupported.append(
                f"Requested grain '{raw_grain}' is not available; this "
                f"source is {grain} grain only."
            )
        intent["grain"] = grain

        unresolved = set(extraction.get("unresolved") or [])
        for field in ("product_ids", "market_ids", "metric_ids"):
            if not intent[field]:
                unresolved.add(field)
        if grain != "snapshot" and (not intent["months"] or unresolved_extra):
            unresolved.add("months")
        unresolved |= unresolved_extra if grain != "snapshot" else set()

        return {
            "domain_id": domain_id,
            "partial_intent": intent,
            "proposed_intent": proposed_intent,
            "unresolved": sorted(unresolved),
            "questions": [
                f"Provide explicit {field} to proceed."
                for field in sorted(unresolved)
            ],
            "unsupported": sorted(set(unsupported)),
            "invalid_ids": sorted(set(invalid_ids)),
            "extraction_mode": mode,
            "limitations": extraction.get("limitations"),
            "llm_error": llm_error,
            "note": (
                "Extraction never creates a plan; confirm the guided form "
                "and submit it explicitly."
            ),
        }

    def _extract_llm(self, domain_id: str, text: str, llm) -> dict:
        if llm is None:
            from smart_librarian.llm.client import OpenAIIntentExtractor

            llm = OpenAIIntentExtractor()
        raw = llm.extract_intent(
            conversation=[text],
            catalog_choices=self._slim_choices(domain_id),
        )
        return {
            "partial_intent": {
                "product_ids": raw.get("product_ids") or [],
                "market_ids": raw.get("market_ids") or [],
                "metric_ids": raw.get("metric_ids") or [],
                "months": raw.get("months") or [],
                "grain": raw.get("grain"),
            },
            "unresolved": raw.get("unresolved") or [],
            "unsupported": raw.get("unsupported") or [],
            "invalid_ids": [],
            "limitations": _LLM_LIMITATIONS,
        }


    def create_report_plan(self, user_id: str, domain_id: str, intent: dict,
                           owner_id: str, rationale: str) -> dict:
        actor = self._require_user(user_id)
        if domain_id not in CONTRACTS:
            raise SessionNotFound(f"unknown challenge domain '{domain_id}'")
        self._check_market_scope(actor, list(intent.get("market_ids") or []))
        try:
            spec = self.data.report_spec(domain_id, intent, owner_id)
        except ValueError as exc:
            raise Conflict(str(exc)) from exc
        spec_hash = stable_hash(spec)
        existing = self.store.find_approved_challenge_plan(
            spec_hash, self.data.fingerprint
        )
        if existing is not None:
            self._check_plan_scope(actor, existing)
            return {"outcome": "REUSE", "plan": self._plan_view(existing)}
        plan = self.store.create_challenge_plan(
            requester=user_id, kind="report", domain_id=domain_id,
            spec=spec, spec_hash=spec_hash,
            fingerprint=self.data.fingerprint, rationale=rationale,
        )
        return {"outcome": "PENDING_APPROVAL", "plan": self._plan_view(plan)}

    def create_lifecycle_plan(self, user_id: str, asset_id: str, action: str,
                              target_asset_id, owner_id: str,
                              rationale: str) -> dict:
        actor = self._require_user(user_id)
        if actor["allowed_market_ids"] is not None:
            raise Forbidden(
                "Estate lifecycle proposals require the global requester."
            )
        try:
            spec = self.data.lifecycle_spec(
                asset_id, action, owner_id, rationale, target_asset_id
            )
        except ValueError as exc:
            raise Conflict(str(exc)) from exc
        spec_hash = stable_hash(spec)
        plan = self.store.create_challenge_plan(
            requester=user_id, kind="lifecycle", domain_id=None,
            spec=spec, spec_hash=spec_hash,
            fingerprint=self.data.fingerprint, rationale=rationale,
        )
        return {"outcome": "PENDING_APPROVAL", "plan": self._plan_view(plan)}


    def _plan_view(self, plan: dict) -> dict:
        view = dict(plan)
        if plan.get("kind") == "report":
            view["estate_candidates"] = self._estate_candidates(plan["spec"])
        view["audit"] = self.store.list_challenge_events(plan["plan_id"])
        return view

    def _visible(self, actor, plan: dict) -> bool:
        if actor["allowed_market_ids"] is None:
            return True
        if plan.get("kind") != "report":
            return plan["requester"] == actor["user_id"]
        markets = set(
            ((plan.get("spec") or {}).get("intent") or {})
            .get("market_ids") or []
        )
        return bool(markets) and markets.issubset(
            set(actor["allowed_market_ids"])
        )

    def _load_plan(self, plan_id: str):
        plan = self.store.get_challenge_plan(plan_id)
        if plan is None:
            raise SessionNotFound(plan_id)
        return plan

    def _check_plan_scope(self, actor, plan: dict):
        if plan.get("kind") == "report":
            intent = (plan.get("spec") or {}).get("intent") or {}
            self._check_market_scope(actor, intent.get("market_ids") or [])

    def list_plans(self, user_id: str) -> dict:
        actor = self._require_user(user_id)
        return {
            "plans": [
                self._plan_view(plan)
                for plan in self.store.list_challenge_plans()
                if self._visible(actor, plan)
            ]
        }

    def get_plan(self, user_id: str, plan_id: str) -> dict:
        actor = self._require_user(user_id)
        plan = self._load_plan(plan_id)
        if not self._visible(actor, plan):
            raise SessionNotFound(plan_id)
        self._check_plan_scope(actor, plan)
        return {"plan": self._plan_view(plan)}

    def _estate_candidates(self, spec: dict) -> list[dict]:
        intent = spec.get("intent") or {}
        product_ids = set(intent.get("product_ids") or [])
        names = {
            r["product_id"]: r["product_name"]
            for r in self.data.tables["Products"]
        }
        scopes = product_ids | {names.get(pid) for pid in product_ids}
        scopes.discard(None)
        markets = set(intent.get("market_ids") or [])
        candidates = []
        for row in self.data.tables["Analytics_Assets"]:
            if scopes and row.get("product_scope") not in scopes:
                continue
            if markets and row.get("market_scope") not in markets:
                continue
            candidates.append({
                "asset_id": row["asset_id"],
                "asset_name": row["asset_name"],
                "platform": row.get("platform"),
                "endorsement": row.get("endorsement"),
                "lifecycle_status": row.get("lifecycle_status"),
                "product_scope": row.get("product_scope"),
                "market_scope": row.get("market_scope"),
            })
            if len(candidates) >= 20:
                break
        return candidates


    _DECISION_STATUS = {"approve": "approved", "reject": "rejected"}

    def record_approval(self, user_id: str, plan_id: str, actor_user_id: str,
                        spec_hash: str, decision: str,
                        expected_revision: int) -> dict:
        self._require_user(user_id)
        self.data.assert_current()
        actor = ACTORS.get(actor_user_id)
        if actor is None:
            raise Forbidden("Unknown simulated governance actor.")
        if "approver" not in actor["roles"]:
            raise Forbidden(
                "This simulated actor is not an approver; stewards review "
                "but cannot approve."
            )
        if actor_user_id == user_id:
            raise Forbidden("Requester cannot approve their own plan.")
        target = self._DECISION_STATUS[decision]

        for _ in range(MAX_UPDATE_ATTEMPTS):
            plan = self._load_plan(plan_id)
            if plan["requester"] != user_id:
                raise Forbidden("Plan belongs to a different requester.")
            if plan["spec_hash"] != spec_hash:
                raise Conflict("Stale spec hash; reload the plan.")
            if plan["revision"] != expected_revision:
                raise Conflict("Stale plan revision; reload the plan.")
            if plan["source_fingerprint"] != self.data.fingerprint:
                raise Conflict(
                    "Source builder pack changed; this plan is no longer "
                    "valid."
                )
            if plan["status"] == target:
                return {"plan": self._plan_view(plan), "idempotent": True}
            if plan["status"] != "pending":
                raise Conflict(
                    f"Plan already '{plan['status']}'; the decision cannot "
                    "be changed."
                )
            try:
                self.data.assert_current()
                updated, superseded = self.store.decide_challenge_plan(
                    plan_id, expected_revision, target, plan["requester"],
                    plan["spec_hash"], plan["source_fingerprint"],
                    audit={
                        "user_id": actor_user_id,
                        "event_type": f"approval_{decision}",
                        "detail": {
                            "spec_hash": spec_hash,
                            "decision": decision,
                            "requester_user_id": user_id,
                        },
                    },
                )
            except RevisionConflict:
                self.data.assert_current()
                continue
            if superseded is not None:
                return {
                    "plan": self._plan_view(updated),
                    "idempotent": False,
                    "outcome": "REUSE",
                    "superseded_plan_id": superseded["plan_id"],
                }
            result = {"plan": self._plan_view(updated), "idempotent": False}
            if updated["kind"] == "lifecycle" and target == "approved":
                result["outcome"] = "approved proposal; not executed"
            return result
        raise Conflict(CONCURRENT_UPDATE_MESSAGE)


    def render(self, user_id: str, plan_id: str, spec_hash: str,
               expected_revision: int) -> dict:
        actor = self._require_user(user_id)
        self.data.assert_current()
        for _ in range(MAX_UPDATE_ATTEMPTS):
            plan = self._load_plan(plan_id)
            if not self._visible(actor, plan):
                raise SessionNotFound(plan_id)
            if plan["kind"] != "report":
                raise Conflict(
                    "Lifecycle plans are approved proposals; they are never "
                    "executed or rendered."
                )
            if plan["spec_hash"] != spec_hash:
                raise Conflict("Stale spec hash; reload the plan.")
            if plan["revision"] != expected_revision:
                raise Conflict("Stale plan revision; reload the plan.")
            if plan["status"] == "rendered" and plan.get("report"):
                return {"plan": self._plan_view(plan), "idempotent": True}
            if plan["status"] != "approved":
                raise Conflict(
                    f"Report cannot be rendered while the plan is "
                    f"'{plan['status']}'."
                )
            if plan["source_fingerprint"] != self.data.fingerprint:
                raise Conflict(
                    "Source builder pack changed; refusing to render."
                )
            self._check_plan_scope(actor, plan)
            try:
                report = self.data.render(plan["spec"])
            except ValueError as exc:
                raise Conflict(str(exc)) from exc
            report["approval_status"] = "approved"
            report["plan_id"] = plan_id
            report["requester"] = plan["requester"]
            try:
                updated = self.store.update_challenge_plan(
                    plan_id, expected_revision,
                    {"status": "rendered", "report_json": report},
                    audit={
                        "user_id": user_id,
                        "event_type": "report_rendered",
                        "detail": {"spec_hash": spec_hash},
                    },
                )
            except RevisionConflict:
                continue
            return {"plan": self._plan_view(updated), "idempotent": False}
        raise Conflict(CONCURRENT_UPDATE_MESSAGE)

    def get_report(self, user_id: str, plan_id: str) -> dict:
        actor = self._require_user(user_id)
        plan = self._load_plan(plan_id)
        if not self._visible(actor, plan):
            raise SessionNotFound(plan_id)
        self._check_plan_scope(actor, plan)
        if plan["kind"] != "report":
            raise Conflict("Lifecycle plans have no rendered report.")
        if plan["status"] != "rendered" or not plan.get("report"):
            raise Conflict(
                "No frozen report exists for this plan; render it after "
                "approval first."
            )
        return {"plan_id": plan_id, "report": plan["report"],
                "audit": self.store.list_challenge_events(plan_id)}
