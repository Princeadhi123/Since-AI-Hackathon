# Architecture

Smart Librarian is a modular monolith using a `src/` layout package
(`smart_librarian`). A multi-domain slice is implemented end to end over
synthetic fixtures: Sales (`data/demo_v1`, always) plus Logistics
(`data/demo_logistics_v1`) and Quality (`data/demo_quality_v1`) when those
sibling fixture directories exist.

## Layers

- **apps/streamlit_app.py** - Streamlit UI; HTTP client of the API only
  (httpx), no database or business logic.
- **api/app.py** - FastAPI transport: `create_app(demo_dir=, runtime_db=)`
  plus module-level `app` for uvicorn. Holds one `DemoCatalog` +
  `GovernedCatalog` + `WorkflowService` per available domain over a single
  shared `RuntimeStore`. Session-bound routes resolve the domain from the
  stored session state, never from a client parameter; catalog/assets/users/
  reuse/session-create accept an explicit `domain_id` (default `sales`).
- **workflow/service.py** - Session state machine: chat intake -> guided
  intent confirmation -> proposal -> simulated approval -> render ->
  publication. Binds identity to session, uses revision CAS for updates,
  rechecks fingerprint and permissions at approval/render, and re-checks
  snapshot coherence again after calculation before registering a generated
  asset. `record_approval` gates on a separate simulated governance actor
  (role + market scope), even on idempotent repeats.
- **domain/** - Deterministic core: `parser.py` (offline intent extraction),
  `decision.py` (ACCESS_DENIED / NEEDS_REVIEW / REUSE / PROPOSE_CHANGE /
  PROPOSE_BUILD, spec + spec_hash + deterministic asset identity),
  `executable_contract.py` (per-model catalog-vs-code checks dispatched by
  model_id), `operational_contracts.py` (lead-authored logistics/quality
  contracts), `governance.py` (fixed simulated approver/steward registry).
  No provider, API or UI imports.
- **catalog/store.py** - Read-only fixture catalog metadata, simulated
  users, choice lists, dataset fingerprint, plus `GovernedCatalog`: a
  runtime view that overlays generated reports and lineage (filtered to the
  current fingerprint and active lifecycle) without mutating the fixture.
- **reporting/** - `calculations.py` (fixed sales calculations),
  `operational.py` (fixed logistics/quality calculations) and `exports.py`
  (self-contained HTML report + CSV/JSON ZIP bundle from frozen render
  output only). The calculation modules are the only source of business
  values; exports never recompute them.
- **persistence/store.py** - Runtime SQLite sessions/approvals/audit plus
  the `generated_reports` registry (deterministic `identity_key` dedup,
  atomic publication that re-verifies the live session revision/proposal/
  approval); never touches fixture databases.
- **llm/client.py** - Optional OpenAI extraction adapter, reached only via
  the workflow and only when a request sets `use_llm=true` and a key is
  configured. Uses exactly the packaged `intent_prompt.txt`.

## Dependency direction

UI -> API -> workflow -> domain / catalog / reporting / persistence.

- `llm` is accessed only through the workflow adapter.
- Deterministic `domain` code must not import provider, API or UI modules.

## Data boundaries

- Scenario truth lives outside the runtime: `tests/fixtures/demo_scenarios.json`
  is acceptance-only and never a retrieval input.
- Demo fixtures (`data/demo_*_v1/`) are read-only; `persistence` never
  mutates them, and `create_app` refuses a `RUNTIME_DB_PATH` inside ANY
  fixture directory (validated for every discovered domain before the store
  is opened). The dataset fingerprint covers `catalog.json`, `demo.sqlite`,
  `products.csv`, `markets.csv` and `calendar.csv`, captured once at load;
  drift after load fails closed (409) until restart.
- Runtime SQLite lives under `var/` (git-ignored) and is shared by all
  domain services; generated assets carry the fingerprint they were
  rendered against, so a changed snapshot filters them out of discovery.

## Trust flow

1. Simulated user opens a session in a domain (identity + domain bound,
   market allow-list).
2. Chat text only produces a partial intent and clarifying questions - it
   never executes anything. The guided form is the authoritative confirmation.
3. The deterministic engine checks market access (all-or-nothing, no details
   leak on deny), scope validity, metric approval/support, model endorsement,
   owner, refresh health, coverage and candidate report lineage. Candidates
   are limited to reports fully visible to the requester's markets so a
   wider generated asset cannot leak through evidence.
4. REUSE needs no approval; PROPOSE_CHANGE / PROPOSE_BUILD create a pending
   proposal whose approval binds to the spec hash and is recorded against a
   separate simulated governance actor (approver role + market scope;
   requester self-approval and non-approver actors are refused), even on
   repeated decisions.
5. Rendering re-verifies fingerprint, access and governance, computes via
   the fixed engine for the session's domain, re-verifies the snapshot, then
   publishes the deterministic `GEN-` asset atomically against the live
   session revision - a stale render cannot publish. Rejected or stale
   proposals cannot render; repeated renders dedup to one registration.

## Not implemented

Power BI PBIP/PBIX export, real authentication, production authorization,
role isolation, asset lifecycle retirement, and a published report
destination (generated assets live in the local runtime registry behind
`/api/assets/{id}?domain_id=...`, which requires a `user_id` parameter).

## Transport

The API and UI bind `127.0.0.1` and serve plain HTTP, which is intentional
for the local demo only; it is not authentication or remote transport
security. Any remote or tunneled deployment requires TLS termination and real
authentication, neither of which is implemented here. Optional LLM provider
requests, when a user explicitly opts in, are separate from this loopback
transport.
