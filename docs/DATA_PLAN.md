# Smart Librarian: data first

## Product and boundaries

Build a governed analytics assistant, not a medical prediction system.
The supplied presentation shows Prompt -> Intent -> Evidence -> Spec -> Report.
Reuse and review are first-class outcomes before generating a new report.
The workbook is synthetic/illustrative; product names provide public context only.
Do not alter the workbook, treat migration candidates as ground truth, infer
permissions, or claim that a certified asset necessarily answers a request.

## Architecture and build order

| Layer | Responsibility | MVP implementation |
| --- | --- | --- |
| 0. Sources and ingestion | Preserve source, export catalog, retain provenance | openpyxl, JSON, CSV, SQLite |
| 1. Catalog and semantic contracts | Assets, KPIs, model capabilities, lineage | SQLite plus explicit synthetic model contracts |
| 2. UI and API | Chat, evidence display, session endpoints | Streamlit and FastAPI |
| 3. Prompt to intent | Extract intent, resolve ambiguity, retain conversation | Configurable LLM, typed intent, explicit workflow state |
| 4. Intent to evidence | Find candidates and check exact capabilities | Parameterized SQL tools; optional semantic search |
| 5. Governance and decision | Check evidence, propose reuse/change/build/review | Python validation; no LLM-authored policy execution |
| 6. Evidence to specification | Produce a typed, supported report proposal | LLM may propose; Python validates catalog IDs and capabilities |
| 7. Approval and rendering | Approve changes, render a preview, export | Audit trail, deterministic renderer, versioned JSON |

An LLM adapter initially targets GPT-4.1 mini if credentials and provider access
are available. No API calls or credentials are needed for data preparation.
A real PBIP exporter is a separate, narrowly tested integration, not implemented
by merely naming a JSON file with a .pbip extension.

## Sources already available

- Workbook: primary structured estate, governance and synthetic business data.
- DOCX/PDF brief: requirements and judging criteria, not operational evidence.
- Presentation photos: workflow guidance, not verified executable schemas.
- Personal notes: design context, not authoritative governance rules.
- Audio clips: present but not transcribed or used as verified requirements.

Use all workbook sheets for preservation. START_HERE and Package_Overview are
presentation grids, not rectangular data tables. Keep their original grid shape.
Products, Markets, Owners, KPI_Catalog, Workspaces, Semantic_Models,
Analytics_Assets, Asset_KPI_Map, Asset_Usage, Lineage_Edges,
Product_Market_Monthly, Launch_Milestones, Market_Access, Supply_Operations,
Data_Quality, Governance_Signals, Migration_Backlog, Business_Requests,
Governance_Rules, Data_Dictionary, Public_References and Change_Log can be
exported as tables with workbook row provenance.

## Missing inputs: add explicitly, never infer silently

| Gap | Required next artifact | Constraint |
| --- | --- | --- |
| Executable metric semantics | Versioned metric contracts | Column mapping, units, grain, aggregation and date/value-type rules |
| Model capabilities | Model/table/column/relationship contracts | Do not equate table counts or model names with actual capability |
| Known report coverage | Explicit coverage for a small demo fixture | Separate synthetic overlay; never overwrite existing asset records |
| Real report destinations | Local demo detail routes | Mark mock links; no invented Power BI URLs |
| Identity and authorization | Simulated identity and access policy | No claims of real Bayer authorization |
| Approval history | Runtime approval and audit tables | Synthetic scenario approvals are not real owner approvals |
| Reliable refresh timing | Snapshot time and freshness contract | Refresh status/frequency is not a last-success timestamp |

First supported business slice: monthly synthetic Net Sales by product and market.
The Product_Market_Monthly table contains both actual-like and forecast-like
synthetic value types: specify their treatment before computing anything.
The existing KPI catalog is not an executable definition of those calculations.
The independent `data/demo_v1/catalog.json` now defines executable model and metric
contracts for a small synthetic fixture. These do not establish formulas or
capabilities for the organizer's existing model IDs. See docs/DEMO_DATA_README.md.

## Preparation behavior

Run `python prepare_catalog.py` from this project with openpyxl installed.
It creates a new timestamped directory under data/prepared, leaving originals
and earlier snapshots untouched. A manifest identifies the source SHA-256,
exported columns and row counts. A directory without manifest.json is incomplete.
Grid JSON preserves scalar values (dates normalized to ISO 8601) and blank rows;
CSV and SQLite are convenient text-oriented catalog views. Formula cells, if
present, are preserved as expressions and are not evaluated.
CSV is an interchange artifact, not a sanitized spreadsheet for untrusted inputs.

Preparation does not clean contradictory requests or enforce guessed foreign
keys. A later audit must surface contradictions and unresolved references as
evidence gaps. Source sheet and workbook row allow tracing every exported record.

## Data readiness gate before agents

1. Confirm the source hash, row counts, headers and cell values match the export.
2. Audit IDs and documented joins without silently dropping unmatched records.
3. Author the supported synthetic metric/model/coverage contracts separately.
4. Define example requests for reuse, extension, build and clarification.
5. Keep scenario inputs separate from expected decisions used for testing.

No public download is required for the core prototype. External documentation,
sample BI projects or additional product context can be added later with
permission to use network access and a recorded source/license.

## Status

The supplied catalog is preserved; the generated export snapshot under
data/prepared was removed as redundant and can be regenerated later by running
`prepare_catalog.py`. A separate demo_v1 fixture now
provides 54 sales rows, schemas, relationships, metric contracts, known report
coverage, simulated identities/policy, and empty event stores. Six acceptance
scenarios are kept outside the retrieval data. Data checks are recorded in
artifacts/validation/demo_data_validation.json.

A local demo slice now implements chat intake, deterministic governance checks,
guided intent confirmation, simulated approval and report rendering over the
demo_v1 fixture; an opt-in LLM adapter exists but is disabled by default.
BI export and a published report destination are not implemented. The
organizer estate still requires a relationship audit before using its records
for executable decisions.
