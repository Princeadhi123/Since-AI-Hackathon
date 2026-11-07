# Smart Librarian

A governed analytics assistant over curated data catalogs. The product goal is
to let users ask business questions, clarify intent, and produce governed,
approvable report specifications over trusted catalog data - not a chatbot
that guesses SQL.

## Status

Working today (local loopback demo):

- FastAPI service with session, chat, guided intent confirmation, simulated
  approval and deterministic report rendering over three synthetic domains:
  Sales (`data/demo_v1`), plus Logistics (`data/demo_logistics_v1`) and
  Quality (`data/demo_quality_v1`) when those sibling fixtures exist.
- Streamlit UI that talks to the API over HTTP only: domain + identity
  pickers, scenario prefills, approval panel bound to a separate simulated
  governance actor, per-domain asset library, HTML/ZIP report downloads.
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

Not implemented yet: Power BI PBIP/PBIX export, real authentication,
production authorization, role isolation, a published report destination,
asset lifecycle retirement.

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
|   `-- persistence/store.py  # Runtime SQLite sessions/approvals/assets
|-- tests/
|   |-- fixtures/demo_scenarios.json   # Acceptance cases (never retrieval input)
|   |-- test_end_to_end.py    # API acceptance contract (lead-authored)
|   |-- test_calculations.py  # Calculation contract (lead-authored)
|   |-- test_offline_parser.py + test_structure.py
|-- docs/                     # ARCHITECTURE.md, DATA_PLAN.md, DEMO_DATA_README.md
|-- data/
|   |-- <source workbook + original notes/media>
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
python run_demo.py
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

1. Pick a domain (Sales, Logistics, Quality) and a simulated identity in the
   sidebar. Switching either starts a fresh session.
2. Type `Show sales performance.` and Send - the librarian asks clarifying
   questions; nothing executes.
3. Follow up with `Nubeqa Germany Net Sales January through March 2026` -
   the extracted fields prefill the guided form. Scenario buttons prefill
   the five scripted paths the same way.
4. Confirm the intent in the form. `DEMO-P-NUB` + `DE` + `Net Sales` +
   Jan-Mar 2026 resolves to REUSE of the certified report (no approval
   needed); adding `Sales Forecast` becomes PROPOSE_CHANGE, which needs an
   approval; the logistics and quality scenarios propose new builds.
   Approvals are recorded against a separate simulated governance actor
   (default Synthetic Governance Approver) - the requester cannot approve
   their own proposal.
5. Approve or reject, then open the report preview for charts, totals,
   table and CSV/HTML/ZIP downloads. An approved render publishes a
   deterministic `GEN-...` asset; the Asset library lists it and
   **Open / reuse** starts a fresh session that resolves to REUSE.
6. Switch to the Finland-only identity and request Germany - the response is
   ACCESS_DENIED with no report details or values.

See `docs/DEMO_RUNBOOK.md` for the full launch checklist and
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

- All data is synthetic; identities, certification, governance actors and
  approvals are simulated role-play, not security controls - there is no
  authentication, authorization or role isolation.
- The offline parser is keyword-based, not general language understanding;
  it may miss unfamiliar requirements - always inspect the exact guided form
  before confirming.
- Report output is JSON, charts, a standalone HTML file and a CSV/JSON ZIP
  bundle - no PBIP/PBIX export or published destination exists.
- The optional LLM path is a thin adapter; its live provider behavior is not
  part of the automated test suite.
