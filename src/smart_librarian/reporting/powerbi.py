"""Power BI import kit: frozen report values serialized for manual import.

These functions only serialize values already present in a render result
(or a frozen evidence payload). They never recompute, aggregate, sum or
rescale figures - a percent value of 5.85 stays 5.85 on the 0-100 scale.

Honest limitation: an import kit is a folder of CSV files plus ready-made
Power Query (M) scripts and a theme. It is NOT a .pbip project or .pbix
file, and nothing here publishes to the Power BI service.
"""

import csv
import io
import json
import zipfile

FOLDER_PATH_PLACEHOLDER = "C:\\SmartLibrarianExport"

_DIMENSION_BASE = [
    "product_id", "product_name", "market_id", "market_name",
]

_SOURCE_LABEL_HEADERS = ["source_table", "source_row_label"]
_SOURCE_DETAIL_HEADERS = ["source_id", "source_column", "source_row"]

_TIME_M_TYPES = {
    "fiscal_year": "Int64.Type",
    "period": "type text",
}

_THEME = {
    "name": "Smart Librarian",
    "dataColors": [
        "#0F3557", "#0E7C7B", "#4C9A9C", "#D9A441", "#7A9CC6",
        "#5A6B7A", "#B4522B", "#88A65E",
    ],
    "background": "#FFFFFF",
    "foreground": "#0F3557",
    "tableAccent": "#0E7C7B",
    "textClasses": {
        "title": {"fontSize": 14, "fontFace": "Segoe UI Semibold",
                  "color": "#0F3557"},
        "header": {"fontSize": 11, "fontFace": "Segoe UI Semibold",
                   "color": "#0F3557"},
        "label": {"fontSize": 10, "fontFace": "Segoe UI",
                  "color": "#33424F"},
    },
}


def _safe_cell(value):
    """Serialize one CSV cell.

    String cells get a spreadsheet formula-injection mitigation: control
    characters (tab/CR/LF) are flattened to spaces first, then a value
    whose first non-whitespace character is ``= + - @`` gets a
    single-quote prefix. Numbers and None are never modified (None
    serializes as an empty cell -> null on import).
    """
    if value is None:
        return ""
    if isinstance(value, str):
        flattened = (
            value.replace("\t", " ").replace("\r", " ").replace("\n", " ")
        )
        probe = flattened.lstrip()
        if probe and probe[0] in ("=", "+", "-", "@"):
            return "'" + flattened
        return flattened
    return value


def serialize_rows_csv(rows: list[dict], headers: list[str]) -> str:
    """Serialize frozen rows to CSV text with the cell safety rules above."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_safe_cell(row.get(header)) for header in headers])
    return buffer.getvalue()


def _m_string(value: str) -> str:
    """Encode a Python string as a safe M string literal."""
    return '"' + value.replace("#(", "#(#)(").replace('"', '""') + '"'


def _m_query(file_name: str, typed_columns: list[tuple[str, str]]) -> str:
    """A typed CSV import query. Missing values stay null; nothing is summed."""
    column_names = ", ".join(_m_string(name) for name, _ in typed_columns)
    typing = ",\n        ".join(
        f"{{{_m_string(name)}, {mtype}}}" for name, mtype in typed_columns
    )
    return f"""let
    FolderPath = {_m_string(FOLDER_PATH_PLACEHOLDER)},
    Source = Csv.Document(
        File.Contents(FolderPath & "\\{file_name}"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    WithNulls = Table.ReplaceValue(Promoted, "", null, Replacer.ReplaceValue, {{{column_names}}}),
    Typed = Table.TransformColumnTypes(WithNulls, {{
        {typing}
    }}, "en-US")
in
    Typed
"""


def _provenance(report: dict) -> dict:
    spec = report.get("spec") or {}
    asset = report.get("asset") or {}
    return {
        "spec": spec,
        "spec_hash": report.get("spec_hash"),
        "dataset_fingerprint": spec.get("dataset_fingerprint"),
        "proposal_id": report.get("proposal_id"),
        "approval_status": report.get("approval_status"),
        "outcome": report.get("outcome"),
        "source_asset_id": report.get("source_asset_id"),
        "registered_asset_id": report.get("registered_asset_id"),
        "asset_name": asset.get("name"),
        "owner": asset.get("owner_name") or asset.get("owner_id"),
        "units": report.get("units") or {},
        "time_column": report.get("time_column") or "month",
        "data_classification": report.get("data_classification"),
        "source_provenance": report.get("source_provenance"),
        "data_disclaimer": (
            "All values are published actual public sales figures in EUR "
            "million, copied verbatim from the frozen public source; "
            "approval and registry metadata are simulated, not Bayer "
            "certification. This kit is not a PBIP/PBIX file and does not "
            "publish to the Power BI service."
            if report.get("data_classification") == "public_reported_actual"
            or report.get("synthetic_record") is False
            else
            "All values are synthetic fixture figures produced by the fixed "
            "calculation engine, copied here verbatim. Percent values are on "
            "a 0-100 scale, not fractional. This kit is not a PBIP/PBIX file "
            "and does not publish to the Power BI service."
        ),
    }


def build_powerbi_import_bundle(report: dict) -> bytes:
    """Zip kit: CSVs + M queries + theme + provenance + README.

    Fixed contents: report.csv, totals.csv, PowerQuery_Report.m,
    PowerQuery_Totals.m, theme.json, provenance.json, README.txt.
    """
    rows = report.get("rows") or []
    totals = report.get("totals") or {}
    units = report.get("units") or {}
    metric_ids = list(totals) or list(units)
    time_column = report.get("time_column") or "month"
    is_public = (
        report.get("data_classification") == "public_reported_actual"
        or report.get("synthetic_record") is False
    )

    source_detail_headers = [
        header for header in _SOURCE_DETAIL_HEADERS
        if any(row.get(header) is not None for row in rows)
    ]
    headers = _DIMENSION_BASE + [time_column] + metric_ids
    if is_public:
        headers += _SOURCE_LABEL_HEADERS + source_detail_headers
    report_csv = serialize_rows_csv(rows, headers)
    totals_csv = serialize_rows_csv(
        [totals] if totals else [], metric_ids
    )

    time_type = _TIME_M_TYPES.get(time_column, "type date")
    report_typed = (
        [("product_id", "type text"), ("product_name", "type text"),
         ("market_id", "type text"), ("market_name", "type text"),
         (time_column, time_type)]
        + [(metric_id, "type number") for metric_id in metric_ids]
    )
    if is_public:
        report_typed += (
            [("source_table", "type text"),
             ("source_row_label", "type text")]
            + [(header, "type text") for header in source_detail_headers]
        )
    report_m = _m_query("report.csv", report_typed)
    totals_m = _m_query(
        "totals.csv",
        [(metric_id, "type number") for metric_id in metric_ids],
    )

    unit_lines = "\n".join(
        f"  {metric_id}: {units.get(metric_id) or 'value'}"
        for metric_id in metric_ids
    ) or "  (none)"
    span_word = (
        "cross-year" if time_column == "fiscal_year" else "cross-period"
    )
    if totals:
        totals_description = (
            "  totals.csv            The single frozen totals row produced by\n"
            "                        the calculation engine. Use this for\n"
            "                        headline numbers - do NOT re-sum report.csv\n"
            "                        columns.\n"
        )
    else:
        totals_description = (
            "  totals.csv            Header row only - this report spans\n"
            "                        multiple periods and there is deliberately\n"
            f"                        no {span_word} aggregate to carry.\n"
        )
    totals_note = ""
    if not totals:
        totals_note = (
            "                        NOTE: no data rows - the totals query\n"
            "                        imports headers only.\n"
        )
    if is_public:
        totals_note += (
            "                        Figures stay in EUR million; nothing is\n"
            "                        rescaled to EUR.\n"
        )
    data_note = (
        "published actual public data" if is_public
        else "synthetic demo data"
    )
    readme = f"""Smart Librarian - Power BI import kit ({data_note})
================================================================

This kit is NOT a .pbip project or .pbix file and nothing here publishes
to the Power BI service. It is a manual import kit only.

Contents:
  report.csv            Frozen report rows (one row per product x market
                        x {time_column}) with ids, names and metric
                        columns.
{totals_description}{totals_note}
  PowerQuery_Report.m   Typed import query for report.csv.
  PowerQuery_Totals.m   Typed import query for totals.csv.
  theme.json            Power BI theme (View > Themes > Browse for themes).
  provenance.json       Specification, spec_hash, dataset fingerprint,
                        approval status and owner the figures came from.

Import steps (Power BI Desktop):
  1. Extract this zip to a folder, e.g. {FOLDER_PATH_PLACEHOLDER}.
  2. Home > Get data > Blank query > Advanced editor; paste the contents
     of each .m file. Edit FolderPath at the top if your folder differs.
  3. After loading, select each numeric metric column and set
     "Don't summarize" (or model them as explicit measures). Percent and
     duration columns must not be summed - the provided totals.csv already
     carries the engine's totals. A missing value is null, not zero.
  4. Units - values are already in these units; percent figures are on a
     0-100 scale, not fractional:
{unit_lines}

CSV safety note (formula-injection mitigation): embedded tabs and
newlines in string cells were flattened to spaces, and any string whose
first non-whitespace character is =, +, - or @ was written with a
leading single quote to reduce the risk of spreadsheet formula
execution. Numeric cells were never modified.
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.csv", report_csv)
        archive.writestr("totals.csv", totals_csv)
        archive.writestr("PowerQuery_Report.m", report_m)
        archive.writestr("PowerQuery_Totals.m", totals_m)
        archive.writestr("theme.json", json.dumps(_THEME, indent=2))
        archive.writestr(
            "provenance.json", json.dumps(_provenance(report), indent=2)
        )
        archive.writestr("README.txt", readme)
    return buffer.getvalue()


_PUBLIC_HEADERS = [
    "product_name", "year", "sales_eur_million",
    "source_table", "source_row_label",
]


def build_public_financials_bundle(evidence: dict) -> bytes:
    """Power BI kit for the frozen public financials rows (no totals)."""
    rows = evidence.get("rows") or []
    csv_text = serialize_rows_csv(rows, _PUBLIC_HEADERS)
    m_text = _m_query(
        "public_financials.csv",
        [("product_name", "type text"),
         ("year", "Int64.Type"),
         ("sales_eur_million", "type number"),
         ("source_table", "type text"),
         ("source_row_label", "type text")],
    )
    provenance = {
        "source_url": evidence.get("source_url"),
        "source_title": evidence.get("source_title"),
        "source_sha256": evidence.get("source_sha256"),
        "source_snapshot": evidence.get("source_snapshot"),
        "retrieved_at_utc": evidence.get("retrieved_at_utc"),
        "data_classification": evidence.get("data_classification"),
        "unit": evidence.get("unit"),
        "grain": evidence.get("grain"),
        "data_disclaimer": evidence.get("disclaimer"),
    }
    readme = f"""Public financials - Power BI import kit
================================================================

Reported annual product sales, copied verbatim from the frozen evidence
file. This kit is NOT a .pbip project or .pbix file and nothing here
publishes to the Power BI service.

Contents:
  public_financials.csv        Frozen rows (product x fiscal year).
  PowerQuery_PublicFinancials.m  Typed import query (year = integer,
                               sales_eur_million = number).
  theme.json                   Power BI theme.
  provenance.json              Source URL, retrieval timestamp, SHA-256,
                               classification and disclaimer.

Import steps:
  1. Extract this zip to a folder, e.g. {FOLDER_PATH_PLACEHOLDER}.
  2. Blank query > Advanced editor; paste the .m file and set FolderPath.
  3. There is deliberately no totals file: do not sum across products or
     years. Figures are {evidence.get("unit") or "EUR million"}, global,
     reported sales for the selected products only - not the full
     division, not forecasts, not monthly or country figures.

CSV safety note (formula-injection mitigation): embedded tabs and
newlines in string cells were flattened to spaces, and any string whose
first non-whitespace character is =, +, - or @ was written with a
leading single quote. Numeric cells were never modified.
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("public_financials.csv", csv_text)
        archive.writestr("PowerQuery_PublicFinancials.m", m_text)
        archive.writestr("theme.json", json.dumps(_THEME, indent=2))
        archive.writestr(
            "provenance.json", json.dumps(provenance, indent=2)
        )
        archive.writestr("README.txt", readme)
    return buffer.getvalue()
