"""Frozen challenge-render exports: HTML, CSV, ZIP and a manual import kit.

Serializes only values already present in a frozen engine render - nothing
is recomputed, aggregated or rescaled. CSV cells are formula-injection
safe via the shared serializer. The Power Query kit is a manual CSV+M
import kit only: it is NOT a PBIP/PBIX project and publishes nothing.
"""

import html
import io
import json
import zipfile

from smart_librarian.reporting.powerbi import (
    _THEME,
    _m_query,
    serialize_rows_csv,
)


def _e(value) -> str:
    return html.escape(str(value))


def _headers(report: dict) -> list[str]:
    spec = report.get("spec") or {}
    intent = spec.get("intent") or {}
    metric_ids = list(intent.get("metric_ids") or [])
    extra = [
        column for column in ("month", "milestone_date", "value_type",
                              "synthetic_record")
        if any(column in row for row in (report.get("rows") or []))
    ]
    return (
        ["product_id", "product_name", "market_id", "market_name"]
        + extra + metric_ids + ["_source_sheet", "_source_row"]
    )


def challenge_rows_csv(report: dict) -> str:
    return serialize_rows_csv(report.get("rows") or [], _headers(report))


def challenge_report_html(report: dict, audit: list[dict] | None = None) -> str:
    spec = report.get("spec") or {}
    intent = spec.get("intent") or {}
    rows = report.get("rows") or []
    units = report.get("units") or {}
    headers = _headers(report)
    names = {
        field["metric_id"]: field.get("name") or field["metric_id"]
        for field in spec.get("fields") or []
    }
    thead = "".join(
        f"<th scope='col'>{_e(names.get(h, h))}"
        f"{f' ({_e(units[h])})' if units.get(h) else ''}</th>"
        for h in headers
    )
    body = "".join(
        "<tr>" + "".join(
            f"<td>{_e(row.get(h))}</td>" for h in headers
        ) + "</tr>"
        for row in rows
    )
    provenance = {
        "domain_id": spec.get("domain_id"),
        "grain": intent.get("grain"),
        "spec_hash": report.get("spec_hash"),
        "owner_id": spec.get("owner_id"),
        **(report.get("source_provenance") or {}),
        "aggregation": spec.get("aggregation"),
        "semantic_note": spec.get("semantic_note"),
    }
    prov_rows = "".join(
        f"<tr><th scope='row'>{_e(k)}</th><td>{_e(v)}</td></tr>"
        for k, v in provenance.items() if v is not None
    )
    embedded = (
        json.dumps(
            {"spec": spec, "quality_checks": report.get("quality_checks"),
             "audit": audit or []},
            sort_keys=True,
        )
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Challenge report - {_e(spec.get('domain_id'))}</title>
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 24px;
  background: #f5f8fa; color: #23201a; }}
.banner {{ background: #0f3557; color: #e8f0f4; padding: 8px 14px;
  border-radius: 6px; font-size: 0.9rem; }}
table {{ border-collapse: collapse; width: 100%; background: #fff; }}
th, td {{ border: 1px solid #d5e0e6; padding: 6px 10px; text-align: left;
  font-size: 0.85rem; }}
h1, h2 {{ color: #0f3557; }}
</style></head><body>
<div class="banner">{_e((report.get('source_provenance') or {}).get('disclaimer', 'Official synthetic challenge builder pack.'))} Local preview artifact only.</div>
<h1>Challenge report: {_e(spec.get('domain_id'))}</h1>
<table><caption>Frozen source rows (no aggregation)</caption>
<thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table>
<h2>Provenance</h2>
<table><tbody>{prov_rows}</tbody></table>
<h2>Specification and audit</h2>
<script type="application/json" id="spec">{embedded}</script>
</body></html>
"""


def challenge_bundle(report: dict, audit: list[dict] | None = None) -> bytes:
    """ZIP: report.html, report.csv, spec/evidence/audit JSON, README."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.html", challenge_report_html(report, audit))
        archive.writestr("report.csv", challenge_rows_csv(report))
        archive.writestr(
            "specification.json",
            json.dumps(
                {
                    "spec": report.get("spec"),
                    "spec_hash": report.get("spec_hash"),
                    "units": report.get("units"),
                    "quality_checks": report.get("quality_checks"),
                    "source_provenance": report.get("source_provenance"),
                    "audit": audit or [],
                },
                indent=2, sort_keys=True,
            ),
        )
        archive.writestr(
            "README.txt",
            "Challenge report bundle - official synthetic builder pack.\n"
            "Frozen source rows only; nothing is recomputed, joined or "
            "aggregated. Native workbook units and value_type are "
            "preserved; forecast-like rows are not actuals.\n",
        )
    return buffer.getvalue()


def challenge_import_kit(report: dict) -> bytes:
    """Typed Power Query M + CSV manual-import kit - NOT PBIP/PBIX."""
    rows = report.get("rows") or []
    units = report.get("units") or {}
    headers = _headers(report)
    typed = []
    for header in headers:
        if header in ("month", "milestone_date"):
            typed.append((header, "type text"))
        elif header == "synthetic_record":
            typed.append((header, "type logical"))
        elif header in units and units[header] not in (
            "category", "identifier"
        ):
            typed.append((header, "type number"))
        elif header == "_source_row":
            typed.append((header, "Int64.Type"))
        else:
            typed.append((header, "type text"))
    readme = (
        "Challenge report - Power BI manual import kit\n"
        "===============================================\n\n"
        "This kit is NOT a .pbip project or .pbix file and nothing here\n"
        "publishes to the Power BI service. It is frozen source rows plus a\n"
        "typed Power Query (M) script for manual CSV import only.\n\n"
        "Import: extract, then Home > Get data > Blank query > Advanced\n"
        "editor; paste PowerQuery_Report.m and adjust FolderPath. Keep the\n"
        "numeric field columns at 'Don't summarize' - rows are native\n"
        "source values, never to be summed into totals.\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.csv", serialize_rows_csv(rows, headers))
        archive.writestr("PowerQuery_Report.m", _m_query("report.csv", typed))
        archive.writestr("theme.json", json.dumps(_THEME, indent=2))
        archive.writestr("README.txt", readme)
    return buffer.getvalue()
