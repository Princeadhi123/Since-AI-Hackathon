# Challenge demo runbook

Local loopback demo only. Simulated identities and approvals; not real
Bayer performance and not production authorization.

## Launch

Foreground (stops when this terminal closes):

```powershell
python run_demo.py --mode challenge --api-port 8021 --ui-port 8521
```

Background (Windows only): registers a one-time Windows Task Scheduler
job for the current user that runs the same demo in the background, so
it keeps running after the launching terminal closes. The scheduled
supervisor runs `pythonw.exe` with **no console attached** and its
API/UI children run `python.exe` with `CREATE_NO_WINDOW` to avoid
console-close events; supervisor output is appended to
`artifacts/logs/launcher-<api>-<ui>.log` and child logs stay in
`artifacts/logs/`. The command prints the generated task name; stop it
later with `schtasks /End /TN <task-name>`. The task does not survive
logoff/reboot. Environment variables set only in the current shell are
not forwarded to the scheduled task (`.env` is still loaded). Prefer
the foreground command above while actively presenting.

```powershell
python run_demo.py --mode challenge --api-port 8021 --ui-port 8521 --background
```

Open http://127.0.0.1:8521. Other modes: `--mode public` (real-data-only
public sales), `--mode legacy` (synthetic multi-domain + public UI).

## 5-7 minute presentation order

1. Enter a request (or pick a sample) - show the raw request proposal.
2. Confirm the guided form explicitly (products/markets/metrics/period).
3. Select the accountable **active owner** - no default is chosen.
4. Create the plan - status `pending` (keep the same requester identity;
   a global requester such as `DEMO-CHALLENGE-REQUESTER` plus active
   owner `OWN-001` is the recommended pairing).
5. In the **Approval (separate actor)** block on the same page choose
   `DEMO-CHALLENGE-APPROVER` and approve - the plan is fingerprint-pinned
   to the current source workbook. Do not switch the sidebar identity;
   that clears the plan.
6. Render - the frozen report is a source-row snapshot; download
   HTML/CSV/ZIP/Power Query kit/PBIP.
7. Re-submit the same scope - `REUSE` returns the existing approved plan
   instead of re-rendering. Repeat for another domain or the estate
   proposal / refusal paths.

Suggested order across the 4 domains: commercial monthly report ->
supply snapshot -> market access snapshot -> launch events -> estate
proposal -> FI refusal/reuse guardrails.

## State and handoff

Plans, frozen reports and audit events persist in the runtime SQLite
(`var/runtime.sqlite`); downloads are plain local files with no access
control after export. A proposed production shape is Entra identities +
a managed asset registry + a governed artifact workspace - none of that
is implemented here. The accountable owner denotes proposed
responsibility, not enforced data certification.

## Focused scenarios

All flows share: pick a simulated requester identity, optionally extract
text, confirm the guided form explicitly, select an accountable **active
owner** (no default is chosen), create a plan, approve with the separate
simulated approver, render, preview and export.

1. **Commercial** - Nubeqa (P-NUB) Germany (DE), fields
   `net_sales_m_eur_syn` + `forecast_m_eur_syn`, months
   Jan-Mar 2026 (`2026-01-01`..`2026-03-01`), grain month.
2. **Supply** - P-NUB DE, fields `otif_pct_syn`, `inventory_weeks_syn`,
   `risk_status`; snapshot grain, no period.
3. **Market access** - P-NUB DE, `coverage_pct_syn` +
   `reimbursement_status`; snapshot grain.
4. **Launch** - P-NUB Japan (JP), `milestone_id`, `milestone_type`,
   `status`, month `2026-01-01`; event grain.
5. **Estate proposal** - Estate decisions tab, e.g. AST-0002 migrate
   proposal; approve yields "approved proposal; not executed".
   Reuse/negative guardrails: FI requester is denied non-FI scopes and
   estate access; steward cannot approve; equivalent approved scope is
   reused instead of re-rendered.

## Power BI export

The PBIP ZIP is a generated offline project (PBIR + embedded TMSL import
model): extract fully, open `GovernedReport.pbip`, then run **Refresh**
on first load (mandatory - it loads the embedded frozen snapshot into
the model, even if Desktop does not prompt),
then use the Dashboard / Source Evidence / Ownership & Evidence tabs.
There is no PBIX export, no service publish, no live connection.
Templates were checked with Power BI Desktop 2.159.1231.0. The fresh
four-domain browser acceptance exports were opened in Desktop and
Refresh was invoked on every project, including commercial. Rendered
dashboard screenshots and page-check logs are in
`artifacts/logs/pbi-accept-gate.log` and `pbi-accept-*.png`.
The browser evidence is in
`artifacts/downloads/team_acceptance_20261107_072528/`.
Validate in your target version. Chart measures return BLANK on
multi-row contexts and are never aggregated.

## Not implemented

Canonical/executable semantic equivalence of source estate records,
actual lifecycle execution (retire/migrate/consolidate are proposals
only), real authentication/authorization, TLS, Power BI service
publishing. The synthetic challenge workbook and the public sales
dataset are separate flows and never joined.
