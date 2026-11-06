# Architecture

Smart Librarian is a modular monolith using a `src/` layout package
(`smart_librarian`). Layers are settled; implementations are planned.

## Layers

- **apps/streamlit_app.py** - Streamlit UI (placeholder; not implemented).
- **api** - FastAPI transport exposing workflows over HTTP.
- **workflow** - Orchestration from intent clarification through proposal and
  approval. The only layer that reaches the LLM, via an adapter.
- **domain** - Deterministic core: schemas, semantic definitions, governance
  rules, specification compiler.
- **catalog** - Read-only access to prepared catalogs and demo fixtures, plus
  parameterized searches.
- **reporting** - Deterministic query, render and export of approved specs.
- **persistence** - Runtime sessions, approvals and audit events.
- **llm** - Provider integration only.

## Dependency direction

UI -> API -> workflow -> domain / catalog / reporting.

- `llm` is accessed only through the workflow adapter.
- Deterministic `domain` code must not import provider, API or UI modules.

## Data boundaries

- Scenario truth lives outside the runtime: `tests/fixtures/demo_scenarios.json`
  is acceptance-only and never a retrieval input.
- Demo fixtures (`data/demo_v1/`) and prepared snapshots under `data/prepared/`
  are read-only; `persistence` never mutates fixture databases. The generated
  `data/prepared/` snapshot was removed as redundant; `prepare_catalog.py` can
  regenerate optional snapshots later.
- Future runtime SQLite lives under `var/` (git-ignored).

## Not implemented

Chat, LLM adapter, governance enforcement, specification compiler, approval
workflow, report renderer, BI export, API endpoints and the UI are all planned
but absent. No server is running or needed at this stage.
