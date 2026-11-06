"""Snapshot the supplied workbook without repairing or inventing metadata."""

import csv
import hashlib
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx"
PRESENTATION_SHEETS = {"START_HERE", "Package_Overview"}


def normalize(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"Unsupported cell type: {type(value).__name__}")


def quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def main():
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "data" / "prepared" / f"{stamp}_{source_hash[:12]}"
    output.mkdir(parents=True, exist_ok=False)
    workbook = openpyxl.load_workbook(SOURCE, read_only=True, data_only=False)
    manifest = {
        "format_version": 1,
        "source_file": SOURCE.name,
        "source_sha256": source_hash,
        "created_at_utc": stamp,
        "disclaimer": "Supplied synthetic/illustrative estate; not actual Bayer operations.",
        "normalization": (
            "Dates use ISO 8601. JSON retains scalar types; CSV and SQLite use text. "
            "Formulas remain formula text, not calculated values. Empty rows are retained "
            "in grid JSON; tabular exports omit fully empty rows. No inferred relations, "
            "repairs, permissions, formulas, or recommendations are added."
        ),
        "sheets": [],
    }
    try:
        with sqlite3.connect(output / "catalog.sqlite") as connection:
            for sheet in workbook:
                grid = [
                    [normalize(cell) for cell in row]
                    for row in sheet.iter_rows(values_only=True)
                ]
                (output / f"{sheet.title}.grid.json").write_text(
                    json.dumps(grid, ensure_ascii=True, indent=2, allow_nan=False),
                    encoding="utf-8",
                )
                info = {
                    "sheet": sheet.title,
                    "grid_file": f"{sheet.title}.grid.json",
                    "grid_rows": len(grid),
                    "tabular": sheet.title not in PRESENTATION_SHEETS,
                }
                if info["tabular"]:
                    headers = grid[0] if grid else []
                    if not headers or any(not isinstance(h, str) or not h for h in headers):
                        raise ValueError(f"Invalid header in {sheet.title}")
                    columns = ["_source_sheet", "_source_row", *headers]
                    if len({c.casefold() for c in columns}) != len(columns):
                        raise ValueError(f"Duplicate/reserved column in {sheet.title}")
                    records = []
                    for source_row, row in enumerate(grid[1:], start=2):
                        if not any(value is not None for value in row):
                            continue
                        if len(row) > len(headers) and any(
                            value is not None for value in row[len(headers):]
                        ):
                            raise ValueError(f"Cells beyond header: {sheet.title}:{source_row}")
                        values = (row + [None] * len(headers))[:len(headers)]
                        records.append([sheet.title, source_row, *values])
                    definitions = ", ".join(f"{quote(c)} TEXT" for c in columns)
                    connection.execute(f"CREATE TABLE {quote(sheet.title)} ({definitions})")
                    placeholders = ", ".join("?" for _ in columns)
                    connection.executemany(
                        f"INSERT INTO {quote(sheet.title)} VALUES ({placeholders})", records
                    )
                    with (output / f"{sheet.title}.csv").open(
                        "w", encoding="utf-8", newline=""
                    ) as handle:
                        writer = csv.writer(handle)
                        writer.writerow(columns)
                        writer.writerows(records)
                    info.update({
                        "columns": headers,
                        "record_count": len(records),
                        "csv_file": f"{sheet.title}.csv",
                        "sqlite_table": sheet.title,
                    })
                manifest["sheets"].append(info)
    finally:
        workbook.close()
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError("Source changed during export; snapshot must not be used.")
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    print(output)
    print("Snapshot complete. Only directories with manifest.json are complete snapshots.")


if __name__ == "__main__":
    main()
