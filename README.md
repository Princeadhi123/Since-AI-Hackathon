# Smart Librarian

A locally governed analytics prototype for Bayer's "Build Less, Build
Better" challenge. Users phrase business requests in natural language,
get explicit intent extraction, confirm a guided scope, route it through
simulated approval, and receive fingerprint-pinned frozen reports - no
SQL guessing, no silent inference.

Data basis: the official SinceAI synthetic builder pack - four report
domains plus a source estate. Nothing here is real Bayer performance or
internal data.

## Status

Implemented and locally verified for the four scenarios below:

- Four governed report domains - commercial monthly, supply snapshot,
  market access snapshot, launch events - plus estate lifecycle
  proposals (approved but never executed).
- Live LLM intent extraction (opt-in, CSC Aitta) followed by
  deterministic validation, an authoritative guided form, simulated
  approval, frozen source-row renders, and HTML/CSV/ZIP/Power Query
  kit/PBIP exports. The LLM only proposes intent; it never computes
  values or bypasses approval. It does not claim general dashboard or
  report equivalence.

## Setup (fresh clone)

Requires Python >= 3.11 (see `pyproject.toml`). Windows is needed only
for the `--background` launcher option and Power BI Desktop checks;
the app itself is platform-neutral.

```powershell
git clone https://github.com/Princeadhi123/Since-AI-Hackathon.git
cd Since-AI-Hackathon
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ui,llm,dev]"
```

Commands below use `.\.venv\Scripts\python.exe` explicitly so no
PowerShell activation step (or execution-policy change) is needed.
Installation requires network access; the app itself then runs fully
locally - no provider network is used unless you opt into LLM
extraction.

Power BI Desktop is optional and only needed to open PBIP exports;
project (PBIP) support is required and templates were checked with
version 2.159.1231.0 - validate in your target version.

The source workbook `data/Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx`
(read-only) and all data fixtures are tracked in the repo - no
regeneration step is needed. Do not edit the workbook, the frozen
evidence JSONs under `data/evidence/`, or place a runtime DB under
`data/` (challenge mode refuses to run with the runtime DB inside
`data/`).

## Configuration (.env)

This repository currently tracks a `.env` with a **temporary shared
event credential** (CSC Aitta) committed deliberately for the hackathon
- do not print or copy the real value. Recommendations:

- Prefer your own credential via process environment (process env always
  wins over `.env`).
- The shared event token may expire, be revoked, or hit rate limits;
  rotate it after the event.
- `.env.example` contains placeholders only - use it as a reference if
  `.env` is missing; do not overwrite the tracked `.env` blindly.
- Only the whitelisted keys in `src/smart_librarian/settings.py` are
  read; everything else in `.env` is ignored. The runtime DB defaults to
  `var/runtime.sqlite`.

Typical contents (placeholders):

```dotenv
LLM_PROVIDER=aitta
LLM_MODEL=openai/gpt-oss-120b
AITTA_API_TOKEN=<your-token>
```

For OpenAI instead set `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-4.1-mini`
and `OPENAI_API_KEY`; use only the matching provider credential. See
[docs/AITTA_SETUP.md](docs/AITTA_SETUP.md) for Aitta access. The app and
any Power BI project run locally, but LLM inference is a **remote** call
to Aitta (or OpenAI when selected) - it needs internet and a valid
credential. The opt-in is the
"Send request text + catalog metadata to the LLM" checkbox on the
challenge Builder page; the request text and catalog metadata (no source
business figures) are sent - never enter secrets or confidential text.
If the provider is unavailable the UI explicitly shows the offline
fallback warning - it never claims live-LLM success.

## Run the demo

```powershell
.\.venv\Scripts\python.exe run_demo.py --mode challenge --api-port 8021 --ui-port 8521
```

Open http://127.0.0.1:8521 (UI). The API base is
http://127.0.0.1:8021 with interactive docs at
http://127.0.0.1:8021/docs. Loopback only - each user runs their own local
instance; do not expose the unauthenticated API remotely.

- Foreground mode keeps the terminal open; Ctrl+C stops only the
  children it spawned. Busy ports? Pick different `--api-port`/
  `--ui-port` values - the launcher refuses to start rather than kill an
  unknown process.
- Windows `--background` registers a unique current-user scheduled task
  running `pythonw.exe` (no console) with `CREATE_NO_WINDOW` children.
  The printed task name stops it: `schtasks /End /TN <task-name>`. It
  does not promise survival across logoff/reboot or soak-level uptime,
  and shell-only environment variables are not forwarded to the task
  (`.env` is still loaded). Logs land in `artifacts/logs/`, plans in
  `var/runtime.sqlite`.
- Bare `python run_demo.py` also defaults to challenge mode but on ports
  8000/8501 - `--api-port`/`--ui-port` pick others.

Mode table:

| Mode | What it serves |
| --- | --- |
| `challenge` (launcher default) | Official synthetic builder pack: 4 domains, estate, challenge API/UI |
| `public` | Real-data-only: 15 published products/families, 10 reporting periods, global EUR million |
| `legacy` | 3 fictional synthetic domains + old 4-product annual public view |

Note: the raw module `smart_librarian.api.app:app` defaults to the
**public** real-data-only app - different from the launcher's challenge
default. Manual uvicorn for challenge must use
`--factory smart_librarian.api.app:create_challenge_app`.

## Challenge walkthrough (end to end)

1. Keep the sidebar identity on `DEMO-CHALLENGE-REQUESTER`; pick a
   domain in **Builder pack reports**.
2. Check the LLM opt-in checkbox, enter request text, click **Extract
   intent**. Inspect the extraction - then explicitly confirm/adjust the
   guided form (products/markets/source fields/months; nothing is
   inferred silently).
3. Select an accountable **active owner** (e.g. `OWN-001` - no default
   is chosen) and click **Create plan** - status `pending`. If an
   equivalent approved scope already exists the plan is **REUSE**d
   immediately instead.
4. In the **Approval (separate actor)** block on the same page choose
   `DEMO-CHALLENGE-APPROVER` and approve - do not switch the sidebar
   identity (that clears the plan). Then **Render frozen report**,
   preview, and download.
5. Saved plans persist in the local `var/runtime.sqlite` (git-ignored,
   not cloned).

Exact verified requests:

| Domain | Request text |
| --- | --- |
| commercial | `Show monthly Nubeqa net sales and sales forecast in Germany for January through March 2026.` |
| supply | `Show a current snapshot of Nubeqa in Germany: on-time in-full, inventory in weeks, and supply risk status.` |
| market_access | `Show the current market access snapshot for Nubeqa in Germany: coverage percentage and reimbursement status.` |
| launch | `Show Nubeqa launch milestones in Japan in January 2026, including milestone ID, milestone type, and status.` |

Guardrails worth showing: the estate flow (e.g. asset `AST-0002`,
action `migrate`) approves a proposal that is **not executed**; an FI
identity attempting a non-FI scope is refused (403); a steward cannot
approve a pending plan. Reuse/duplicate guardrails reuse approved scope
rather than re-rendering - they do not claim source-estate reports are
replaceable duplicates.

## Power BI export

Five formats: HTML, CSV, ZIP bundle, Power Query kit (CSV + M script +
theme for manual import), and PBIP project ZIP (generated offline PBIR
+ embedded TMSL import model with native charts plus Source Evidence
and Ownership & Evidence pages - different from the manual kit).

Download the PBIP ZIP, extract the full tree keeping
`.Report`/`.SemanticModel` beside `GovernedReport.pbip`, open it in
Power BI Desktop, and run **Refresh on first load (mandatory)** - it
loads the embedded frozen snapshot into the model, not new business
data. There is no PBIX export, no service publish, no live connection,
no scheduled refresh. Chart measures return BLANK on ambiguous
multi-row contexts and are never summed or averaged; source values stay
in native units (snapshots show no invented time trends).

## Verified state (as of 2026-11-07)

- Four requests above driven through a real browser with live LLM
  extraction: pending plan, steward refusal, separate approver, frozen
  render, five real downloads, identical-resubmit REUSE - per domain
  (commercial approval/render was captured in an earlier partial pass;
  the final pass reused it; the other three ran the full fresh pending
  flow).
  `/extract` responses were captured via direct API calls with identical
  payloads (the UI calls the API server-side); UI-side mode caption and
  form prefill were asserted separately - the API captures are not the
  UI's own response objects.
- Power BI Desktop: all four new PBIP projects opened, actual Refresh
  invoked on each, and all three pages screenshotted and reviewed.
- Tests: full suite of 347 tests passed on an earlier code state;
  26 focused tests (launcher + mocked offline-fallback UI) pass on the
  final code.
- Evidence under `artifacts/logs/` (`verification-final-e2e-v2.txt`,
  `launcher-final-narrow.txt`, `pbi-accept-gate.log`) and
  `artifacts/downloads/team_acceptance_20261107_072528/` is local and
  git-ignored - not part of a fresh clone.
- Live provider behavior is not part of the automated suite; the
  provider-outage path is covered by a mocked fallback test. These are
  finite checks, not a soak test or a general accuracy guarantee.

## Tests

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Focused suites: `test_challenge.py`, `test_pbip_dashboard.py`,
`test_launcher_config.py`.

## Layout

```
.
|-- run_demo.py               # Launcher: API + UI, foreground or --background
|-- pyproject.toml            # Python >= 3.11, extras: ui, llm, dev
|-- .env / .env.example       # Whitelisted config keys (tracked .env = event cred)
|-- apps/streamlit_app.py     # Streamlit UI (HTTP client of the API only)
|-- src/smart_librarian/
|   |-- challenge.py          # Read-only workbook contracts/source engine
|   |-- api/challenge.py      # /api/challenge/* router
|   |-- workflow/challenge.py # Extract/plan/approve/render service
|   |-- ui/challenge.py       # Challenge Streamlit workspaces
|   |-- reporting/challenge_pbip.py + challenge_pbip_dashboard.py
|   |-- persistence/store.py  # Runtime SQLite: plans, audit, reports
|   `-- settings.py           # Env/.env whitelisting, paths, provider status
|-- docs/                     # ARCHITECTURE.md, CHALLENGE_DEMO.md,
|                             # AITTA_SETUP.md, DEPLOYMENT.md
|-- data/                     # Source workbook (read-only) + frozen evidence
|-- var/                      # Runtime SQLite (git-ignored, auto-created)
`-- artifacts/                # Local logs + validation evidence (git-ignored)
```

## Limitations / future work

Not implemented: real authentication/authorization, TLS, role
isolation, Power BI service publishing or any managed hosting, lifecycle
execution (proposals never mutate the estate), canonical/executable
semantic equivalence, and general-purpose reporting beyond the curated
catalogs.

Suggested next steps for a team: broaden manual UX and edge-case
coverage, keep the governance controls and frozen-evidence guarantees
intact while extending, design the presentation and deployment shape
(proposed architecture in `docs/DEPLOYMENT.md`), and rotate the shared
event credential.
