# Deployment

## What exists today (local loopback)

- FastAPI on `127.0.0.1:8000`, Streamlit on `127.0.0.1:8501`, plain HTTP.
- Multi-domain demo: Sales (always), plus Logistics and Quality when their
  sibling fixture directories (`data/demo_logistics_v1`,
  `data/demo_quality_v1`) exist next to the sales fixture.
- Runtime state in a single SQLite file (`var/runtime.sqlite` by default):
  sessions, approvals, audit events and the generated-report registry. The
  fixture catalogs are read-only; `RUNTIME_DB_PATH` resolving inside the
  fixture directory is refused at startup.
- Simulated identities (`DEMO-USER-*`) per domain catalog and simulated
  governance actors (`DEMO-APPROVER`, `DEMO-STEWARD`) from a fixed in-code
  registry. Approvals are bound to the acting actor and audited with the
  requester id - **this is role simulation, not authentication**.
- Optional LLM intent extraction: off by default; only runs when a request
  sets `use_llm` AND `OPENAI_API_KEY` is configured (process env or `.env`).
  No other provider calls exist.

## Not implemented (explicitly)

- TLS, authentication, authorization, role isolation, tenant isolation.
- PBIP/PBIX export or a published report destination; generated assets live
  in the local runtime registry behind `/api/assets/{id}`.
- Lifecycle management (retire/deprecate generated assets), ownership
  transfer.
- Live data refresh; every dataset is a frozen synthetic snapshot.

## Proposed production shape (future work - nothing below is built)

- **Hosting**: Azure Container Apps (or App Service) behind a TLS-terminating
  ingress; Streamlit replaced or fronted by the same ingress; no plain-HTTP
  loopback assumptions.
- **Identity**: Microsoft Entra ID (OIDC) for sign-in; app roles/groups map
  to requester/approver/steward personas, replacing the simulated actor
  registry. Approver authority must come from the IdP token, never a request
  field.
- **Data**: managed relational store (e.g. Azure Database for PostgreSQL or
  Azure SQL) for the runtime registry and audit log, replacing the SQLite
  file; encrypted at rest, network-restricted.
- **Governance workflow**: real owner approval queue for PROPOSE_BUILD /
  PROPOSE_CHANGE publication; separation-of-duties enforced server-side;
  retention and asset retirement policies for the registry.
- **Refresh**: scheduled, audited dataset refresh pipelines producing new
  fingerprinted snapshots; approvals remain bound to the snapshot they were
  issued against.
- **Backup/DR**: managed DB backups; fixture catalogs versioned in artifact
  storage with recorded provenance hashes.
