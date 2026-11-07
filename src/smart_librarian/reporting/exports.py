"""Portable report artifacts: self-contained HTML and a CSV/JSON zip bundle.

These functions only serialize the frozen values already present in a render
result. They never recompute, aggregate or adjust business figures; all
numbers come verbatim from report["totals"] and report["rows"].
"""

import csv
import html
import io
import json
import zipfile

def _e(value) -> str:
    return html.escape(str(value))


def _fmt(value, unit) -> str:
    if value is None:
        return "N/A"
    if unit == "percent":
        return f"{value:.2f}%"
    if unit == "EUR":
        return f"{value:,} EUR"
    if unit == "days":
        return f"{value:.2f} days"
    return f"{value:,} {unit}" if unit else f"{value:,}"


def _metric_names(report: dict) -> dict:
    return {
        item["metric_id"]: item.get("name") or item["metric_id"]
        for item in (report.get("spec") or {}).get("requested_metrics") or []
    }


def _svg_chart(rows: list[dict], metric_id: str, metric_name: str,
               unit: str, time_column: str = "month") -> str:
    """Tiny inline SVG line chart from existing row values (no recompute).

    Null values are preserved as gaps: a series never draws a line across a
    month where the rate is undefined.
    """
    width, height, pad = 560, 180, 30
    months = sorted(
        {row.get(time_column) for row in rows if row.get(time_column)}
    )
    series: dict[tuple, dict] = {}
    for row in rows:
        key = (row.get("product_name"), row.get("market_name"))
        series.setdefault(key, {})[row.get(time_column)] = row.get(metric_id)
    if not months or not series:
        return ""
    values = [
        v for points in series.values() for v in points.values()
        if v is not None
    ]
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0

    def x(month):
        if len(months) == 1:
            return width / 2
        return pad + (width - 2 * pad) * months.index(month) / (len(months) - 1)

    def y(value):
        return height - pad - (height - 2 * pad) * (value - lo) / span

    palette = ["#16494a", "#b3541e", "#5a6b2f", "#6d4a7c", "#2f5d8a"]
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{_e(metric_name)} line chart" '
        'xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<line x1="{pad}" y1="{height - pad}" x2="{width - pad}" '
        f'y2="{height - pad}" stroke="#7a6f5c"/>',
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height - pad}" '
        f'stroke="#7a6f5c"/>',
    ]
    for index, month in enumerate(months):
        if len(months) <= 12 or index % 2 == 0:
            parts.append(
                f'<text x="{x(month):.1f}" y="{height - 10}" font-size="9" '
                f'text-anchor="middle" fill="#7a6f5c">{_e(month)}</text>'
            )
    parts.append(
        f'<text x="4" y="{pad}" font-size="9" fill="#7a6f5c">'
        f'{_e(_fmt(hi, unit))}</text>'
    )
    parts.append(
        f'<text x="4" y="{height - pad}" font-size="9" fill="#7a6f5c">'
        f'{_e(_fmt(lo, unit))}</text>'
    )
    for index, (key, points) in enumerate(sorted(series.items())):
        color = palette[index % len(palette)]
        label = " | ".join(_e(str(part)) for part in key)
        # Split into contiguous non-null segments so gaps stay gaps.
        segment = []
        for month in months:
            value = points.get(month)
            if value is None:
                if len(segment) > 1:
                    coords = " ".join(segment)
                    parts.append(
                        f'<polyline points="{coords}" fill="none" '
                        f'stroke="{color}" stroke-width="1.5">'
                        f'<title>{label}</title></polyline>'
                    )
                segment = []
                continue
            cx, cy = x(month), y(value)
            segment.append(f"{cx:.1f},{cy:.1f}")
            parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="2.5" '
                f'fill="{color}"><title>{label} {_e(month)}: '
                f'{_e(_fmt(value, unit))}</title></circle>'
            )
        if len(segment) > 1:
            coords = " ".join(segment)
            parts.append(
                f'<polyline points="{coords}" fill="none" stroke="{color}" '
                f'stroke-width="1.5"><title>{label}</title></polyline>'
            )
    parts.append("</svg>")
    return "".join(parts)


def export_report_html(report: dict) -> str:
    """Self-contained, offline HTML rendering of a finished report."""
    totals = report.get("totals") or {}
    units = report.get("units") or {}
    rows = report.get("rows") or []
    spec = report.get("spec") or {}
    intent = spec.get("intent") or {}
    asset = report.get("asset") or {}
    time_column = report.get("time_column") or "month"
    time_label = report.get("time_label") or "Month"
    is_public = (
        report.get("data_classification") == "public_reported_actual"
        or (report.get("synthetic_record") is False)
    )

    metric_ids = list(totals) or list(units) or [
        m["metric_id"] for m in spec.get("requested_metrics") or []
    ]
    metric_names = _metric_names(report)
    dimension_cols = ["product_name", "market_name", time_column]
    header = "".join(f"<th scope='col'>{_e(c)}</th>" for c in dimension_cols)
    header += "".join(
        f"<th scope='col'>{_e(metric_names.get(m, m))}"
        f"{f' ({_e(units[m])})' if units.get(m) else ''}</th>"
        for m in metric_ids
    )
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{_e(row.get(c))}</td>" for c in dimension_cols)
        cells += "".join(
            f"<td>{_e(_fmt(row.get(m), units.get(m)))}</td>"
            for m in metric_ids
        )
        body_rows.append(f"<tr>{cells}</tr>")

    cards = "".join(
        "<div class='card'><div class='metric'>"
        f"{_e(_fmt(totals.get(m), units.get(m)))}</div>"
        f"<div class='label'>{_e(metric_names.get(m, m))}</div></div>"
        for m in metric_ids
        if m in totals
    )
    charts = "".join(
        f"<h3>{_e(metric_names.get(m, m))} by {_e(time_label.lower())}</h3>"
        f"{_svg_chart(rows, m, metric_names.get(m, m), units.get(m), time_column)}"
        for m in metric_ids
        if any(row.get(m) is not None for row in rows)
    )

    provenance = {
        "outcome": report.get("outcome"),
        "proposal_id": report.get("proposal_id"),
        "spec_hash": report.get("spec_hash"),
        "approval_status": report.get("approval_status"),
        "source_asset_id": report.get("source_asset_id"),
        "registered_asset_id": report.get("registered_asset_id"),
        "asset_name": asset.get("name"),
        "owner": asset.get("owner_name") or asset.get("owner_id"),
        "endorsement": asset.get("endorsement"),
        "model_id": spec.get("model_id"),
        "dataset_id": spec.get("dataset_id"),
        "dataset_fingerprint": spec.get("dataset_fingerprint"),
        "grain": intent.get("grain"),
        "time_column": report.get("time_column"),
        "data_classification": report.get("data_classification"),
    }
    provenance.update(
        {f"source_{k}": v for k, v in
         (report.get("source_provenance") or {}).items()}
    )
    prov_items = "".join(
        f"<tr><th scope='row'>{_e(k)}</th><td>{_e(v)}</td></tr>"
        for k, v in provenance.items()
        if v is not None
    )
    if is_public:
        banner = (
            "Published actual sales figures from public company "
            "disclosure. Simulated approval and registry only - not Bayer "
            "certification or internal data. Local preview artifact only."
        )
        totals_heading = (
            "Totals (single fiscal year only)"
            if time_column == "fiscal_year"
            else "Totals (single reporting period only)"
        )
    else:
        banner = (
            "Synthetic demo data - not real business figures. "
            "Simulated approval and certification; local preview artifact "
            "only."
        )
        totals_heading = "Totals"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Smart Librarian report - {_e(report.get("registered_asset_id") or "preview")}</title>
<style>
body {{ font-family: Georgia, 'Times New Roman', serif; background: #faf6ef;
  color: #23201a; margin: 24px; }}
h1, h2, h3 {{ color: #16494a; }}
.banner {{ background: #16494a; color: #f3ead9; padding: 8px 14px;
  border-radius: 6px; font-size: 0.9rem; }}
.card {{ display: inline-block; background: #fff; border: 1px solid #e4d9c3;
  border-radius: 8px; padding: 12px 18px; margin: 6px 6px 6px 0; }}
.metric {{ font-size: 1.4rem; font-weight: bold; color: #16494a; }}
.label {{ font-size: 0.8rem; color: #7a6f5c; }}
table {{ border-collapse: collapse; width: 100%; background: #fff; }}
th, td {{ border: 1px solid #e4d9c3; padding: 6px 10px; text-align: left;
  font-size: 0.9rem; }}
caption {{ text-align: left; font-weight: bold; padding: 4px 0; }}
@media print {{
  body {{ background: #fff; margin: 0; }}
  .banner {{ background: #eee; color: #000; }}
  .card {{ border: 1px solid #999; }}
}}
</style>
</head>
<body>
<div class="banner">{_e(banner)}</div>
<h1>Report: {_e(asset.get("name") or report.get("registered_asset_id") or "Local preview")}</h1>
<section aria-label="{_e(totals_heading)}">{cards}</section>
{charts}
<h2>Rows</h2>
<table>
<caption>Report rows (frozen values; no recomputation)</caption>
<thead><tr>{header}</tr></thead>
<tbody>{"".join(body_rows)}</tbody>
</table>
<h2>Provenance</h2>
<table>
<caption>Specification and governance metadata</caption>
<tbody>{prov_items}</tbody>
</table>
</body>
</html>
"""


def build_report_bundle(report: dict) -> bytes:
    """Zip bundle: report.html, report.csv, specification.json, README.txt."""
    rows = report.get("rows") or []
    units = report.get("units") or {}
    metric_ids = list(report.get("totals") or {}) or list(units)
    time_column = report.get("time_column") or "month"
    is_public = (
        report.get("data_classification") == "public_reported_actual"
        or report.get("synthetic_record") is False
    )

    csv_buffer = io.StringIO()
    source_fields = [
        field
        for field in ("source_id", "source_table", "source_row_label",
                      "source_column", "source_row")
        if any(row.get(field) is not None for row in rows)
    ]
    fieldnames = ["product_id", "product_name", "market_id", "market_name",
                  time_column] + metric_ids + source_fields
    writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames,
                            extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    csv_text = csv_buffer.getvalue()

    if time_column == "fiscal_year":
        column_instruction = (
            f"  3. Load, then keep '{time_column}' as a whole-number\n"
            "     fiscal-year label - an integer column, not a date.\n\n"
        )
    elif time_column == "period":
        column_instruction = (
            "  3. Load, then keep 'period' as a text period label\n"
            "     (values like '2025' or '2026-Q1') - not a date.\n\n"
        )
    else:
        column_instruction = (
            f"  3. Load, then mark '{time_column}' as a date column if "
            "prompted.\n\n"
        )
    data_note = (
        "published actual public data" if is_public
        else "synthetic demo data"
    )
    readme = (
        f"Smart Librarian report bundle ({data_note})\n"
        "===================================================\n\n"
        "Contents:\n"
        "  report.html         Self-contained offline report view. Open in any\n"
        "                      browser; no network, scripts or fonts required.\n"
        "  report.csv          Report rows for import into other tools.\n"
        "  specification.json  The approved specification and spec_hash the\n"
        "                      report was rendered against.\n\n"
        "Importing report.csv into Power BI:\n"
        "  1. In Power BI Desktop choose Get Data > Text/CSV.\n"
        "  2. Select report.csv and confirm the detected delimiter (comma).\n"
        + column_instruction +
        "Honest limitation: this bundle contains no .pbip/.pbix project and no\n"
        "direct Power BI export; CSV import is the only supported path.\n\n"
        + (
            "All values are published actual public sales figures copied\n"
            "verbatim from the frozen public source; approval and registry\n"
            "metadata are simulated, not Bayer certification. "
            + (
                "Totals are\ncarried for a single fiscal year only - there "
                "is deliberately\nno cross-year aggregate - and figures "
                "stay in EUR million,\nunscaled.\n"
                if time_column == "fiscal_year" else
                "A total is\ncarried for one selected reporting period "
                "only - there is deliberately\nno combined cross-period "
                "aggregate - and figures stay in EUR million,\nunscaled.\n"
            )
            if is_public else
            "All values are synthetic fixture figures produced by the fixed\n"
            "calculation engine; they are copied here verbatim, not recomputed.\n"
        )
    )

    specification = {
        "spec": report.get("spec"),
        "spec_hash": report.get("spec_hash"),
        "proposal_id": report.get("proposal_id"),
        "approval_status": report.get("approval_status"),
        "outcome": report.get("outcome"),
        "source_asset_id": report.get("source_asset_id"),
        "registered_asset_id": report.get("registered_asset_id"),
        "asset": report.get("asset"),
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.html", export_report_html(report))
        archive.writestr("report.csv", csv_text)
        archive.writestr(
            "specification.json",
            json.dumps(specification, indent=2, sort_keys=True),
        )
        archive.writestr("README.txt", readme)
    return buffer.getvalue()
