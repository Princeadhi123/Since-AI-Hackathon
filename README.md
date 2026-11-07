# Smart Librarian

A governed analytics assistant over curated data catalogs. The product goal is
to let users ask business questions, clarify intent, and produce governed,
approvable report specifications over trusted catalog data - not a chatbot
that guesses SQL.

## Status

Working today (local loopback demo):

- Challenge mode (the `run_demo.py` default): `create_challenge_app()`
  mounts `/api/challenge/*` over the official synthetic builder pack -
  four source domains (commercial monthly, market access snapshot,
  supply snapshot, launch events), fixed simulated identities
  (requester/FI/approver/steward), governed plan persistence with
  approval + frozen source-row renders, estate lifecycle proposals
  (approved-but-never-executed), and HTML/CSV/ZIP/Power Query kit/PBIP
  exports. The workbook is read-only; plans live in the runtime SQLite.
- FastAPI service with session, chat, guided intent confirmation, simulated
  approval and deterministic report rendering. The standalone `create_app`
  module default is **real-data-only**: only the governed
  **Bayer public sales** domain (`public_sales`) mounts, serving published
  actual annual, quarterly and half-year figures from the frozen dataset
  `data/public_financials_v2/dataset.json` - no synthetic catalogs load.
  Passing `include_synthetic=True` or an explicit `demo_dir` selects the
  legacy mode: three synthetic domains (Sales `data/demo_v1`, Logistics
  `data/demo_logistics_v1`, Quality `data/demo_quality_v1`) plus the old
  four-product annual public domain from `data/evidence/`. The public
  domain never sums across reporting periods and uses a separate simulated
  public-data approver.
- Streamlit UI that talks to the API over HTTP only. Real-data-only mode
  opens a dedicated UI (Report builder, Performance explorer, Saved
  reports, Sources & coverage); legacy mode keeps the classic UI with
  domain + identity pickers, scenario prefills, approval panel bound to a
  separate simulated governance actor, per-domain asset library and
  HTML/ZIP report downloads.
- Read-only evidence API (`GET /api/evidence/{challenge|public}`) serving
  the frozen files in `data/evidence/` (legacy and challenge modes; the
  real-data-only public API returns 404 for it), plus - in legacy
  mode - sidebar workspaces that browse them: **Challenge estate** (the
  official synthetic builder-pack estate), **Public financials** (the old
  four-product annual file) and **Deployment readiness**.
- Power BI import kits (`reporting/powerbi.py`): ZIP bundles of frozen
  values - CSVs, typed Power Query (M) scripts, a theme and provenance -
  for manual import. Not a PBIP/PBIX project; nothing publishes to the
  Power BI service. Challenge mode additionally offers a generated
  offline PBIP project export (`reporting/challenge_pbip.py`, schema-
  validated PBIR + embedded TMSL import model); templates were checked
  with Power BI Desktop 2.159.1231.0 (project opens and the embedded
  frozen model renders; validate in your target version). No service
  publish exists.
- Deterministic offline intent parser plus an opt-in LLM extraction
  adapter - OpenAI or CSC/LUMI Aitta via `LLM_PROVIDER` (never called
  unless a request sets `use_llm=true` and that provider's own credential
  is configured; keys are never routed to the wrong endpoint. The live
  provider path is not continuously verified).
- Runtime sessions/approvals/audit/generated-report registry in
  `var/runtime.sqlite`, separate from the read-only fixtures. Approvals are
  recorded against a separate simulated approver actor, bind to the spec
  hash and re-verify the catalog fingerprint; catalog changes invalidate
  prior approvals. Successful renders of approved build/change proposals
  publish deterministic `GEN-` assets that later sessions reuse.
- Self-contained HTML report and CSV/JSON ZIP bundle export
  (`reporting/exports.py`) - no external scripts, fonts or PBIP.

Not implemented yet: PBIX binary export, Power BI service publishing
(the import kit is a manual CSV+M path only; the challenge PBIP ZIP is
an offline generated project checked with Power BI Desktop
2.159.1231.0 - opens and renders locally, not service-verified),
real authentication, production authorization, role isolation, a
published report destination, asset lifecycle retirement.

## Layout

```
.
|-- prepare_catalog.py        # Stable entry point: workbook -> data/prepared snapshot
|-- create_demo_data.py       # Stable entry point: -> data/demo_v1 fixture
|-- run_demo.py               # Starts API (127.0.0.1:8000) + UI (127.0.0.1:8501)
|-- pyproject.toml
|-- .env.example              # Placeholders for the whitelisted .env loader
|-- create_operational_data.py# -> data/demo_logistics_v1 + demo_quality_v1
|-- apps/
|   `-- streamlit_app.py      # Streamlit UI (HTTP client of the API only)
|-- src/smart_librarian/
|   |-- settings.py           # Env/.env loading, paths, provider status
|   |-- api/app.py            # FastAPI app: per-domain services + routes
|   |-- catalog/store.py      # Read-only fixture catalog + runtime overlay
|   |-- domain/parser.py      # Conservative offline intent parser
|   |-- domain/decision.py    # Deterministic gates + spec/hash building
|   |-- domain/governance.py  # Simulated approver/steward actor registry
|   |-- domain/operational_contracts.py  # Logistics/quality contracts
|   |-- domain/executable_contract.py    # Catalog-vs-code contract check
|   |-- workflow/service.py   # Session state machine + approval + render
|   |-- llm/client.py         # Opt-in OpenAI adapter + intent_prompt.txt
|   |-- reporting/calculations.py  # Fixed sales calculations (lead-authored)
|   |-- reporting/operational.py     # Fixed operational calculations
|   |-- reporting/exports.py       # HTML report + ZIP bundle artifacts
|   |-- reporting/powerbi.py       # Power BI import kits (CSV + M + theme)
|   |-- reporting/public_financials.py # Frozen v2 period calculations
|   |-- catalog/public_financials.py   # v2 snapshot catalog adapter
|   |-- domain/public_financials.py    # v2 contract/scope/evidence/parse
|   |-- ui/demo.py                # Real-data-only Streamlit UI
|   |-- evidence.py             # Read-only frozen evidence loader
|   `-- persistence/store.py  # Runtime SQLite sessions/approvals/assets
|-- tests/
|   |-- fixtures/demo_scenarios.json   # Acceptance cases (never retrieval input)
|   |-- test_end_to_end.py    # API acceptance contract (lead-authored)
|   |-- test_calculations.py  # Calculation contract (lead-authored)
|   |-- test_offline_parser.py + test_structure.py
|-- docs/                     # ARCHITECTURE.md, DATA_PLAN.md, DEMO_DATA_README.md
|-- data/
|   |-- <source workbook + original notes/media>
|   |-- evidence/             # Frozen challenge estate + public financials
|   `-- demo_v1/              # Independent fictional fixture (read-only)
|-- var/                      # Runtime SQLite (git-ignored, auto-created)
`-- artifacts/                # Local logs + validation output (git-ignored)
```

## Data separation

- **Source catalog**: the original workbook under `data/` (unchanged). Its
  generated `data/prepared/` export snapshot was removed as redundant; run
  `prepare_catalog.py` to regenerate it if needed.
- **Demo fixture**: entirely fictional data in `data/demo_v1/` (sales) plus
  `data/demo_logistics_v1/` and `data/demo_quality_v1/` generated once by
  `create_operational_data.py`; all mounted read-only. Fingerprint = SHA-256
  over `catalog.json`, `demo.sqlite`, `products.csv`, `markets.csv` and
  `calendar.csv`, captured once at load; any later drift fails closed (409)
  until the service is restarted.
- **Public financials v2 dataset**: `data/public_financials_v2/dataset.json`
  - the frozen, reviewed snapshot powering the default real-data-only demo
  (150 facts, 15 products, 10 reporting periods, 3 official sources).
  Retained publisher snapshots under `data/public_financials_v2/sources/`
  are git-ignored - no redistribution license is asserted. The preparation
  pipeline refuses to overwrite an existing dataset.
- **Evidence files**: `data/evidence/challenge_estate.json` (official
  SinceAI builder-pack estate - synthetic metadata, source rows preserved
  without repair) and `data/evidence/public_financials.json` (selected
  published actual global product sales, EUR million). Read-only, served
  verbatim by the API. In default real-data-only mode the challenge estate
  is not exposed (404); in legacy mode the governed `public_sales` domain
  reads only the public financials evidence through a fixed annual adapter
  and the challenge estate is browse-only - the two datasets are never
  combined. Publisher HTML/XLSX snapshots retained
  under `data/evidence/` are git-ignored - no redistribution license is
  asserted.
- **Acceptance scenarios**: `tests/fixtures/demo_scenarios.json` - used only to
  check expected outcomes, never as retrieval input.
- **Runtime output**: `var/runtime.sqlite` (sessions/approvals/audit) and
  `artifacts/` (logs, validation evidence) - both git-ignored.

The two root generation scripts deliberately stay at the workspace root as
stable entry points to preserve their path assumptions and historical source
hashes. **Do not re-run `create_demo_data.py`** - it fails if its output
directory already exists.

## Run the demo

All dependencies for the local slice are already installed in this
environment; no install or network is needed for offline mode:

```powershell
python run_demo.py                 # challenge builder-pack demo (default)
python run_demo.py --mode public   # real-data-only public sales demo
python run_demo.py --mode legacy   # synthetic multi-domain + public UI
```

Then open http://127.0.0.1:8501. The launcher refuses to start if a port is
already in use and Ctrl+C stops only the children it spawned. Logs land in
`artifacts/logs/`.

Equivalent manual commands, in two shell windows:

```powershell
# Window 1 - API
$env:PYTHONPATH = 'src'
python -m uvicorn smart_librarian.api.app:app --host 127.0.0.1 --port 8000

# Window 2 - UI
$env:PYTHONPATH = 'src'
python -m streamlit run apps/streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

## Demo walkthrough

The default demo is **real-data-only**: it serves 15 published products and
product families across ten frozen reporting periods - FY 2024 and FY 2025,
Q4 2024, Q4 2025, Q1 2025, Q1 2026, Q2 2025, Q2 2026, H1 2025 and H1 2026 -
sourced from three official publisher snapshots. Global figures only, EUR
million; no country, monthly or forecast data exists. Approvals, the
approver identity, endorsement and the asset registry are simulated.

The sidebar offers four workspaces:

1. **Report builder** - starter buttons prefill the guided form (they never
   approve anything): `Nubeqa annual performance` (FY 2024/2025),
   `Compare all products` (annual), `Q2 year-over-year comparison`
   (Q2 2025 vs Q2 2026). Or type a request and Send. Select products, a
   period type (Annual/Quarterly/Half-year) and reporting periods, then
   **Confirm intent**. Extracted out-of-coverage values stay visible and
   require an explicit replace acknowledgment - nothing is silently
   reduced. Approve with the separate simulated public approver, then
   **Open report preview** for charts, the readable table (source rows in
   an expander) and CSV/HTML/ZIP/Power BI kit downloads.
2. **Performance explorer** - browse the frozen published rows by period
   type, product and reporting period; values are shown verbatim, never
   aggregated or derived.
3. **Saved reports** - the local registry of generated `GEN-...` assets;
   **Open / reuse** resumes a governed session (no auto-render).
4. **Sources & coverage** - the three official source URLs, SHA-256 hashes,
   retrieval timestamps, snapshot scope and what the source cannot answer.

The legacy synthetic multi-domain UI and its evidence workspaces
(Challenge estate, Public financials legacy file, Deployment readiness)
are **not exposed by default**; they appear only when the API runs in
legacy mode (`create_app(include_synthetic=True)` or an explicit
`demo_dir`). In legacy mode the walkthrough is: pick Sales/Logistics/
Quality, chat to prefill, confirm, approve with the simulated approver and
preview.

See `docs/CHALLENGE_DEMO.md` for the challenge-mode runbook and `docs/DEMO_RUNBOOK.md` for the full launch checklist and
`docs/DEPLOYMENT.md` for the proposed (unbuilt) production shape.

Optional LLM extraction: set `LLM_PROVIDER` plus the matching credential
(`OPENAI_API_KEY` or `AITTA_API_TOKEN`) in the environment or a local
`.env` (never commit tokens to `.env.example` or any tracked file) - see
`docs/AITTA_SETUP.md` - then check
the opt-in box in the sidebar. The request text plus catalog metadata choices
are sent to the model; catalog metadata contains no source business figures,
but your request text may contain confidential information - do not enter
secrets. Without a key the action fails safely and the session is retained.

The selected demo model is `openai/gpt-oss-120b`, served through **CSC Aitta**
(not the paid OpenAI API). Configure it in your local `.env`:

```dotenv
LLM_PROVIDER=aitta
LLM_MODEL=openai/gpt-oss-120b
AITTA_API_TOKEN=<your Aitta token>
```

See [Aitta setup](docs/AITTA_SETUP.md) for access instructions and
[the model comparison](docs/AITTA_MODEL_COMPARISON.md) for the recorded
four-model results and selected-model workflow checks. This is a small,
task-specific comparison, not a general model ranking or latency guarantee.
The LLM extracts intent only; calculations, permission checks and approvals
remain deterministic (the demo identities and approvals are simulated).

Optional installs for other environments (not executed here):

```powershell
pip install -e ".[ui,llm,dev]"
```

## Tests

```powershell
$env:PYTHONPATH = 'src'
python -m unittest discover -s tests -p "test_*.py" -v
```

## Limitations

- The default launcher (`run_demo.py --mode challenge`) serves the four
  official synthetic builder-pack report domains (commercial monthly,
  market-access snapshots, supply snapshots, launch events) with the
  challenge estate view. `--mode public` serves published actual figures
  for 15 products and product families across 10 reporting periods
  (annual, quarterly, half-year; global, EUR million) from
  `data/public_financials_v2/` - a separate flow that is never joined to
  the synthetic pack. `--mode legacy` mounts the fixture domains (Sales,
  Logistics, Quality) and the older four-product public financials view.
  Identities, certification,
  governance actors and approvals are simulated role-play, not security
  controls - there is no authentication, authorization or role isolation,
  and nothing here is Bayer certification or internal data.
- The offline parser is keyword-based, not general language understanding;
  it may miss unfamiliar requirements - always inspect the exact guided form
  before confirming.
- Report output is JSON, charts, a standalone HTML file, a CSV/JSON ZIP
  bundle and a Power BI import kit (CSV + M scripts + theme). Challenge
  mode additionally exports a generated offline PBIP project ZIP; there
  is no PBIX export or published destination.
- The evidence workspaces are read-only views over frozen files; the
  estate is synthetic challenge metadata (migration backlog entries are
  supplied scenario inputs, not recommendations or certifications) and
  the public figures cover four products and two fiscal years only - no
  monthly, country or forecast questions can be answered from them.
- The Power BI import kits were verified structurally and via AppTest/
  browser checks; the manual CSV+Power Query import steps in Desktop are
  documented but not executed here. The generated challenge PBIP project
  was opened and checked locally with Power BI Desktop 2.159.1231.0.
- The optional LLM path is a thin adapter; its live provider behavior is not
  part of the automated test suite.
