"""Runtime persistence: sessions, approvals and audit events in SQLite.

This store is separate from the read-only demo fixture and never mutates it.
Mutations run inside IMMEDIATE transactions with a session revision used for
compare-and-swap so concurrent updates cannot silently lose state.
"""

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS generated_reports (
    asset_id TEXT PRIMARY KEY,
    identity_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    dataset_fingerprint TEXT NOT NULL,
    model_id TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    spec_hash TEXT NOT NULL,
    metric_ids_json TEXT NOT NULL,
    coverage_json TEXT NOT NULL,
    grain TEXT NOT NULL,
    lifecycle_status TEXT NOT NULL,
    endorsement TEXT NOT NULL,
    destination_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS challenge_plans (
    plan_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL,
    requester TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    domain_id TEXT,
    spec_hash TEXT,
    source_fingerprint TEXT,
    spec_json TEXT NOT NULL,
    report_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS challenge_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RevisionConflict(Exception):
    """Raised when a session changed between read and write."""


class PublicationRejected(Exception):
    """Raised when a render can no longer publish against the live session."""


class RuntimeStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(_SCHEMA)
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def create_session(self, user_id: str, domain_id: str = "sales") -> dict:
        session_id = str(uuid.uuid4())
        now = _now()
        state = {
            "session_id": session_id,
            "user_id": user_id,
            "domain_id": domain_id,
            "outcome": None,
            "messages": [],
            "partial_intent": {},
            "questions": [],
            "unsupported": [],
            "evidence": [],
            "proposal": None,
            "extraction_mode": None,
            "limitations": None,
        }
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO sessions (session_id, user_id, revision, state_json,"
                " created_at, updated_at) VALUES (?, ?, 0, ?, ?, ?)",
                (session_id, user_id, json.dumps(state), now, now),
            )
            connection.commit()
        return state

    def get_session(self, session_id: str) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT revision, state_json FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        state = json.loads(row["state_json"])
        state["revision"] = row["revision"]
        return state

    def update_state(self, session_id: str, expected_revision: int, state: dict,
                     audit: dict | None = None) -> None:
        """CAS update of the session row plus an optional audit event."""
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE sessions SET state_json = ?, revision = revision + 1,"
                " updated_at = ? WHERE session_id = ? AND revision = ?",
                (json.dumps({k: v for k, v in state.items() if k != "revision"}),
                 _now(), session_id, expected_revision),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise RevisionConflict(session_id)
            if audit is not None:
                connection.execute(
                    "INSERT INTO audit_events (session_id, user_id, event_type,"
                    " detail, created_at) VALUES (?, ?, ?, ?, ?)",
                    (session_id, audit["user_id"], audit["event_type"],
                     json.dumps(audit["detail"]), _now()),
                )
            connection.commit()

    def append_audit(self, session_id: str, user_id: str, event_type: str,
                     detail: dict) -> None:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO audit_events (session_id, user_id, event_type,"
                " detail, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, user_id, event_type, json.dumps(detail), _now()),
            )
            connection.commit()

    # -- generated report registry -------------------------------------------

    @staticmethod
    def _decode_report(row: sqlite3.Row) -> dict:
        record = dict(row)
        record["metric_ids"] = json.loads(record.pop("metric_ids_json"))
        record["coverage"] = json.loads(record.pop("coverage_json"))
        record["destination"] = json.loads(record.pop("destination_json"))
        record["spec"] = json.loads(record.pop("spec_json"))
        return record

    def get_generated_report(self, asset_id: str) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM generated_reports WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
        return self._decode_report(row) if row else None

    def list_generated_reports(self) -> list[dict]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM generated_reports ORDER BY created_at, asset_id"
            ).fetchall()
        return [self._decode_report(row) for row in rows]

    def publish_report(self, session_id: str, expected_revision: int,
                       audit_user_id: str, asset: dict) -> tuple[dict, bool]:
        """Atomically register a rendered asset against the live session.

        Re-verifies the session revision, proposal id/hash and approval inside
        an IMMEDIATE transaction so a stale render cannot publish. Dedup is by
        the deterministic identity_key; a repeat render returns the existing
        record without a second registration audit event.
        """
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT revision, state_json FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None or row["revision"] != expected_revision:
                connection.rollback()
                raise PublicationRejected(session_id)
            proposal = (json.loads(row["state_json"]).get("proposal") or {})
            if (
                proposal.get("proposal_id") != asset["source_proposal_id"]
                or proposal.get("spec_hash") != asset["spec_hash"]
                or proposal.get("approval_status") not in ("approved", "not_required")
            ):
                connection.rollback()
                raise PublicationRejected(session_id)
            existing = connection.execute(
                "SELECT * FROM generated_reports WHERE identity_key = ?",
                (asset["identity_key"],),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return self._decode_report(existing), False
            now = _now()
            connection.execute(
                "INSERT INTO generated_reports (asset_id, identity_key, name,"
                " owner_id, created_by, created_at, updated_at,"
                " dataset_fingerprint, model_id, spec_json, spec_hash,"
                " metric_ids_json, coverage_json, grain, lifecycle_status,"
                " endorsement, destination_json) VALUES"
                " (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    asset["asset_id"], asset["identity_key"], asset["name"],
                    asset["owner_id"], asset["created_by"], now, now,
                    asset["dataset_fingerprint"], asset["model_id"],
                    json.dumps(asset["spec"]), asset["spec_hash"],
                    json.dumps(asset["metric_ids"]),
                    json.dumps(asset["coverage"]), asset["grain"],
                    asset["lifecycle_status"], asset["endorsement"],
                    json.dumps(asset["destination"]),
                ),
            )
            connection.execute(
                "INSERT INTO audit_events (session_id, user_id, event_type,"
                " detail, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, audit_user_id, "report_asset_registered",
                 json.dumps({
                     "asset_id": asset["asset_id"],
                     "identity_key": asset["identity_key"],
                     "proposal_id": asset["source_proposal_id"],
                     "spec_hash": asset["spec_hash"],
                 }), now),
            )
            connection.commit()
        stored = self.get_generated_report(asset["asset_id"])
        return stored, True

    @staticmethod
    def _decode_plan(row: sqlite3.Row) -> dict:
        record = dict(row)
        record["spec"] = json.loads(record.pop("spec_json"))
        report = record.pop("report_json")
        record["report"] = json.loads(report) if report else None
        return record

    def create_challenge_plan(self, requester: str, kind: str, domain_id,
                              spec: dict, spec_hash, fingerprint,
                              rationale: str = "") -> dict:
        plan_id = str(uuid.uuid4())
        now = _now()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO challenge_plans (plan_id, revision, requester,"
                " kind, status, domain_id, spec_hash, source_fingerprint,"
                " spec_json, report_json, created_at, updated_at) VALUES"
                " (?, 0, ?, ?, 'pending', ?, ?, ?, ?, NULL, ?, ?)",
                (plan_id, requester, kind, domain_id, spec_hash, fingerprint,
                 json.dumps(spec, sort_keys=True), now, now),
            )
            connection.execute(
                "INSERT INTO challenge_events (plan_id, user_id, event_type,"
                " detail, created_at) VALUES (?, ?, ?, ?, ?)",
                (plan_id, requester, "plan_created",
                 json.dumps({"kind": kind, "spec_hash": spec_hash,
                             "rationale": rationale}), now),
            )
            connection.commit()
        return self.get_challenge_plan(plan_id)

    def get_challenge_plan(self, plan_id: str) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM challenge_plans WHERE plan_id = ?", (plan_id,),
            ).fetchone()
        return self._decode_plan(row) if row else None

    def list_challenge_plans(self) -> list[dict]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM challenge_plans ORDER BY created_at, plan_id"
            ).fetchall()
        return [self._decode_plan(row) for row in rows]

    def find_approved_challenge_plan(self, spec_hash: str,
                                     fingerprint: str) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM challenge_plans WHERE spec_hash = ? AND"
                " source_fingerprint = ? AND status IN ('approved','rendered')"
                " ORDER BY created_at LIMIT 1",
                (spec_hash, fingerprint),
            ).fetchone()
        return self._decode_plan(row) if row else None

    def update_challenge_plan(self, plan_id: str, expected_revision: int,
                              fields: dict, audit: dict) -> dict:
        """CAS status/spec/report transition plus an audit event."""
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = [
            json.dumps(value, sort_keys=True)
            if key in ("spec_json", "report_json") else value
            for key, value in fields.items()
        ]
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                f"UPDATE challenge_plans SET {assignments},"
                " revision = revision + 1, updated_at = ?"
                " WHERE plan_id = ? AND revision = ?",
                (*values, _now(), plan_id, expected_revision),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise RevisionConflict(plan_id)
            connection.execute(
                "INSERT INTO challenge_events (plan_id, user_id, event_type,"
                " detail, created_at) VALUES (?, ?, ?, ?, ?)",
                (plan_id, audit["user_id"], audit["event_type"],
                 json.dumps(audit["detail"]), _now()),
            )
            connection.commit()
        return self.get_challenge_plan(plan_id)

    def decide_challenge_plan(self, plan_id: str, expected_revision: int,
                              target: str, requester: str, spec_hash: str,
                              fingerprint: str,
                              audit: dict) -> tuple[dict, dict | None]:
        """Atomic approval/reject with report dedup coalescing.

        For an approve decision on a report plan, another already
        approved/rendered plan with the same spec_hash + source fingerprint
        wins inside the same IMMEDIATE transaction: this plan becomes
        'superseded' with a duplicate_reused audit event and the winner is
        returned as (winner, loser). Otherwise the decision is applied and
        (plan, None) is returned.
        """
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT kind, status FROM challenge_plans WHERE plan_id = ?"
                " AND revision = ? AND status = 'pending' AND spec_hash = ?"
                " AND source_fingerprint = ? AND requester = ?",
                (plan_id, expected_revision, spec_hash, fingerprint,
                 requester),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise RevisionConflict(plan_id)
            winner_row = None
            if target == "approved" and row["kind"] == "report":
                winner_row = connection.execute(
                    "SELECT * FROM challenge_plans WHERE spec_hash = ? AND"
                    " source_fingerprint = ? AND plan_id != ? AND"
                    " status IN ('approved','rendered')"
                    " ORDER BY created_at LIMIT 1",
                    (spec_hash, fingerprint, plan_id),
                ).fetchone()
            now = _now()
            if winner_row is not None:
                cursor = connection.execute(
                    "UPDATE challenge_plans SET status = 'superseded',"
                    " revision = revision + 1, updated_at = ?"
                    " WHERE plan_id = ? AND revision = ?"
                    " AND status = 'pending'",
                    (now, plan_id, expected_revision),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    raise RevisionConflict(plan_id)
                connection.execute(
                    "INSERT INTO challenge_events (plan_id, user_id,"
                    " event_type, detail, created_at) VALUES"
                    " (?, ?, 'duplicate_reused', ?, ?)",
                    (plan_id, audit["user_id"],
                     json.dumps({"winner_plan_id": winner_row["plan_id"],
                                 "spec_hash": spec_hash}), now),
                )
                connection.commit()
                return (
                    self._decode_plan(winner_row),
                    self.get_challenge_plan(plan_id),
                )
            cursor = connection.execute(
                "UPDATE challenge_plans SET status = ?, revision = revision + 1,"
                " updated_at = ? WHERE plan_id = ? AND revision = ?"
                " AND status = 'pending'",
                (target, now, plan_id, expected_revision),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise RevisionConflict(plan_id)
            connection.execute(
                "INSERT INTO challenge_events (plan_id, user_id, event_type,"
                " detail, created_at) VALUES (?, ?, ?, ?, ?)",
                (plan_id, audit["user_id"], audit["event_type"],
                 json.dumps(audit["detail"]), now),
            )
            connection.commit()
        return self.get_challenge_plan(plan_id), None

    def append_challenge_event(self, plan_id: str, user_id: str,
                             event_type: str, detail: dict) -> None:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO challenge_events (plan_id, user_id, event_type,"
                " detail, created_at) VALUES (?, ?, ?, ?, ?)",
                (plan_id, user_id, event_type, json.dumps(detail), _now()),
            )
            connection.commit()

    def list_challenge_events(self, plan_id: str) -> list[dict]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT user_id, event_type, detail, created_at FROM"
                " challenge_events WHERE plan_id = ? ORDER BY id",
                (plan_id,),
            ).fetchall()
        return [
            {
                "user_id": row["user_id"],
                "event_type": row["event_type"],
                "detail": json.loads(row["detail"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def list_audit(self, session_id: str) -> list[dict]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT user_id, event_type, detail, created_at FROM audit_events"
                " WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [
            {
                "user_id": row["user_id"],
                "event_type": row["event_type"],
                "detail": json.loads(row["detail"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
