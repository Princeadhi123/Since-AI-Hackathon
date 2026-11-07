# Smart Librarian: complete team demo test runbook

This is the detailed reference: 44 numbered sections covering the same
37 test cases as the easy step-by-step guide `DEMO_WALKTHROUGH.md` (the
source of the generated deck). It is a manual test plan, not a record
of tests executed today - record actual results separately. The four datasets
are Commercial, Supply, Market Access, and Launch from the official
synthetic challenge builder pack, not real Bayer performance.

## 01 | The whole demo in one picture
- Do: Follow this path: ask a question -> check the form -> choose an owner -> create a plan -> get approval -> render -> download -> repeat.
- See: A written request becomes a governed, frozen report. Repeating the same approved scope can return the existing plan: REUSE.
- Proves: The demo joins natural-language intake, human decisions, source-backed reports, and reuse.
- Remember: The business data and roles are synthetic. The LLM is real, but it does not calculate the report or approve anything.

## 02 | Install once on each tester's computer
- Do: In PowerShell, clone the project and install it. If you already have this clone, use its folder and skip the first two commands.
```powershell
git clone https://github.com/Princeadhi123/Since-AI-Hackathon.git
cd Since-AI-Hackathon
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ui,llm,dev]"
```
- See: Installation finishes without an error. Your project now has a .venv folder.
- Proves: This computer has the software needed to run the demo; this is not yet an LLM test.
- Remember: Python 3.11+ and internet are required. Do not edit the source workbook or frozen evidence files.

## 03 | Connect Snowflake before starting the app
- Do: Obtain a valid, scoped Snowflake PAT privately. Your Snowflake user must allow this computer's public outgoing IP. Enter these commands in the PowerShell you will launch from.
```powershell
$env:LLM_PROVIDER = 'snowflake'
$env:SNOWFLAKE_ACCOUNT_HOST = 'TNRTNCL-SX96827.snowflakecomputing.com'
$env:LLM_MODEL = 'claude-sonnet-4-6'
$cortexToken = Read-Host 'Snowflake PAT' -AsSecureString
$env:SNOWFLAKE_PAT = [System.Net.NetworkCredential]::new('', $cortexToken).Password
```
- See: The token prompt hides what you paste. The commands finish without printing the token.
- Proves: You supplied local configuration. A successful live request is still needed to prove access.
- Remember: Same Wi-Fi is not a credential. Never share the PAT in Git, chat, screenshots, or slides. No model deployment is needed.

## 04 | Choose a clean test or use existing plans
- Do: For every fresh approval check, run the commands below in that configured PowerShell. If 8025/8525 are busy, change BOTH ports, for example to 8026/8526.
```powershell
$env:RUNTIME_DB_PATH = "var/team-demo-$([guid]::NewGuid().ToString('N')).sqlite"
.\.venv\Scripts\python.exe run_demo.py --mode challenge --api-port 8025 --ui-port 8525
```
- See: API ready and UI ready, with the URLs to open. A new database under var/ preserves your existing plans.
- Proves: A clean run lets you exercise pending -> approval -> render instead of immediately getting REUSE.
- Remember: For existing-state REUSE, skip the fresh launch and use your verified running Snowflake instance. Keep the terminal open; do not use --background.

## 05 | Open the correct demo, not the old preview
- Do: Open the UI URL printed by your launcher: normally http://127.0.0.1:8525. In a SECOND PowerShell, check the API below; change its port if you chose another pair.
```powershell
Invoke-RestMethod 'http://127.0.0.1:8025/api/capabilities' |
  Select-Object provider, model, configured
```
- See: snowflake / claude-sonnet-4-6 / True. In the UI, choose Builder pack reports and keep DEMO-CHALLENGE-REQUESTER in the sidebar.
- Proves: You reached the intended backend and it has a credential. This read-only check does not prove authentication.
- Remember: An old 8501/8000 instance may still use Aitta. Use the new printed URL, not an old preview. Do not expose this unauthenticated demo publicly.

## 06 | Read the status: what happens next?
- Do: Use the status to choose your next click. llm = extraction succeeded; pending = waiting; approved = ready to render; rendered = frozen report available; REUSE = existing approved scope found.
- See: Pending: choose an approver. Approved: click Render frozen report. Rendered: inspect and download. REUSE: check the returned plan ID and existing result.
- Proves: Extraction, approval, rendering, and reuse are different steps, not one automatic AI action.
- Remember: REUSE is not a failure. An approved-but-not-rendered reused plan still needs rendering; a rendered reused plan already has a frozen result.

## 07 | Know when a test really passed
- Do: For each case, save the request, unedited form, status, plan ID, and a screenshot. Compare what you actually see with this guide before correcting anything.
- See: last extraction: llm is a live result. offline_fallback_after_llm_unavailable means the live case is BLOCKED, not passed.
- Proves: Your evidence distinguishes real model output from offline parsing, manual edits, and steps you did not run.
- Remember: A checkbox alone proves nothing. Do not press Prefill to make a live extraction look correct. Use the blank team results CSV.

## 08 | C1: Commercial - exact LLM request
- Workspace Builder pack reports; Source domain Commercial; requester DEMO-CHALLENGE-REQUESTER.
```text
Show monthly Nubeqa net sales and sales forecast in Germany for January through March 2026.
```
- Paste into Describe the report, tick the LLM opt-in, click Extract intent, and wait for completion.
- Expected: last extraction: llm. Save a screenshot of the request, caption, and any warnings before changing the form.

## 09 | C2: Commercial - confirm exact scope
- Products: Nubeqa (P-NUB). Markets: Germany (DE).
- Source fields: net_sales_m_eur_syn and forecast_m_eur_syn.
- Months: 2026-01-01, 2026-02-01, 2026-03-01. Grain: month.
- Inspect Guided confirmation (authoritative). Record any mismatch, then explicitly correct it if continuing.
- Accountable owner: choose active OWN-001 yourself; no default is selected. Rationale: Team Commercial live LLM test.
- Expected: Create plan (requires approval) becomes enabled. Capture the confirmed form.

## 10 | C3: Commercial - refuse steward, then approve
- Click Create plan (requires approval). Record plan ID, revision, spec hash, and status. Fresh DB expected: pending.
- If REUSE appears, use C5 and record fresh approval/steward checks as not exercised on this plan; use a fresh test DB for those checks.
- In Approval (separate actor), choose DEMO-CHALLENGE-STEWARD and click Approve.
- Expected: API error 403; steward is not an approver; plan remains pending. Capture refusal.
- In the SAME block choose DEMO-CHALLENGE-APPROVER and click Approve. Expected: approved. Capture status and Audit trail.
- Do not switch the sidebar requester identity. It clears current UI plan state.

## 11 | C4: Commercial - render, inspect, download
- Click Render frozen report. Expected: rendered; monthly chart plus frozen source-row table and Audit trail.
- Expected scope: Nubeqa/Germany, Jan-Mar 2026; three source rows, million EUR units, no aggregation. January source values: net sales 19.66, forecast 18.42; value_type forecast_like_synthetic. These are synthetic, not actual performance.
- Download ALL five: HTML, CSV, ZIP bundle, Power Query kit (CSV+M), Power BI project (PBIP ZIP).
- Save under a Commercial-specific evidence folder; export names repeat across domains, so avoid overwriting.
- Open HTML and CSV; compare selected fields, dates, values, units, and source provenance with the frozen preview. Inspect ZIP/kit contents; follow G2-G3 for Power BI.

## 12 | C5: Commercial - prove repeat-request REUSE
- After rendering, record original plan ID and spec hash. Keep the same requester and owner OWN-001.
- Re-enter the exact C1 request with LLM enabled, click Extract intent, and capture last extraction: llm again.
- Confirm EXACTLY the C2 product, market, fields, months, grain, and owner; click Create plan (requires approval).
- Expected: equivalent approved scope already exists / REUSE. Returned plan ID and spec hash match the original; status is rendered and the original frozen result is available.
- No new pending plan or new approval is needed. Re-download CSV and compare its source rows with the first CSV; do not use volatile ZIP bytes as a reuse test.
- Capture original and reused IDs, the REUSE notice, and Audit trail. Keep source fingerprint unchanged.

## 13 | S1: Supply - exact LLM request
- Return to Builder pack reports; choose Source domain Supply; keep DEMO-CHALLENGE-REQUESTER.
```text
Show a current snapshot of Nubeqa in Germany: on-time in-full, inventory in weeks, and supply risk status.
```
- Enter Describe the report, ensure LLM opt-in is checked, click Extract intent.
- Expected: last extraction: llm. Capture request/caption/warnings before edits. Do not use the Prefill button as extraction evidence.

## 14 | S2: Supply - confirm snapshot scope
- Products P-NUB; Markets DE.
- Source fields otif_pct_syn, inventory_weeks_syn, risk_status.
- Grain snapshot; months empty. Expected caption: Snapshot source: no period selection applies.
- There must be no invented dated trend. Record extraction mismatches before correcting the authoritative form.
- Explicit owner OWN-001; rationale Team Supply live LLM test. Capture completed form.

## 15 | S3: Supply - pending, steward refusal, approval
- Click Create plan (requires approval); record ID, revision, hash. Fresh DB expected: pending. If REUSE, follow S5 and mark fresh-only checks not exercised.
- Approval block: choose DEMO-CHALLENGE-STEWARD, click Approve. Expected API error 403 and unchanged pending status.
- Choose DEMO-CHALLENGE-APPROVER in that block; click Approve. Expected approved.
- Keep the sidebar identity unchanged. Capture pending, refusal, approved, and Audit trail.

## 16 | S4: Supply - frozen snapshot and all exports
- Click Render frozen report. Expected rendered; snapshot bars for numeric fields and a table preserving categorical risk_status.
- For P-NUB/DE, source values include otif_pct_syn 87.9 and inventory_weeks_syn 8.8. Preserve the source risk label and native units; no invented monthly series or totals.
- Download HTML, CSV, ZIP bundle, Power Query kit (CSV+M), Power BI project (PBIP ZIP) into a Supply-specific folder.
- Open HTML/CSV, compare to preview, inspect ZIP/kit, and perform G2-G3 for this domain's PBIP.
- Capture table, chart, Audit trail, and evidence filenames.

## 17 | S5: Supply - repeat live request and REUSE
- Record rendered Supply plan ID/hash; repeat S1 with LLM opt-in and capture last extraction: llm.
- Confirm P-NUB/DE; otif_pct_syn, inventory_weeks_syn, risk_status; empty months; snapshot; SAME owner OWN-001.
- Click Create plan (requires approval). Expected REUSE of original plan ID/hash, rendered status, original frozen result.
- No fresh approval needed. Re-download CSV and compare source rows. Capture notice, original/reused IDs, and Audit trail.
- A dated period or changed owner is not this identical-scope test.

## 18 | M1: Market Access - exact LLM request
- Builder pack reports; Source domain Market Access; requester DEMO-CHALLENGE-REQUESTER.
```text
Show the current market access snapshot for Nubeqa in Germany: coverage percentage and reimbursement status.
```
- Enter request, tick LLM opt-in, click Extract intent; capture last extraction: llm and any warnings before edits.
- The request is for a current snapshot, not a month-by-month trend.

## 19 | M2: Market Access - confirm exact form
- Products P-NUB; Markets DE.
- Source fields coverage_pct_syn and reimbursement_status.
- Grain snapshot; months empty; no period selector applies. Record mismatches before manual correction.
- Explicit owner OWN-001; rationale Team Market Access live LLM test.
- Expected Create plan enabled. Capture completed authoritative form.

## 20 | M3: Market Access - governance checks
- Create plan; record ID/hash/revision. Fresh DB expected pending; existing REUSE means fresh-only checks are not exercised.
- Choose DEMO-CHALLENGE-STEWARD in Approval (separate actor); Approve must show API error 403, status still pending.
- Choose DEMO-CHALLENGE-APPROVER in the same block; Approve must yield approved.
- Keep DEMO-CHALLENGE-REQUESTER in the sidebar. Capture pending/refusal/approval and Audit trail.

## 21 | M4: Market Access - render and export
- Click Render frozen report. Expected rendered snapshot chart/table; coverage_pct_syn is 65.6 for P-NUB/DE.
- Preserve reimbursement_status as a category, not a number. No invented historical series or averaged percentages.
- Download HTML, CSV, ZIP bundle, Power Query kit (CSV+M), Power BI project (PBIP ZIP) into a Market Access-specific folder.
- Open HTML/CSV, compare values/units/scope/provenance to the preview, inspect ZIP/kit, and perform G2-G3 on this PBIP.
- Capture table, chart, Audit trail, and evidence filenames.

## 22 | M5: Market Access - repeat live request and REUSE
- Record rendered plan ID/hash, repeat M1 with LLM enabled, and capture last extraction: llm.
- Confirm P-NUB/DE; coverage_pct_syn and reimbursement_status; empty months; snapshot; same owner OWN-001.
- Create plan. Expected REUSE, same original plan ID/hash and rendered frozen result; no new pending approval.
- Re-download CSV and compare source rows with initial export. Capture notice/IDs/Audit trail.

## 23 | L1: Launch - exact LLM request
- Builder pack reports; Source domain Launch; requester DEMO-CHALLENGE-REQUESTER.
```text
Show Nubeqa launch milestones in Japan in January 2026, including milestone ID, milestone type, and status.
```
- Enter request, enable LLM opt-in, click Extract intent; capture last extraction: llm and warnings before edits.
- Japan is JP, not Germany DE. Launch is an event dataset, not a sales or snapshot dataset.

## 24 | L2: Launch - confirm event scope
- Products P-NUB; Markets JP.
- Source fields milestone_id, milestone_type, status.
- Months 2026-01-01; grain event. Explicit owner OWN-001; rationale Team Launch live LLM test.
- Record any extraction mismatch before correcting the authoritative form.
- Expected Create plan enabled. Capture completed form with Japan and January visible.

## 25 | L3: Launch - pending and separate approval
- Click Create plan; record ID/hash/revision. Fresh DB expected pending; if REUSE, follow L5 and record fresh-only checks not exercised.
- Choose DEMO-CHALLENGE-STEWARD in the approval block; click Approve. Expected API error 403, pending unchanged.
- Choose DEMO-CHALLENGE-APPROVER in the SAME block; click Approve. Expected approved.
- Do not change sidebar requester. Capture pending/refusal/approved and Audit trail.

## 26 | L4: Launch - inspect events and all downloads
- Click Render frozen report. Expected rendered event table; do not require a numeric chart for categorical milestone fields.
- Check source event LM-0001 for P-NUB/JP with milestone_date 2026-01-05T00:00:00; preserve source milestone_type and status.
- No invented event totals, monthly sales, or snapshot trends.
- Download HTML, CSV, ZIP bundle, Power Query kit (CSV+M), Power BI project (PBIP ZIP) into a Launch-specific folder.
- Open HTML/CSV and compare to preview; inspect ZIP/kit; perform G2-G3 for Launch PBIP. Capture table/Audit trail/files.

## 27 | L5: Launch - repeat live request and REUSE
- Record rendered Launch plan ID/hash; repeat L1 with live LLM and capture last extraction: llm.
- Confirm P-NUB/JP; milestone_id, milestone_type, status; 2026-01-01; event; SAME owner OWN-001.
- Click Create plan. Expected REUSE of the same plan ID/hash and frozen result, no new pending approval.
- Compare re-downloaded CSV source rows; capture REUSE notice, IDs, and Audit trail.
- Do not silently replace January or Japan if extraction differs; record the mismatch.

## 28 | G1: Inspect all five exports for EACH dataset
- HTML: open locally and check scope, native units, source rows, provenance, ownership, and audit information.
- CSV: check selected columns and source rows against the frozen preview. Do not let Excel's date/number formatting masquerade as changed source values.
- ZIP bundle: extract and inspect packaged report/evidence files. Power Query kit: inspect CSV, PowerQuery_Report.m, theme, and included instructions; this is a manual-import kit, NOT the PBIP project.
- PBIP ZIP is a different export: use G2-G3. Keep each domain's files in its own folder; automatic browser suffixes are not reliable domain labels.
- Record five downloaded filenames per dataset. A visible download button is not proof that a usable file was downloaded.

## 29 | G2: Power BI Desktop handoff - repeat four times
- Optional dependency: Power BI Desktop with PBIP/project support. If unavailable, record Desktop checks as not tested, not passed.
- For each Commercial, Supply, Market Access, and Launch PBIP ZIP, extract the FULL archive into its own folder.
- Keep GovernedReport.Report and GovernedReport.SemanticModel beside GovernedReport.pbip. Do not move only the .pbip file.
- Open GovernedReport.pbip in Desktop. Run Refresh on first load even if not prompted: this loads the embedded frozen snapshot, not new business data.
- Record Desktop version and any warnings. Templates were previously checked with 2.159.1231.0; verify your own target version.

## 30 | G3: Validate every Power BI page per dataset
- Open Dashboard, Source Evidence, and Ownership & Evidence; capture all three pages for EACH of the four datasets after Refresh.
- Compare scope, field names, values, units, owner, and source identifiers with that domain's frozen HTML/CSV and UI preview.
- Commercial: monthly sales/forecast source values. Supply/Market Access: snapshot values and categorical statuses, no invented dated trends. Launch: event identity/type/status, not sales totals.
- Measures may return BLANK for ambiguous multi-row contexts; do not demand summed/averaged source values. Investigate an unexpected blank in an unambiguous context.
- No PBIX export, service publish, live connection, or scheduled refresh is implemented. Power Query kit requires manual import and is not this project-opening test.

## 31 | G4: Saved plans, reload, and URL resume
- Repeat for all four rendered plans: Workspace Saved plans, click Refresh, select the recorded plan ID.
- Expected: same plan ID/hash, rendered snapshot, Audit trail, and five download choices. Re-download CSV and compare source rows.
- Copy the UI URL containing ?plan_id=...; open in a new browser tab with the same requester identity.
- Expected report plan resumes in Builder pack reports with its domain and frozen result. A lifecycle plan resumes in Saved plans.
- Browser reload/new tab must not demand a fresh approval for an already-rendered plan. For persistence after restart, stop only your launcher and restart with the SAME recorded RUNTIME_DB_PATH and ports.
- Do NOT regenerate the GUID command when testing restart persistence; that would select a different empty DB.

## 32 | G5: REUSE boundaries and scope changes
- REUSE uses the normalized report specification plus source fingerprint, including owner. Same wording alone is not enough; wording/rationale are not the deduplication key.
- On each rendered domain, reorder selected fields (and Commercial months), keeping the same selection set and owner; create again. Expected same original plan via REUSE.
- Changed-scope test: from Commercial C2, keep Germany/Nubeqa/OWN-001 but select ONLY net_sales_m_eur_syn (remove forecast); create.
- In this clean run that new scope must be pending, not reuse the original two-field plan. If previously approved, it may reuse its OWN different plan; record both IDs.
- A pending plan is not eligible for approved-plan REUSE. Do not claim metadata-only source-estate candidates are equivalent executable reports.

## 33 | G6: Duplicate pending plans coalesce at approval
- Optional advanced UI test, before approving the new single-field scope from G5: create the SAME single-field scope again with the same owner, without approving either copy.
- Expected two different pending plan IDs, A and B. Record both; use Saved plans to select them.
- Approve A with DEMO-CHALLENGE-APPROVER. Then load B freshly from Saved plans and approve B.
- Expected second approval returns REUSE of A; B becomes superseded. Audit trail records the duplicate resolution; only the winning approved plan should be rendered.
- If the scope was already approved before this test, choose a new valid scope or a new isolated test DB; do not delete prior records.
- This tests duplicate handling, not a live multi-thread race. Stale-revision concurrency checks are in the automated suite.

## 34 | G7: Rejection does not produce a report
- Use a fresh valid Commercial scope not yet approved: Nubeqa/Germany, ONLY forecast_m_eur_syn, January 2026, owner OWN-001.
- Create a pending plan; select DEMO-CHALLENGE-APPROVER in its approval block, then click Reject.
- Expected rejected status, rejection in Audit trail, and no Render frozen report button or export downloads for that rejected plan.
- Saved plans must preserve the rejected state. Creating the same rejected scope again creates a new pending plan unless an equivalent approved plan exists.
- Do not reject an already-approved baseline. Terminal approved/rejected decisions cannot simply be flipped; API checks are covered by G15.

## 35 | G8: Finland scope refusal and identity reset
- After recording/saving current plan IDs, switch sidebar identity to DEMO-CHALLENGE-FI. Expected current plan/form identity state clears; stored plans are not deleted.
- In Commercial use the DE/Germany scope from C2 with active owner OWN-001 and click Create plan.
- Expected API error 403: requested markets outside your scope. Extracting text is not itself scope authorization; plan creation enforces it.
- Workspace Estate decisions as FI must also be refused (403), because estate records span all markets.
- Saved plans must not expose Germany/Japan-only plans to FI. Opening one of those saved URLs as FI must not reveal its frozen report.
- Restore DEMO-CHALLENGE-REQUESTER; use Saved plans to resume your original work. Simulated policy checks are not real login security.

## 36 | G9: Required fields and authoritative confirmation
- On a new builder form, confirm Create plan is disabled with missing product, market, source fields, or explicit owner.
- For Commercial/Launch, missing required months also disables creation. Supply/Market Access have no period selector.
- Select a complete scope; owner must still be chosen explicitly. Capture disabled and enabled states.
- Intake warnings are visible, but they do not automatically prevent a user from explicitly choosing a different valid scope in the form.
- Do not report a manually corrected form as an accurate unedited LLM extraction. Preserve before/after evidence.

## 37 | G10: Unsupported or incomplete intake
- In Commercial with LLM enabled, try: Show Nubeqa in Germany. Expect missing required scope to be surfaced; record any guessed fields as an extraction issue. Do not approve silently guessed scope.
- In Supply try: Show monthly Nubeqa supply risk in Germany for January through March 2026. Inspect unsupported-period/grain warnings; snapshot source must not become monthly data.
- In Commercial try: Show Nubeqa profit in Germany in January 2026. Profit is not a supported source field; record if extraction silently substitutes sales.
- In Launch try: Show Nubeqa milestones in Japan in December 2025. Out-of-coverage periods must not silently become January 2026.
- LLM wording varies; capture actual mode, warnings/questions, and proposed/confirmed form. Deterministic API invalid-scope checks are separately covered in G15.

## 38 | G11: Offline path versus provider-outage fallback
- Offline control: uncheck LLM, run the C1 text through Extract intent; expected last extraction: offline. The separate Prefill commercial example fills a known form but is not an inference test.
- Live-provider outage: if an outage occurs, capture last extraction: offline_fallback_after_llm_unavailable and the visible offline-fallback warning; record live tests as blocked.
- Do not intentionally invalidate the shared token or disrupt another tester's network/process. For a deterministic simulated outage use the mocked fallback test in G15.
- Continuing with an explicitly confirmed offline form can test report governance, but does not complete any of the four live-LLM extraction checks.
- Restore the live checkbox for the next LLM test; checking it without a NEW extraction does not change the mode of a previous result.

## 39 | G12: Estate migration proposal, never execution
- As DEMO-CHALLENGE-REQUESTER open Estate decisions. Filter assets by AST-0002; inspect Asset, Model/owner, KPIs, usage, lineage/downstream, quality/migration signals, and governance rules.
- Choose action migrate, active owner OWN-001, and a nonempty Rationale such as Team estate migration proposal test.
- Click Create lifecycle proposal. Expected pending; in its decision block test steward refusal, then choose DEMO-CHALLENGE-APPROVER and Approve.
- Expected Approved proposal; not executed. There is no report render or execution for a lifecycle plan; named release sign-offs remain proposed requirements.
- Reopen in Saved plans and inspect specification/Audit trail. The source estate is unchanged. Capture proposal evidence and non-execution message.

## 40 | G13: Other estate actions and refusal paths
- Supported action choices: reuse, repair, consolidate, retire, migrate. These are ALL proposals only; estate action reuse is not report-plan REUSE.
- For repair/reuse, choose an asset, active owner, and nonempty rationale; inspect the resulting proposal and approval. Do not claim a source report was executed.
- For consolidate, inspect Consolidation candidates; explicitly choose a candidate target. Shared product/market/KPI metadata is NOT verified executable equivalence.
- When no consolidation candidates exist, the UI warns; do not invent a target. Invalid targets must be refused by the API.
- Migrate is restricted to supported source platform; retirement may be refused for downstream dependencies. Use G15 for exact deterministic rejection tests instead of guessing safe asset IDs.
- Record the selected asset/action and actual outcome; no retire/migrate action modifies the workbook.

## 41 | G14: Source requests, ownership, provenance
- Builder page: expand Source business requests (original rows), choose a Sample request, click Load request text.
- Expected original text loads into Describe the report. Context labels may contradict text and are not auto-truth; inspect them rather than silently trusting them.
- This is a separate exploratory intake test; do not replace the four exact baseline requests when collecting C1/S1/M1/L1 evidence.
- Inspect Source estate records in this product/market scope (metadata only), where available, and the plan Specification.
- Workspace Ownership & deployment explains simulated roles, proposed responsibility, and production gaps. Accountable owner is not enforced certification.
- Preserve native units, value_type, source-row references, and fingerprint. Exported local files have no access control after download.

## 42 | G15: Automated API-only guardrail appendix
- These offline tests cover cases not fully exposed as clickable UI controls. They do NOT prove live provider availability and must be recorded separately from manual/live results.
```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_challenge.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_pbip_dashboard.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_launcher_config.py"
```
- Challenge suite covers unknown IDs, wrong grain/months/owner, cross-domain fields, scope refusal, pending/rejected render refusal, stale hash/revision, source drift, duplicate approval coalescing, frozen resume, export packaging, and mocked LLM fallback.
- Never edit workbook/evidence to demonstrate source drift manually; tests isolate such scenarios. Legacy live_aitta scripts target different domains and are not this four-dataset acceptance flow.

## 43 | G16: Troubleshooting without losing test evidence
- Busy ports: reuse the correct instance or choose a new API/UI pair. Changing ports alone does NOT create a fresh DB.
- Module errors: use the SAME venv Python for pip and launcher. Wrong UI: launch --mode challenge, not public/legacy.
- API unreachable: inspect launching terminal and artifacts/logs/api-8025.log / ui-8525.log (adjust port suffixes).
- LLM unavailable: verify approved credentials/provider/model privately, capture warning and mark live tests blocked; never publish token contents.
- Unexpected REUSE: compare original scope, owner, hash, and source fingerprint; fresh pending approval needs an unused scope/new isolated DB, not database deletion.
- Lost current UI plan after identity change: restore requester and reopen Saved plans; do not recreate blindly.

## 44 | G17: Team completion record and shutdown
- For EACH dataset record: live extraction caption; unedited scope accuracy and corrections; confirmed owner/scope; pending or existing-REUSE branch; steward refusal; approval; rendered result; five downloaded files; repeat-request REUSE; saved-plan resume; optional Desktop results.
- Use result labels NOT RUN, PASS, FAIL, BLOCKED, or NOT APPLICABLE with an explanation. Never prefill success. Existing-state REUSE does not pass a fresh-approval test that was skipped.
- Record shared G1-G16 results and evidence links separately. If Desktop/provider is unavailable, say so; do not relabel it a complete live end-to-end pass.
- Existing tests provide the cited synthetic spot-check values; your team must still compare current frozen output to source provenance. These instructions are not today's execution report.
- Stop your foreground demo with Ctrl+C in its launching terminal. Keep the recorded DB and downloads for handoff; do not delete someone else's processes or files.
- To return a dedicated test PowerShell to default DB selection later, remove only its process variable: Remove-Item Env:RUNTIME_DB_PATH. This does not delete a DB file; .env configuration still applies.
