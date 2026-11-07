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
