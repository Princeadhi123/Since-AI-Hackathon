import argparse
import csv
import hashlib
import io
import json
import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import httpx
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent
WORKBOOK = ROOT / "data" / "Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx"
OUTPUT = ROOT / "data" / "evidence"
PUBLIC_URL = (
    "https://reports.bayer.com/annual-report-2025/en/report-on-economic-position/"
    "earnings-asset-and-financial-position/business-development-by-division/pharmaceuticals.html"
)
SHEETS = (
    "Analytics_Assets", "Semantic_Models", "Owners", "KPI_Catalog", "Asset_KPI_Map",
    "Asset_Usage", "Lineage_Edges", "Governance_Signals", "Migration_Backlog",
    "Data_Quality", "Governance_Rules",
)
PRODUCTS = ("Nubeqa", "Kerendia", "Eylea", "Xarelto")
EXPECTED_SALES = {
    ("Nubeqa", 2024): 1523, ("Nubeqa", 2025): 2385,
    ("Kerendia", 2024): 463, ("Kerendia", 2025): 829,
    ("Eylea", 2024): 3306, ("Eylea", 2025): 3110,
    ("Xarelto", 2024): 3480, ("Xarelto", 2025): 2344,
}


class TableRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("th", "td") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("th", "td") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def scalar(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"Unsupported workbook value: {type(value).__name__}")


def workbook_evidence(timestamp):
    digest = hashlib.sha256(WORKBOOK.read_bytes()).hexdigest()
    tables = {}
    workbook = load_workbook(WORKBOOK, read_only=True, data_only=False)
    try:
        for name in SHEETS:
            rows = iter(workbook[name].values)
            headers = next(rows)
            if not all(isinstance(h, str) and h for h in headers):
                raise ValueError(f"Invalid headers in {name}")
            if len(set(headers)) != len(headers) or "_source_row" in headers:
                raise ValueError(f"Duplicate or reserved headers in {name}")
            records = []
            for source_row, values in enumerate(rows, start=2):
                if not any(value is not None for value in values):
                    continue
                if len(values) != len(headers):
                    raise ValueError(f"Unexpected row width in {name}:{source_row}")
                records.append({
                    "_source_row": source_row,
                    **{key: scalar(value) for key, value in zip(headers, values, strict=True)},
                })
            tables[name] = records
    finally:
        workbook.close()
    if hashlib.sha256(WORKBOOK.read_bytes()).hexdigest() != digest:
        raise ValueError("Workbook changed during extraction")
    return {
        "source_file": WORKBOOK.name,
        "source_sha256": digest,
        "retrieved_at_utc": timestamp,
        "data_classification": "official_synthetic_challenge",
        "disclaimer": (
            "Official SinceAI builder pack: entirely synthetic/illustrative metadata, "
            "not internal Bayer systems. Source rows are preserved without repair. "
            "Migration candidates and governance signals are scenario inputs, not "
            "validated recommendations or certification. The executable report "
            "workflow uses separate independent demo fixtures, not this estate."
        ),
        "tables": tables,
    }


def public_evidence(source_bytes, timestamp):
    parser = TableRows()
    parser.feed(source_bytes.decode("utf-8"))
    selected = {}
    header = None
    for cells in parser.rows:
        if cells and cells[0] == "€ million":
            header = cells
        if not cells or cells[0] not in {name + "™" for name in PRODUCTS}:
            continue
        if header is None or len(header) != 17 or len(cells) != 17:
            raise ValueError("Public table layout changed")
        if header[10] != "2024" or header[12] != "2025":
            raise ValueError("Annual sales column labels changed")
        product = cells[0].removesuffix("™")
        for year, column in ((2024, 10), (2025, 12)):
            value = cells[column]
            if not re.fullmatch(r"\d{1,3}(?:,\d{3})*|\d+", value):
                raise ValueError("Unexpected published sales value")
            key = (product, year)
            if key in selected:
                raise ValueError("Duplicate source product/year")
            selected[key] = {
                "product_name": product,
                "year": year,
                "sales_eur_million": int(value.replace(",", "")),
                "source_table": "Best-selling Pharmaceuticals products",
                "source_row_label": cells[0],
            }
    actual = {key: record["sales_eur_million"] for key, record in selected.items()}
    if actual != EXPECTED_SALES:
        raise ValueError("Published values differ from the reviewed 2025 disclosure")
    return {
        "source_url": PUBLIC_URL,
        "source_title": "Bayer Annual Report 2025 — Pharmaceuticals",
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_snapshot": "bayer_pharma_2025.html",
        "retrieved_at_utc": timestamp,
        "data_classification": "public_reported_actual",
        "disclaimer": (
            "Actual published global product sales for four selected products, "
            "fiscal years 2024 and 2025, in EUR million. Not the whole division; "
            "not internal Bayer data, not forecasts, not monthly or country data. "
            "Reported sales are not currency/portfolio-adjusted growth. These "
            "figures are never combined with synthetic workflow figures."
        ),
        "rights_note": (
            "Public company disclosure; no open-data license is asserted. The HTML "
            "snapshot is retained locally for verification; review publisher terms "
            "before redistributing source documents."
        ),
        "unit": "EUR million",
        "grain": "product x fiscal_year; global reported sales",
        "rows": [selected[(name, year)] for name in PRODUCTS for year in (2024, 2025)],
    }


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--download", action="store_true")
    options = args.parse_args()
    OUTPUT.mkdir(exist_ok=True)
    snapshot = OUTPUT / "bayer_pharma_2025.html"
    if options.download:
        if snapshot.exists():
            raise FileExistsError("Source snapshot exists; reuse it without --download")
        response = httpx.get(PUBLIC_URL, follow_redirects=True, timeout=60)
        response.raise_for_status()
        if str(response.url) != PUBLIC_URL:
            raise ValueError("Publisher URL redirected; review the new source before use")
        if "text/html" not in response.headers.get("content-type", ""):
            raise ValueError("Expected an HTML financial disclosure")
        source_bytes = response.content
    else:
        source_bytes = snapshot.read_bytes()
    timestamp = datetime.now(timezone.utc).isoformat()
    estate = workbook_evidence(timestamp)
    public = public_evidence(source_bytes, timestamp)
    for name in ("challenge_estate.json", "public_financials.json", "public_financials.csv"):
        if (OUTPUT / name).exists():
            raise FileExistsError(f"Refusing to overwrite frozen evidence: {name}")
    if options.download:
        snapshot.write_bytes(source_bytes)
    for name, data in (("challenge_estate.json", estate), ("public_financials.json", public)):
        (OUTPUT / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(public["rows"][0]))
    writer.writeheader()
    writer.writerows(public["rows"])
    (OUTPUT / "public_financials.csv").write_text(
        buffer.getvalue(), encoding="utf-8", newline=""
    )
    print(json.dumps({
        "output": str(OUTPUT),
        "workbook_sha256": estate["source_sha256"],
        "public_source_sha256": public["source_sha256"],
        "public_rows": len(public["rows"]),
        "estate_tables": {name: len(rows) for name, rows in estate["tables"].items()},
    }, indent=2))


if __name__ == "__main__":
    main()
