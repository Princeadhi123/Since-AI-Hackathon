# Demo Data (demo_v1)

Independent, entirely fictional fixture. The source workbook is unchanged.

## Contents

- `data/demo_v1/demo.sqlite` plus four CSVs (`products.csv`, `markets.csv`, `calendar.csv`, `sales_monthly.csv`) contain the business data.
- `data/demo_v1/catalog.json` contains models, metrics, reports, owners, users, and simulated policy.
- `data/demo_v1/provenance.json` and `data/demo_v1/manifest.json` identify the source and hashes.
- `data/demo_v1/approval_events.json` and `data/demo_v1/audit_events.json` are intentionally empty (not approvals).

## Scope

- 2 products: Nubeqa and Kerendia, with `DEMO`-prefixed product IDs.
- Markets: Germany, Finland, France.
- Monthly values for Jan-Sep 2026, in integer EUR.
- All rows are `synthetic_actual`.

## Scenarios

`tests/fixtures/demo_scenarios.json` is acceptance-only with expected outcomes. It is never a retrieval input.

## Model support

- Supported: Net Sales, Sales Forecast, and aggregate-derived variance %.
- Draft Gross Sales is unsupported.

## Report destination

The current report destination is an unimplemented local preview reference. There is no working UI or BI file yet.
