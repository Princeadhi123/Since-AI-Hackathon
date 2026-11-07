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
- Live LLM intent extraction (opt-in) followed by deterministic
  validation, an authoritative guided form, simulated approval, frozen
  source-row renders, and HTML/CSV/ZIP/Power Query kit/PBIP exports.
  **Snowflake Cortex is the recommended provider for team live tests** -
  see [Snowflake setup for testers](#snowflake-setup-for-testers);
  Aitta, OpenAI, and Featherless remain alternatives. Cloning the repo
  gives you no credential - each tester configures a local PAT. The LLM
  only proposes intent; it never computes values or bypasses approval.
  It does not claim general dashboard or report equivalence.

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

## Snowflake setup for testers

**Snowflake Cortex is the recommended provider for team live tests** -
four live extraction requests passed with this configuration on
2026-11-07 (see Verified state). Cloning the repo gives you **no credential**: each
tester configures a local PAT on their own machine. No model deployment
or workbook upload is needed, and no app code changes are required.

Prerequisites per tester:

- Your own clone + the install above (Python >= 3.11, internet).
- A valid Snowflake PAT for a user with Cortex access - prefer your own
  scoped PAT on a least-privilege role with
  `SNOWFLAKE.CORTEX_REST_API_USER` (or the broader `SNOWFLAKE.CORTEX_USER`)
  (steps in [docs/SNOWFLAKE_SETUP.md](docs/SNOWFLAKE_SETUP.md)).
- Your public outgoing IPv4 must be allowed for that Snowflake user.
  Sitting on the same Wi-Fi does not guarantee the same public IP
  (VPNs/proxies differ), and an allowed IP alone does not grant Cortex
  access. If your IP is refused, an admin must scope a user-level
  network policy to your IP - never `0.0.0.0/0` or an account-wide
  opening.

Team example account host (not a secret):
`TNRTNCL-SX96827.snowflakecomputing.com`. Your own account works the
same - substitute the hostname and an available model.

In one **private PowerShell** terminal at the repo root, foreground:

```powershell
$env:LLM_PROVIDER = 'snowflake'
$env:SNOWFLAKE_ACCOUNT_HOST = 'TNRTNCL-SX96827.snowflakecomputing.com'
$env:LLM_MODEL = 'claude-sonnet-4-6'
$cortexToken = Read-Host 'Snowflake PAT' -AsSecureString
$env:SNOWFLAKE_PAT = [System.Net.NetworkCredential]::new('', $cortexToken).Password
.\.venv\Scripts\python.exe run_demo.py --mode challenge --api-port 8025 --ui-port 8525
```

- The token is typed once, hidden, and lives only in that shell session.
  Never put the token literal in a shared file, chat, Git, docs, or a
  screenshot - and never echo `$env:SNOWFLAKE_PAT`. After the terminal
  closes, re-enter the variables in a new one.
- Process env overrides any `.env`. An already-running API does **not**
  pick up new shell variables - restart only your own launcher (Ctrl+C
  in its terminal, then rerun the block). `--background` is unsupported
  for this token flow: the scheduled task does not inherit shell-only
  variables.
- The launcher wires the UI to its own API port automatically. Keep the
  terminal open while testing.

### Verify a real Snowflake extraction

In a **second** PowerShell terminal (the first is busy running the
demo), run this read-only check - it makes no Cortex call:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8025/api/capabilities' | Select-Object provider, model, configured
```

Expected: provider `snowflake`, model `claude-sonnet-4-6`,
configured `True` - meaning credentials are **present**, not that
authentication succeeded.

Then in the UI (<http://127.0.0.1:8525>): workspace **Builder pack
reports**, Source domain **Commercial**, sidebar
`DEMO-CHALLENGE-REQUESTER`. Tick **"Send request text + catalog
metadata to the LLM"**, enter exactly `Show monthly Nubeqa net sales
and sales forecast in Germany for January through March 2026.` and
click **Extract intent**.

Expected: caption `last extraction: llm`; the form proposes products
`P-NUB`, market `DE`, source fields `net_sales_m_eur_syn` +
`forecast_m_eur_syn`, months `2026-01-01`..`2026-03-01`, grain month.
Confirm the form, choose owner `OWN-001`, and continue the normal
walkthrough (create/approve/render) - extraction alone creates nothing.
A caption `offline_fallback_after_llm_unavailable` means the live case
is **BLOCKED, not a pass** - the offline flow still works but records
no LLM pass.

Only the request text and catalog metadata are sent remotely - never
source business figures. Each extraction is a paid remote call; do not
type secrets or confidential text.

### Troubleshooting (Snowflake)

| Symptom | Fix |
| --- | --- |
| Offline-fallback caption | Check capabilities and the UI port first; an old instance can select a different provider. `configured=True` does not prove authentication. Review the reported error before changing settings. |
| Authentication error | Check whether the PAT is active, its role has access, and your public IP is allowed for that user; never share the token. |
| `max_tokens is deprecated` | `git pull` - the Snowflake request now sends `max_completion_tokens`; restart your own launcher (nothing else changes). |
| `openai package is not installed` | Rerun the pip install with the `[ui,llm,dev]` extra using the venv Python. |
| Port busy | Pick a fresh `--api-port`/`--ui-port` pair; never kill unknown processes. |

Optional manual connectivity check - a **single paid call**, not a
four-domain verification. In a configured private shell (stop your own
foreground launcher first if needed):

```powershell
.\.venv\Scripts\python.exe tests\live_snowflake_diagnostic.py --allow-provider-call
```

Output is credential-redacted; still review it before sharing.

### Other providers and offline testing

- Aitta: `LLM_PROVIDER=aitta` + `AITTA_API_TOKEN` +
  `LLM_MODEL=openai/gpt-oss-120b` - see
  [docs/AITTA_SETUP.md](docs/AITTA_SETUP.md). OpenAI: `openai` +
  `OPENAI_API_KEY` + `gpt-4.1-mini`. Featherless: `featherless` +
  `FEATHERLESS_API_KEY` + a catalog model id. A credential is only ever
  sent to its own provider.
- `.env` is local and git-ignored - never commit it. `.env.example`
  holds placeholders only: copy it only if you have no `.env`, or merge
  specific keys safely. Only the whitelisted keys in
  `src/smart_librarian/settings.py` are read; process env always wins.
  The runtime DB defaults to `var/runtime.sqlite`. Any credential
  committed historically should be rotated, not reused as a shared
  token.
- Offline testing needs no provider at all: uncheck the LLM box and use
  the domain **Prefill** buttons - the full guided workflow functions,
  it just is not an LLM pass. If the provider is unavailable the UI
  explicitly shows the offline-fallback warning - it never claims
  live-LLM success.

Running the demo with a team? Start with the easy step-by-step guide
[docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md) - 44 numbered
steps, each telling you what to do, what you should see, and what it
proves. It is the source of the rendered 45-slide deck
([HTML](docs/DEMO_SLIDES.html) / [PDF](docs/DEMO_SLIDES.pdf) /
[PowerPoint](docs/DEMO_SLIDES.pptx); HTML and PPTX are regenerated by
`docs/build_demo_slides.py`, the PDF via browser Print → Save as PDF).
[TEAM_DEMO_TEST_RUNBOOK.md](docs/TEAM_DEMO_TEST_RUNBOOK.md) is the
detailed reference for the same case IDs; results go in the blank
[CSV](docs/TEAM_DEMO_RESULTS_TEMPLATE.csv); index:
[docs/DEMO_QUICKSTART.md](docs/DEMO_QUICKSTART.md).

## Run the demo

Configure the provider env vars first (see Snowflake setup for testers
above), then in the same shell:

```powershell
.\.venv\Scripts\python.exe run_demo.py --mode challenge --api-port 8025 --ui-port 8525
```

Open http://127.0.0.1:8525 (UI). The API base is
http://127.0.0.1:8025 with interactive docs at
http://127.0.0.1:8025/docs. Loopback only - each user runs their own local
instance; do not expose the unauthenticated API remotely. If a port is
already serving something, use the exact printed URL - an older
instance may be running a different provider config.

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
  8000/8501 (the older Aitta example ports) - the Snowflake tester flow
  above uses 8025/8525; `--api-port`/`--ui-port` pick others.

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
- Snowflake Cortex live extraction was verified separately on
  2026-11-07: all four requests above returned extraction mode `llm`
  (no fallback) with the expected products/markets/metrics/periods/grain
  on model `claude-sonnet-4-6`. Evidence:
  `artifacts/logs/snowflake_live_20261107_170832_665939/results.json`
  and `artifacts/logs/snowflake_ui_recheck_20261107_173007_684893.json`
  (local, git-ignored). Approval/render/export/REUSE were not re-run
  under Snowflake - the end-to-end checks above used the earlier
  provider.
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
|-- .env / .env.example       # local .env ignored; .env.example = tracked placeholder
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
|                             # AITTA_SETUP.md, SNOWFLAKE_SETUP.md, DEPLOYMENT.md
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
(proposed architecture in `docs/DEPLOYMENT.md`), and rotate any
previously committed credentials.
