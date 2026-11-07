import base64
import hashlib
import io
import json
import math
import zipfile

from smart_librarian.reporting.challenge_pbip_dashboard import (
    build_dashboard_files,
    model_presentation,
)

SCHEMA_ROOT = "https://developer.microsoft.com/json-schemas/fabric/"
PBIP_STATUS = (
    "Generated offline Power BI project using PBIR and a TMSL import model. "
    "Native domain charts, source-evidence and governance pages are included "
    "alongside the frozen source table. Frozen synthetic rows are embedded; "
    "no source connection, credentials, service publication or refresh "
    "pipeline. Run one Refresh if Desktop prompts for it; the embedded "
    "snapshot is loaded locally, not from any live connection. Templates "
    "checked with Power BI Desktop 2.159.1231.0; validate in your target "
    "version. "
    "Open the extracted GovernedReport.pbip in a compatible Power BI Desktop "
    "with project support and validate before deployment."
)


def _json(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2)


def _m_string(value):
    return '"' + value.replace("#", "#(#)").replace('"', '""') + '"'


def _column_type(values):
    present = [v for v in values if v is not None]
    if present and all(isinstance(v, bool) for v in present):
        return "boolean", "type logical"
    if present and all(isinstance(v, int) and not isinstance(v, bool) for v in present):
        if all(-(2**63) <= v < 2**63 for v in present):
            return "int64", "Int64.Type"
        raise ValueError("Integer outside the Power BI int64 range")
    if present and all(isinstance(v, (float, int)) and not isinstance(v, bool) for v in present):
        if not all(math.isfinite(v) for v in present):
            raise ValueError("Non-finite report values cannot be exported")
        return "double", "type number"
    if all(isinstance(v, str) for v in present):
        return "string", "type text"
    raise ValueError("Mixed or nested report-column values cannot be exported")


def build_challenge_pbip_files(report):
    spec = report.get("spec") or {}
    if spec.get("kind") != "report" or spec.get("data_classification") != "official_synthetic_challenge":
        raise ValueError("PBIP requires a frozen official synthetic challenge report")
    digest = hashlib.sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    if report.get("spec_hash") != digest:
        raise ValueError("Report specification hash does not match its frozen specification")
    rows = report.get("rows")
    if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
        raise ValueError("PBIP requires nonempty frozen report rows")
    if any(r.get("_source_sheet") != spec.get("source_sheet") for r in rows):
        raise ValueError("Report rows do not match the approved source sheet")
    provenance = report.get("source_provenance") or {}
    if provenance.get("source_sha256") != spec.get("source_sha256"):
        raise ValueError("Report provenance does not match its specification")
    names = list(rows[0])
    if not all(isinstance(name, str) and name for name in names):
        raise ValueError("Invalid frozen report columns")
    if any(set(row) != set(names) for row in rows):
        raise ValueError("Inconsistent frozen report columns")
    if "_source_row" not in names:
        raise ValueError("Source-row identity is required for nonaggregating visuals")
    source_rows = [r["_source_row"] for r in rows]
    if (not all(isinstance(n, int) and not isinstance(n, bool) and n >= 2 for n in source_rows)
            or len(set(source_rows)) != len(source_rows)):
        raise ValueError("Source-row identities must be unique worksheet row numbers")
    types = {name: _column_type([r[name] for r in rows]) for name in names}
    encoded = base64.b64encode(_json(rows).encode("utf-8")).decode("ascii")
    transforms = ", ".join("{" + _m_string(name) + ", " + types[name][1] + "}" for name in names)
    expression = [
        "let",
        f'    FrozenRows = Json.Document(Binary.FromText("{encoded}", BinaryEncoding.Base64)),',
        "    Source = Table.FromRecords(FrozenRows),",
        f'    Typed = Table.TransformColumnTypes(Source, {{{transforms}}}, "en-US")',
        "in",
        "    Typed",
    ]
    model = {
        "name": "GovernedReport",
        "compatibilityLevel": 1601,
        "model": {
            "culture": "en-US",
            "sourceQueryCulture": "en-US",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "description": PBIP_STATUS + " " + provenance.get("disclaimer", ""),
            "tables": [{
                "name": "FrozenReport",
                "description": "Source-row-identical synthetic values. No aggregations or implicit measures.",
                "columns": [
                    {"name": name, "dataType": types[name][0], "sourceColumn": name,
                     "summarizeBy": "none"}
                    for name in names
                ],
                "partitions": [{
                    "name": "FrozenReport", "mode": "import",
                    "source": {"type": "m", "expression": expression},
                }],
            }],
            "annotations": [
                {"name": "SourceSHA256", "value": spec["source_sha256"]},
                {"name": "GovernedSpecHash", "value": report.get("spec_hash", "")},
                {"name": "DataClassification", "value": "official_synthetic_challenge"},
            ],
        },
    }
    presentation_columns, measures, dashboard_fields = model_presentation(report, names, types)
    model["model"]["tables"][0]["columns"].extend(presentation_columns)
    model["model"]["tables"][0]["measures"] = measures
    report_dir = "GovernedReport.Report/"
    model_dir = "GovernedReport.SemanticModel/"
    files = {
        "GovernedReport.pbip": {
            "$schema": SCHEMA_ROOT + "pbip/pbipProperties/1.0.0/schema.json",
            "version": "1.0", "artifacts": [{"report": {"path": report_dir.rstrip("/")}}],
            "settings": {"enableAutoRecovery": True},
        },
        report_dir + "definition.pbir": {
            "$schema": SCHEMA_ROOT + "item/report/definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": {"byPath": {"path": "../" + model_dir.rstrip("/")}},
        },
        model_dir + "definition.pbism": {
            "$schema": SCHEMA_ROOT + "item/semanticModel/definitionProperties/1.0.0/schema.json",
            "version": "1.0", "settings": {"qnaEnabled": False},
        },
        model_dir + "model.bim": model,
        report_dir + "definition/version.json": {
            "$schema": SCHEMA_ROOT + "item/report/definition/versionMetadata/1.0.0/schema.json",
            "version": "2.0.0",
        },
        report_dir + "definition/report.json": {
            "$schema": SCHEMA_ROOT + "item/report/definition/report/3.0.0/schema.json",
            "themeCollection": {},
        },
        "governance/spec.json": spec,
        "governance/provenance.json": {
            **provenance, "power_bi_status": PBIP_STATUS,
            "spec_hash": report.get("spec_hash"),
            "approval_status": report.get("approval_status"),
            "aggregation": "none",
        },
        "governance/frozen_rows.json": rows,
    }
    files.update(build_dashboard_files(report, names, dashboard_fields))
    files["governance/desktop_handoff.json"] = {
        "instructions": [
            "Extract the full archive to a folder, keeping the .Report and "
            ".SemanticModel folders beside GovernedReport.pbip.",
            "Open GovernedReport.pbip in Power BI Desktop with project "
            "(PBIP) support.",
            "Run Refresh once: it loads the embedded frozen snapshot, not "
            "new business data.",
            "Use the Dashboard, Source Evidence and Ownership & Evidence "
            "tabs; chart measures return BLANK on multi-row contexts and "
            "are never summed or averaged.",
            "Identities, approvals and governance labels are local "
            "simulations; nothing here certifies equivalence or publishes "
            "to the Power BI service.",
        ],
    }
    return {name: _json(value).encode("utf-8") for name, value in files.items()}


def build_challenge_pbip_bundle(report):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(build_challenge_pbip_files(report).items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, content)
    return output.getvalue()
