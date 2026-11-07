"""Read-only access to frozen evidence files for the demo UI.

Two independent artifacts live under ``data/evidence`` (resolved from the
repository root, never from DEMO_DATA_DIR):

- ``challenge_estate.json`` - the official SinceAI builder-pack estate
  (entirely synthetic metadata; source rows preserved without repair).
- ``public_financials.json`` - selected public, reported product sales.

These files are public or synthetic evidence only. They are not secured
company systems and contain no user data. This module only reads them -
it never writes, repairs, recomputes or aggregates their contents.
"""

import json
import math
import re
from pathlib import Path
from urllib.parse import urlparse

from smart_librarian.settings import REPO_ROOT

EVIDENCE_DIR = REPO_ROOT / "data" / "evidence"

_FILES = {
    "challenge": "challenge_estate.json",
    "public": "public_financials.json",
}

_EXPECTED_CLASSIFICATION = {
    "challenge": "official_synthetic_challenge",
    "public": "public_reported_actual",
}

_CHALLENGE_TABLES = (
    "Analytics_Assets", "Semantic_Models", "Owners", "KPI_Catalog",
    "Asset_KPI_Map", "Asset_Usage", "Lineage_Edges", "Governance_Signals",
    "Migration_Backlog", "Data_Quality", "Governance_Rules",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PUBLIC_URL_HOST = "reports.bayer.com"


class EvidenceError(Exception):
    """Raised when an evidence file is missing or fails validation."""


def _check_metadata(kind: str, name: str, payload: dict) -> None:
    if payload.get("data_classification") != _EXPECTED_CLASSIFICATION[kind]:
        raise EvidenceError(
            f"evidence file '{name}' has unexpected data_classification "
            f"{payload.get('data_classification')!r}; expected "
            f"{_EXPECTED_CLASSIFICATION[kind]!r}"
        )
    for field in ("disclaimer", "retrieved_at_utc"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise EvidenceError(
                f"evidence file '{name}' is missing '{field}'"
            )
    sha = payload.get("source_sha256")
    if not isinstance(sha, str) or not _SHA256_RE.match(sha):
        raise EvidenceError(
            f"evidence file '{name}' has an invalid 'source_sha256'"
        )


def _check_challenge(payload: dict) -> None:
    tables = payload.get("tables")
    if not isinstance(tables, dict):
        raise EvidenceError(
            "evidence file 'challenge_estate.json' is missing a valid "
            "'tables' container"
        )
    for table in _CHALLENGE_TABLES:
        rows = tables.get(table)
        if not isinstance(rows, list) or not all(
            isinstance(row, dict) for row in rows
        ):
            raise EvidenceError(
                f"evidence file 'challenge_estate.json' table '{table}' "
                "is missing or is not a list of records"
            )
    if not isinstance(payload.get("source_file"), str) or not payload["source_file"]:
        raise EvidenceError(
            "evidence file 'challenge_estate.json' is missing 'source_file'"
        )


def _check_public(payload: dict) -> None:
    for field in ("unit", "grain", "source_url", "source_title",
                  "source_snapshot"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise EvidenceError(
                f"evidence file 'public_financials.json' is missing '{field}'"
            )
    url = urlparse(payload["source_url"])
    if url.scheme != "https" or url.hostname != _PUBLIC_URL_HOST:
        raise EvidenceError(
            "evidence file 'public_financials.json' has an unexpected "
            "'source_url'; only the reviewed https reports.bayer.com "
            "source is accepted"
        )
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise EvidenceError(
            "evidence file 'public_financials.json' is missing a non-empty "
            "'rows' list"
        )
    seen = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise EvidenceError(
                f"evidence file 'public_financials.json' row {index} is "
                "not a record"
            )
        for field in ("product_name", "source_table", "source_row_label"):
            if not isinstance(row.get(field), str) or not row[field]:
                raise EvidenceError(
                    f"evidence file 'public_financials.json' row {index} "
                    f"is missing '{field}'"
                )
        year = row.get("year")
        if isinstance(year, bool) or not isinstance(year, int):
            raise EvidenceError(
                f"evidence file 'public_financials.json' row {index} has "
                "an invalid 'year'"
            )
        sales = row.get("sales_eur_million")
        if (isinstance(sales, bool)
                or not isinstance(sales, (int, float))
                or not math.isfinite(sales)):
            raise EvidenceError(
                f"evidence file 'public_financials.json' row {index} has "
                "an invalid 'sales_eur_million'"
            )
        key = (row["product_name"], year)
        if key in seen:
            raise EvidenceError(
                f"evidence file 'public_financials.json' has a duplicate "
                f"product/year row: {key}"
            )
        seen.add(key)


def load_evidence(kind: str) -> dict:
    """Load and validate one frozen evidence file.

    ``kind`` must be ``challenge`` or ``public``. Raises EvidenceError on
    a missing file, malformed JSON, an unexpected data_classification or
    any broken structural shape. On success the parsed payload is
    returned unmodified.
    """
    if kind not in _FILES:
        raise EvidenceError(f"unknown evidence kind '{kind}'")
    name = _FILES[kind]
    path = EVIDENCE_DIR / name
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EvidenceError(
            f"evidence file '{name}' is not available"
        ) from exc
    except ValueError as exc:
        raise EvidenceError(
            f"evidence file '{name}' is not valid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise EvidenceError(f"evidence file '{name}' is not an object")
    _check_metadata(kind, name, payload)
    if kind == "challenge":
        _check_challenge(payload)
    else:
        _check_public(payload)
    return payload
