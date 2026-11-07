"""Fixed simulated governance actor registry.

These are demo identities for role simulation only - not authentication, not
authorization against a real directory. Approval authority is demonstrated by
binding the approval decision to a separate simulated approver actor whose
roles and market scope are checked deterministically.
"""

ACTORS = {
    "DEMO-APPROVER": {
        "actor_id": "DEMO-APPROVER",
        "name": "Synthetic Governance Approver",
        "roles": ["approver"],
        "allowed_market_ids": ["DE", "FI", "FR"],
        "simulated": True,
    },
    "DEMO-STEWARD": {
        "actor_id": "DEMO-STEWARD",
        "name": "Synthetic Catalog Steward",
        "roles": ["steward"],
        "allowed_market_ids": ["DE", "FI", "FR"],
        "simulated": True,
    },
    "DEMO-PUBLIC-APPROVER": {
        "actor_id": "DEMO-PUBLIC-APPROVER",
        "name": "Demo Public-data Approver",
        "roles": ["approver"],
        "allowed_market_ids": ["GLOBAL"],
        "simulated": True,
    },
}

DEFAULT_APPROVER_ID = "DEMO-APPROVER"


def actor(actor_id: str) -> dict | None:
    return ACTORS.get(actor_id)


def actors() -> list[dict]:
    return [dict(value) for value in ACTORS.values()]


def approval_gaps(actor_record: dict, requester_user_id: str,
                  market_ids) -> list[str]:
    """Reasons an actor may not decide a proposal; empty means permitted."""
    gaps = []
    if actor_record.get("actor_id") == requester_user_id:
        gaps.append("requester_cannot_self_approve")
    if "approver" not in (actor_record.get("roles") or []):
        gaps.append("actor_not_approver")
    allowed = set(actor_record.get("allowed_market_ids") or [])
    if not set(market_ids or []).issubset(allowed):
        gaps.append("actor_market_scope")
    return gaps
