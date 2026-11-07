# Demo Runbook - morning-of launch checklist (Windows)

Everything below is local loopback only. All data is synthetic; identities,
roles, certification and approvals are simulated.

## Pre-flight (5 minutes)

1. Open a PowerShell window in the repo root.
2. Verify Python and deps: `python --version` (3.11+); all demo dependencies
   are already installed in this environment.
3. Optional LLM extraction: copy `.env.example` to `.env` and set
   `LLM_PROVIDER` plus the matching credential - `AITTA_API_TOKEN` for CSC/
   LUMI Aitta (see `docs/AITTA_SETUP.md`) or `OPENAI_API_KEY` for OpenAI.
   The app loads `.env` automatically; process env wins. Only
   `OPENAI_API_KEY`, `AITTA_API_TOKEN`, `LLM_PROVIDER`, `LLM_MODEL`,
   `DEMO_DATA_DIR` and `RUNTIME_DB_PATH` are read from `.env` - everything
   else is ignored. **Offline mode is the default**: without a key nothing
   calls the provider and the offline parser handles extraction. The sidebar
   shows "LLM provider: not configured" in that case.
4. Check ports are free: the launcher refuses to start if 8000 or 8501 is
   already in use rather than killing the unknown process.

## Launch

```powershell
python run_demo.py
```

- API on http://127.0.0.1:8000, UI on http://127.0.0.1:8501 by default.
- Logs are per-port append-only files: `artifacts/logs/api-<port>.log` and
  `artifacts/logs/ui-<port>.log`.
- Ctrl+C stops only the children the launcher spawned.

Manual equivalent (two windows):

```powershell
$env:PYTHONPATH = 'src'
python -m uvicorn smart_librarian.api.app:app --host 127.0.0.1 --port 8000

$env:PYTHONPATH = 'src'
python -m streamlit run apps/streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

## The five demo paths

The sidebar has a **Domain** selector (Sales, Logistics / Distribution,
Manufacturing Quality) above the identity selector; switching either resets
the session. Scenario buttons only prefill the guided form - always confirm
the exact scope yourself; the Approver actor is a separate simulated identity
selectable in the approval panel.

1. **Sales reuse** (Sales domain): scenario button "Sales reuse" or type
   `Nubeqa Germany Net Sales January through March 2026`. Confirm - REUSE of
   the certified seed report, no approval needed, open the preview.
2. **Sales extension** (Sales): "Sales extension" scenario adds Sales
   Forecast - PROPOSE_CHANGE, approve as the simulated approver, render; a
   `GEN-...` asset is published into the runtime registry.
3. **Logistics** (Logistics domain): "Cold Chain Germany Q1" with all three
   metrics (Delivered Orders, On Time %, Lead Time) - PROPOSE_BUILD, approve,
   render, publish.
4. **Quality** (Quality domain): "Tablet Line A Germany Q1" with all four
   metrics - same build/approve/render/publish path.
5. **Access denied** (Sales, DEMO-USER-FI identity): any Germany scope -
   ACCESS_DENIED with no report details or values returned.

## Cross-session reuse walkthrough

After path 2/3/4 publishes a `GEN-...` asset:

1. Open the **Asset library** expander (sidebar/main) - the new asset shows
   with owner, endorsement `promoted`, origin `generated`.
2. Click **Open / reuse** - a fresh session is created and the stored scope
   is confirmed through the normal decision flow; the outcome is REUSE.
3. Or start a new session and confirm the same scope by hand - the decision
   engine resolves the generated asset deterministically; the same scope
   always maps to the same asset id, even across restarts and users (subject
   to market permissions and the dataset fingerprint).

## Artifacts

From the report preview: CSV rows, a **standalone HTML report** (fully
offline, no CDN/scripts) and a **ZIP bundle** (report.html, report.csv,
specification.json, README.txt with Power BI CSV import steps). Open the
HTML by double-clicking; share the ZIP as a file. There is no PBIP/PBIX
export - CSV import is the only supported Power BI path.

## Recovery (no destructive resets)

- UI shows stale or odd state: click **New request** in the sidebar (fresh
  session, runtime registry preserved).
- API down: the UI shows the unreachable banner; restart `run_demo.py`. The
  runtime SQLite keeps sessions and generated assets.
- Catalog file changed mid-demo: the fingerprint drift check fails closed
  (409). Restart the API to reload a coherent snapshot; generated assets
  bound to the old fingerprint are filtered out, not deleted.
- Resume a session after a UI reload: append `?session_id=<id>` to the UI
  URL once; ownership is still enforced.

## If ports 8000/8501 are already in use

The launcher never kills unknown processes. Use alternate ports:

```powershell
python run_demo.py --api-port 8001 --ui-port 8502
```

**Current environment**: 8000/8501 are occupied by pre-existing unknown
processes; the demo is running at API http://127.0.0.1:8001 and UI
http://127.0.0.1:8502 (logs `api-8001.log` / `ui-8502.log`).

**Fresh PROPOSE_BUILD scope**: the runtime registry already contains the
published demo assets from previous runs, so repeating Cold Chain Germany
Q1 or Tablet Line A Germany Q1 resolves to REUSE. To demonstrate a fresh
build path pick an unpublished scope instead, e.g. Standard Freight +
Finland (logistics) or Packaging Line B + Finland (quality), or any
different month set.
