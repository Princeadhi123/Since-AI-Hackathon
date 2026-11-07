import hashlib
import io
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "data" / "public_financials_v2"
PRODUCTS = [
    ("Eylea", "PUBLIC-EYLEA", "Eylea™"),
    ("Nubeqa", "PUBLIC-NUBEQA", "Nubeqa™"),
    ("Xarelto", "PUBLIC-XARELTO", "Xarelto™"),
    ("Mirena / Kyleena / Jaydess", "PUBLIC-MIRENA-FAMILY", "Mirena™/Kyleena™/Jaydess™"),
    ("Kerendia", "PUBLIC-KERENDIA", "Kerendia™"),
    ("Adempas", "PUBLIC-ADEMPAS", "Adempas™"),
    ("YAZ / Yasmin / Yasminelle", "PUBLIC-YAZ-FAMILY", "YAZ™/Yasmin™/Yasminelle™"),
    ("Kovaltry / Jivi", "PUBLIC-KOVALTRY-JIVI", "Kovaltry™/Jivi™"),
    ("CT Fluid Delivery", "PUBLIC-CT-FLUID", "CT Fluid Delivery"),
    ("Ultravist", "PUBLIC-ULTRAVIST", "Ultravist™"),
    ("Aspirin Cardio", "PUBLIC-ASPIRIN-CARDIO", "Aspirin™ Cardio"),
    ("Adalat", "PUBLIC-ADALAT", "Adalat™"),
    ("Gadovist product family", "PUBLIC-GADOVIST-FAMILY", "Gadovist™ product family"),
    ("Stivarga", "PUBLIC-STIVARGA", "Stivarga™"),
    ("Glucobay", "PUBLIC-GLUCOBAY", "Glucobay™"),
]
SOURCES = [
    {
        "source_id": "BAYER-AR2025",
        "source_title": "Bayer Annual Report 2025 — Pharmaceuticals",
        "source_url": "https://reports.bayer.com/annual-report-2025/en/report-on-economic-position/earnings-asset-and-financial-position/business-development-by-division/pharmaceuticals.html",
        "file_suffix": "cmr-best-selling-pharm-products-bayer-ar25.xlsx",
        "headers": ["€ million", "Q4 2024", "Q4 2025", "Reported", "Fx & p adj.",
                    "2024", "2025", "Reported", "Fx & p adj."],
        "columns": {1: "2024-Q4", 2: "2025-Q4", 5: "2024", 6: "2025"},
        "notes": "Reported sales, not currency/portfolio-adjusted growth. CT Fluid Delivery includes injection systems marketed primarily as part of the Stellant product family.",
    },
    {
        "source_id": "BAYER-Q12026",
        "source_title": "Bayer Quarterly Statement Q1 2026 — Pharmaceuticals",
        "source_url": "https://reports.bayer.com/quarterly-statement-q1-2026/en/business-development-by-division/pharmaceuticals.html",
        "file_suffix": "cmr-best-selling-pharm-products-bayer-ir126.xlsx",
        "headers": ["€ million", "Q1 2025", "Q1 2026", "Reported", "Fx & p adj."],
        "columns": {1: "2025-Q1", 2: "2026-Q1"},
        "notes": "The source flags Ultravist 2025 figures as restated. Values retain this report's version; they are not reconciled by subtracting other reports.",
    },
    {
        "source_id": "BAYER-H12026",
        "source_title": "Bayer Half-Year Financial Report Q2 2026 — Pharmaceuticals",
        "source_url": "https://reports.bayer.com/half-year-financial-report-q2-2026/en/interim-group-management-report/sales-earnings-and-financial-position/business-development-by-division/pharmaceuticals.html",
        "file_suffix": "cmr-best-selling-pharm-products-bayer-ir226.xlsx",
        "headers": ["€ million", "Q2 2025", "Q2 2026", "Reported", "Fx & p adj.",
                    "H1 2025", "H1 2026", "Reported", "Fx & p adj."],
        "columns": {1: "2025-Q2", 2: "2026-Q2", 5: "2025-H1", 6: "2026-H1"},
        "notes": "Q2 and H1 are separate published period types. H1 overlaps Q1 and Q2; no missing quarter is derived or reconciled across report versions.",
    },
]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "SmartLibrarianSourceSnapshot/2"})
    with urllib.request.urlopen(request, timeout=60) as response:
        final = urllib.parse.urlparse(response.url)
        if final.scheme != "https" or final.hostname != "reports.bayer.com":
            raise ValueError("Unexpected source redirect.")
        return response.read()


def period_record(identifier):
    year = int(identifier[:4])
    if len(identifier) == 4:
        return {"period_id": identifier, "period_kind": "year", "label": f"FY {year}",
                "start_date": f"{year}-01-01", "end_date": f"{year}-12-31"}
    if identifier.endswith("H1"):
        return {"period_id": identifier, "period_kind": "half_year", "label": f"H1 {year}",
                "start_date": f"{year}-01-01", "end_date": f"{year}-06-30"}
    quarter = int(identifier[-1])
    start, end = {1: ("01-01", "03-31"), 2: ("04-01", "06-30"),
                  4: ("10-01", "12-31")}[quarter]
    return {"period_id": identifier, "period_kind": "quarter",
            "label": f"Q{quarter} {year}", "start_date": f"{year}-{start}",
            "end_date": f"{year}-{end}"}


def extract(spec, raw):
    workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    rows = list(sheet.iter_rows(values_only=True))
    if rows[1][0] != "Best-selling Pharmaceuticals products":
        raise ValueError("Unexpected source table.")
    headers = [" ".join(str(value).split()) for value in rows[4][:len(spec["headers"])]]
    if headers != spec["headers"]:
        raise ValueError(f"Unexpected columns for {spec['source_id']}.")
    by_label = {label: (name, identifier) for name, identifier, label in PRODUCTS}
    result, seen = [], set()
    for number, row in enumerate(rows[5:], 6):
        label = row[0]
        if label == "Total best-selling products":
            break
        if not isinstance(label, str):
            raise ValueError("Missing product label before source total.")
        normalized = re.sub(r"\d+$", "", label).strip()
        if normalized not in by_label:
            raise ValueError(f"Unreviewed source product: {label!r}")
        name, identifier = by_label[normalized]
        if identifier in seen:
            raise ValueError("Duplicate source product.")
        seen.add(identifier)
        for column, period in spec["columns"].items():
            value = row[column]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"Invalid published value at row {number}, column {column + 1}.")
            result.append({
                "product_id": identifier, "product_name": name,
                "market_id": "GLOBAL", "market_name": "Global",
                "period": period, "period_kind": period_record(period)["period_kind"],
                "PUBLIC-REPORTED-SALES": value, "source_id": spec["source_id"],
                "source_table": "Best-selling Pharmaceuticals products",
                "source_row_label": label, "source_row": number,
                "source_column": spec["headers"][column],
            })
    if seen != {identifier for _, identifier, _ in PRODUCTS}:
        raise ValueError("Incomplete published product selection.")
    return result


def main():
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite source snapshot: {OUTPUT}")
    captured, records, sources = {}, [], []
    retrieved = datetime.now(timezone.utc).isoformat()
    for spec in SOURCES:
        page = fetch(spec["source_url"])
        links = Links()
        links.feed(page.decode("utf-8"))
        candidates = {urllib.parse.urljoin(spec["source_url"], link) for link in links.links
                      if link.endswith(spec["file_suffix"])}
        if len(candidates) != 1:
            raise ValueError("Cannot identify the reviewed downloadable source.")
        xlsx_url = candidates.pop()
        raw = fetch(xlsx_url)
        records.extend(extract(spec, raw))
        html_name, xlsx_name = f"{spec['source_id']}.html", spec["file_suffix"]
        captured[html_name], captured[xlsx_name] = page, raw
        sources.append({
            key: spec[key] for key in ("source_id", "source_title", "source_url", "notes")
        } | {
            "download_url": xlsx_url, "source_snapshot": f"sources/{xlsx_name}",
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "html_snapshot": f"sources/{html_name}",
            "html_sha256": hashlib.sha256(page).hexdigest(), "retrieved_at_utc": retrieved,
        })
    periods = sorted({record["period"] for record in records})
    payload = {
        "schema_version": "public-financials-v2",
        "data_classification": "public_reported_actual",
        "retrieved_at_utc": retrieved, "unit": "EUR million",
        "grain": "product or published product family x global x explicit reporting period",
        "disclaimer": (
            "Published reported sales copied from official Bayer disclosure. "
            "These 15 products/product families are not the whole division. "
            "Annual, quarterly and half-year periods overlap and must never be summed together. "
            "Comparatives retain the cited report version and its restatements. "
            "No monthly, country-level, forecast, delivery or manufacturing-quality values. "
            "Identities, governance and local registry metadata remain simulated."
        ),
        "rights_note": (
            "Public disclosure, not an asserted open-data license. Retained source documents "
            "are local verification snapshots; review publisher terms before redistribution."
        ),
        "products": [{"product_id": identifier, "product_name": name}
                     for name, identifier, _ in PRODUCTS],
        "periods": [period_record(period) for period in periods],
        "sources": sources, "rows": records,
    }
    OUTPUT.mkdir()
    (OUTPUT / "sources").mkdir()
    for name, raw in captured.items():
        (OUTPUT / "sources" / name).write_bytes(raw)
    with (OUTPUT / "dataset.json").open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Created {OUTPUT}: {len(records)} published facts, {len(periods)} periods.")


if __name__ == "__main__":
    main()
