# Smart Librarian

A governed analytics assistant over curated data catalogs. The product goal is
to let users ask business questions, clarify intent, and produce governed,
approvable report specifications over trusted catalog data - not a chatbot
that guesses SQL.

## Status

Implemented today:

- Project structure only (package skeleton under `src/`).
- Data preparation artifacts: the `data/demo_v1/` fictional fixture is the
  active fixture, produced by `create_demo_data.py`. The redundant generated
  `data/prepared/` snapshot was removed; `prepare_catalog.py` can regenerate
  optional snapshots later. The original source workbook is preserved.

Not implemented yet: the FastAPI service, Streamlit UI, LLM adapter, workflow
engine, governance enforcement, specification compiler, report renderer and BI
export. **The app is not running yet** - there is no server or UI to start.

## Layout

```
.
|-- prepare_catalog.py        # Stable entry point: workbook -> data/prepared snapshot
|-- create_demo_data.py       # Stable entry point: -> data/demo_v1 fixture
|-- pyproject.toml
|-- .env.example              # Future config placeholders (not consumed yet)
|-- apps/
|   `-- streamlit_app.py      # Docstring placeholder; no UI yet
|-- src/smart_librarian/      # Package skeleton (docstrings only)
|   |-- api/                  # FastAPI transport (planned)
|   |-- catalog/              # Read-only catalogs + parameterized search
|   |-- domain/               # Schemas, semantics, governance, spec compiler
|   |-- workflow/             # Intent clarification -> proposal -> approval
|   |-- llm/                  # Provider integration only (via workflow adapter)
|   |-- reporting/            # Deterministic query/render/export
|   `-- persistence/          # Sessions, approvals, audit (never fixture DBs)
|-- tests/
|   |-- fixtures/demo_scenarios.json   # Acceptance scenarios (never retrieval input)
|   `-- test_structure.py     # Structural smoke tests
|-- docs/
|   |-- ARCHITECTURE.md
|   |-- DATA_PLAN.md          # Data architecture and readiness plan
|   `-- DEMO_DATA_README.md   # demo_v1 fixture facts
|-- data/
|   `-- demo_v1/              # Independent fictional fixture (active business data)
`-- artifacts/                # Local validation output (git-ignored)
```

## Data separation

- **Source catalog**: the original workbook under `data/` (unchanged). Its
  generated `data/prepared/` export snapshot was removed as redundant; run
  `prepare_catalog.py` to regenerate it if needed.
- **Demo fixture**: entirely fictional data in `data/demo_v1/`.
- **Acceptance scenarios**: `tests/fixtures/demo_scenarios.json` - used only to
  check expected outcomes, never as retrieval input.
- **Runtime output**: future runtime SQLite lives in ignored `var/`; validation
  artifacts live in ignored `artifacts/`.

The two root generation scripts deliberately stay at the workspace root as
stable entry points to preserve their path assumptions and historical source
hashes. **Do not re-run `create_demo_data.py`** - it fails if its output
directory already exists.

## Development

No install or network needed for the structural smoke test:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest discover -s tests -p "test_*.py" -v
```

Optional (not executed; requires network and is for later stages):

```powershell
pip install -e ".[api,ui,llm,dev]"
```
