# Smart Librarian — Live Demo

Every slide answers: what do I do, what should I see, and what does it prove?
Start with Setup, then Commercial, Supply, Market Access, Launch, and the extra checks.
This is a guide to tests you will perform, not a claim that every test passed today.

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

## 08 | C1: Ask the Commercial question
- Do: Choose Source domain Commercial. Tick Send request text + catalog metadata to the LLM. Paste this into Describe the report, then click Extract intent.
```text
Show monthly Nubeqa net sales and sales forecast in Germany for January through March 2026.
```
- See: last extraction: llm and a filled Guided confirmation form.
- Proves: The real LLM proposed an interpretation of this sales request.
- Remember: Record the form before edits. A fallback is not a live pass; do not click Prefill commercial example.

## 09 | C2: Check exactly what you asked for
- Do: Compare the form with the scope below. Record mistakes before correcting them. Explicitly choose active owner OWN-001.
```text
Product: P-NUB (Nubeqa)
Market: DE (Germany)
Fields: net_sales_m_eur_syn, forecast_m_eur_syn
Months: 2026-01-01, 2026-02-01, 2026-03-01
Grain: month
```
- See: The complete form enables Create plan (requires approval).
- Proves: You, not the LLM, decide the final scope and accountable owner.
- Remember: The source fields are synthetic million-EUR sales/forecast fields. Choosing an owner is required, not proof of production certification.

## 10 | C3: Create, refuse the steward, then approve
- Do: Click Create plan (requires approval). For a pending plan, use Approval (separate actor): try DEMO-CHALLENGE-STEWARD + Approve, then DEMO-CHALLENGE-APPROVER + Approve.
- See: pending -> steward error 403, still pending -> approved. Save the plan ID and Audit trail.
- Proves: The simulated steward cannot approve; a separate approver can authorize the confirmed plan.
- Remember: Never change the sidebar requester during approval. If REUSE appears, follow C5; mark these fresh-only checks not exercised.

## 11 | C4: Turn the approved plan into a report
- Do: Click Render frozen report. Inspect the chart/table, then download all five formats: HTML, CSV, ZIP bundle, Power Query kit (CSV+M), Power BI project (PBIP ZIP).
- See: rendered; three monthly source rows for Nubeqa/Germany. January spot-check: net sales 19.66 and forecast 18.42, in synthetic million EUR.
- Proves: The renderer uses frozen source rows for the approved scope; the LLM did not invent these figures.
- Remember: These are synthetic, forecast-like values, not real Bayer results. Save Commercial files in their own folder and compare CSV to the preview.

## 12 | C5: Ask again and prove REUSE
- Do: Record the rendered plan ID. Repeat C1 with live LLM; confirm EXACTLY the same C2 scope and owner OWN-001; click Create plan again.
- See: REUSE, the same original plan ID and spec hash, and the original frozen result. No new approval is needed.
- Proves: An already-approved identical specification can be reused instead of producing another report.
- Remember: Compare CSV source rows, not ZIP bytes. Same wording alone is insufficient: scope, owner, and source fingerprint must match.

## 13 | S1: Ask the Supply question
- Do: Choose Source domain Supply. Keep the global requester, tick the LLM checkbox, paste this request, and click Extract intent.
```text
Show a current snapshot of Nubeqa in Germany: on-time in-full, inventory in weeks, and supply risk status.
```
- See: last extraction: llm and a snapshot proposal.
- Proves: The LLM interpreted a current supply question rather than a sales trend.
- Remember: Save the unedited result. There should be no invented monthly history.

## 14 | S2: Check the Supply snapshot
- Do: Confirm this form, then explicitly select owner OWN-001.
```text
Product: P-NUB (Nubeqa)
Market: DE (Germany)
Fields: otif_pct_syn, inventory_weeks_syn, risk_status
Months: none
Grain: snapshot
```
- See: Snapshot source: no period selection applies. Create plan becomes available with a complete scope and owner.
- Proves: A snapshot stays a snapshot; you confirm the measures and categorical risk field.
- Remember: Record extraction errors before changing the form. Empty months are correct here, not missing input.

## 15 | S3: Approve Supply with a separate actor
- Do: Create the plan. On pending: try DEMO-CHALLENGE-STEWARD + Approve, then DEMO-CHALLENGE-APPROVER + Approve inside Approval (separate actor).
- See: pending -> error 403 with status unchanged -> approved.
- Proves: The same simulated approval gate applies to Supply, not just Commercial.
- Remember: Keep the sidebar identity unchanged. If this is REUSE, go to S5; the skipped pending/refusal checks are not passes.

## 16 | S4: Inspect the frozen Supply result
- Do: Click Render frozen report. Inspect numeric bars and the risk-status table. Download all five formats into a Supply folder.
- See: rendered. For Nubeqa/Germany, source spot-checks include OTIF 87.9% and inventory 8.8 weeks; risk_status remains a category.
- Proves: Different units and categorical values are preserved in a source-backed snapshot.
- Remember: No monthly trend or summed percentage should appear. Compare downloaded CSV/HTML with this preview; Power BI steps are in G2-G3.

## 17 | S5: Reuse the Supply plan
- Do: Save the rendered Supply plan ID. Repeat S1 with live LLM; confirm the SAME S2 fields, empty months, snapshot grain, and owner OWN-001; create again.
- See: REUSE returns the original plan ID/hash and frozen snapshot, without another approval.
- Proves: Snapshot reports can reuse an identical approved scope too.
- Remember: Capture last extraction: llm again and compare the re-downloaded CSV. A changed owner or dated period is a different test.

## 18 | M1: Ask the Market Access question
- Do: Choose Source domain Market Access. With the LLM checkbox ticked, paste this request and click Extract intent.
```text
Show the current market access snapshot for Nubeqa in Germany: coverage percentage and reimbursement status.
```
- See: last extraction: llm and a current-snapshot form.
- Proves: The model can propose scope for access coverage and a reimbursement category.
- Remember: This request does not ask for a month-by-month trend. Save the proposal before editing.

## 19 | M2: Check the Market Access scope
- Do: Compare the form with this scope; explicitly choose owner OWN-001.
```text
Product: P-NUB (Nubeqa)
Market: DE (Germany)
Fields: coverage_pct_syn, reimbursement_status
Months: none
Grain: snapshot
```
- See: No period selector applies; a complete form enables Create plan.
- Proves: A numeric percentage and a category can be confirmed together without inventing dates.
- Remember: Log mismatches first. A manually corrected form is not proof that the LLM got the original extraction right.

## 20 | M3: Pass the Market Access approval gate
- Do: Create the plan. If pending, try the steward's Approve action, then choose DEMO-CHALLENGE-APPROVER and Approve in the same decision block.
- See: pending -> steward error 403 -> approved with the authorized simulated actor.
- Proves: Market Access is subject to the same explicit owner and approval controls.
- Remember: Do not switch the sidebar requester. REUSE follows M5, and does not exercise fresh approval.

## 21 | M4: Render coverage and reimbursement
- Do: Render frozen report. Check the coverage chart and reimbursement table. Download all five formats into a Market Access folder.
- See: rendered. Source spot-check for Nubeqa/Germany: coverage_pct_syn 65.6%; reimbursement_status remains a category.
- Proves: The frozen report preserves the selected source percentage and status, without inventing history.
- Remember: Do not average percentages or turn reimbursement labels into numbers. Compare preview, CSV, and HTML.

## 22 | M5: Reuse Market Access
- Do: Save the rendered plan ID. Repeat M1 with live LLM; confirm the SAME M2 scope and owner OWN-001; create the plan again.
- See: REUSE returns the original plan ID/hash and frozen result. No new pending approval is required.
- Proves: Identical access-report specifications reuse the approved snapshot.
- Remember: Save the new llm caption and compare CSV rows. Empty months are part of this exact snapshot scope.

## 23 | L1: Ask the Launch question
- Do: Choose Source domain Launch. Tick the LLM checkbox, paste this request, and click Extract intent.
```text
Show Nubeqa launch milestones in Japan in January 2026, including milestone ID, milestone type, and status.
```
- See: last extraction: llm and an event-based proposal for Japan.
- Proves: The LLM can interpret the launch-event request, not only numeric reports.
- Remember: Japan is JP, not Germany DE. Keep the unedited proposal as evidence.

## 24 | L2: Check Japan, January, and event fields
- Do: Confirm this scope and explicitly choose owner OWN-001.
```text
Product: P-NUB (Nubeqa)
Market: JP (Japan)
Fields: milestone_id, milestone_type, status
Month: 2026-01-01
Grain: event
```
- See: The complete event scope enables Create plan.
- Proves: The confirmed report asks for milestone identity/type/status, not sales or supply measures.
- Remember: Log any extracted mismatch before correcting it. The selected month is required for Launch.

## 25 | L3: Approve the Launch plan
- Do: Create the plan. For pending, try DEMO-CHALLENGE-STEWARD + Approve, then DEMO-CHALLENGE-APPROVER + Approve in the approval block.
- See: pending -> error 403, still pending -> approved.
- Proves: Event reports need the same separate simulated approval as the other domains.
- Remember: Keep the requester in the sidebar. An existing REUSE result goes to L5; it is not a fresh approval pass.

## 26 | L4: Read the frozen Launch events
- Do: Render frozen report. Inspect the event table and download all five formats into a Launch folder.
- See: rendered; source event LM-0001 for Nubeqa/Japan has milestone_date 2026-01-05T00:00:00, with its source type and status.
- Proves: The renderer preserves event rows and identifiers rather than inventing numeric totals.
- Remember: A numeric chart is not required for these categorical fields. Compare preview/CSV/HTML; optional Power BI checks are G2-G3.

## 27 | L5: Reuse the Launch plan
- Do: Save the rendered plan ID. Repeat L1 with live LLM; confirm the SAME L2 scope and owner OWN-001; create again.
- See: REUSE returns the original plan ID/hash and frozen event result, without new approval.
- Proves: The same reuse rule works for event reports as well as monthly and snapshot reports.
- Remember: Capture last extraction: llm again. Japan, January, selected fields, owner, and source fingerprint must all match.

## 28 | G1: Open the files, not just the download buttons
- Do: For EACH dataset, save and open HTML, CSV, ZIP bundle, Power Query kit (CSV+M), and Power BI project (PBIP ZIP). Keep four separate dataset folders.
- See: HTML/CSV match the frozen preview. ZIPs contain their report/evidence or import/project files; filenames alone are not enough.
- Proves: Usable files were actually exported from the frozen report.
- Remember: The Power Query kit is for manual import; the PBIP ZIP is a complete project. Neither is a live connection to Snowflake business data.

## 29 | G2: Open a Power BI project correctly
- Do: If Power BI Desktop is available, extract the FULL PBIP ZIP. Keep the .Report and .SemanticModel folders beside GovernedReport.pbip. Open that file and click Refresh.
- See: Desktop loads the embedded frozen snapshot. Repeat for all four datasets and record your Desktop version or errors.
- Proves: This exported project can open and load its packaged data in the tested Desktop version.
- Remember: No Desktop? Mark this check NOT RUN. Refresh is required on first load; it does not fetch new source business data.

## 30 | G3: Check all three Power BI pages
- Do: In each project, open Dashboard, Source Evidence, and Ownership & Evidence. Compare scope, values, units, owner, and source IDs with the app's HTML/CSV.
- See: Monthly values for Commercial, snapshots for Supply/Market Access, events for Launch. All three pages retain source/evidence context.
- Proves: The project carries report content and governance evidence, not just a chart.
- Remember: Ambiguous contexts may produce BLANK, not sums/averages. This does not prove PBIX export, service publishing, or scheduled refresh; those are not implemented.

## 31 | G4: Leave the page and resume your work
- Do: Record a rendered plan ID. Open Saved plans -> Refresh -> select that ID. Reopen its ?plan_id= URL in another tab with the same requester.
- See: The same plan ID/hash and frozen result return, with downloads and Audit trail. Repeat for all four report plans.
- Proves: The local plan store preserves approved work beyond the current browser screen.
- Remember: To test restart persistence, reuse the SAME recorded RUNTIME_DB_PATH. A newly generated GUID selects a different database; it does not recover old plans.

## 32 | G5: Change scope and see why wording is not enough
- Do: First reorder fields without changing the selection or owner and create again. Then try Commercial with ONLY net_sales_m_eur_syn, keeping Nubeqa/Germany/Jan-Mar/OWN-001.
- See: Reordering the same selection reuses the original. The one-field request must not reuse the original two-field plan; it is pending or reuses its own previously approved plan.
- Proves: REUSE matches the normalized specification, owner, and source fingerprint, not just the sentence.
- Remember: Record both IDs. A candidate estate record is not proof that two executable dashboards are equivalent.

## 33 | G6: Optional advanced test - duplicate pending plans
- Do: Before approving G5's new one-field scope, create it twice with the same owner. Record pending IDs A and B. Approve A; reload B from Saved plans and approve it.
- See: The second approval returns REUSE of A; B is superseded. Inspect Audit trail and render the winning plan.
- Proves: Duplicate pending requests can resolve to one approved plan at approval time.
- Remember: This needs an unapproved scope or a fresh DB. If already approved, REUSE happens sooner. This is not a live multi-thread race test.

## 34 | G7: Reject a plan and check what is missing
- Do: Use a NEW Commercial scope: Nubeqa/Germany, ONLY forecast_m_eur_syn, January 2026, owner OWN-001. Create pending; choose DEMO-CHALLENGE-APPROVER and click Reject.
- See: rejected; Audit trail records rejection. That plan has no Render frozen report action or report downloads.
- Proves: A rejected plan cannot be used to produce an approved report.
- Remember: Do not reject an approved baseline. If this scope already reuses an approved plan, use a fresh DB for the rejection test.

## 35 | G8: Show that market scope is enforced
- Do: Save your plan IDs. Switch the sidebar to DEMO-CHALLENGE-FI. Try creating the Commercial Germany scope, opening Estate decisions, and opening a Germany-only saved plan.
- See: Out-of-scope actions are refused, not exposed as allowed work. Plan creation and estate access return error 403. Switching identity clears current form/plan state.
- Proves: The demo checks simulated market scope at governed operations; extracting text is not authorization.
- Remember: Stored plans are not deleted. Restore DEMO-CHALLENGE-REQUESTER and resume via Saved plans. These identities are not real login security.

## 36 | G9: Show that missing choices cannot be skipped
- Do: Start an incomplete form. Leave product, market, fields, or owner missing; also omit months for Commercial/Launch. Then complete all required choices.
- See: Create plan is disabled until the required scope and explicit active owner are selected. Supply/Market Access correctly have no month selection.
- Proves: The form requires human confirmation instead of quietly inventing missing required inputs.
- Remember: Record the LLM's original mistakes separately. A manually repaired form proves the correction path, not extraction accuracy.

## 37 | G10: Ask something the source cannot answer
- Do: Try Commercial: Show Nubeqa profit in Germany in January 2026. Also try monthly Supply risk, a December 2025 Launch request, and the incomplete request Show Nubeqa in Germany.
- See: Inspect actual unresolved/unsupported warnings and the proposed form. Record guessed fields or silent substitutions as extraction defects; do not count them as a pass.
- Proves: This checks whether uncertainty and unsupported scope are surfaced, rather than hidden by an attractive answer.
- Remember: Model wording can vary. Do not approve an invented scope. Exact deterministic invalid-scope refusals are covered separately in G15.

## 38 | G11: Demonstrate offline honestly
- Do: Untick the LLM checkbox and extract the Commercial request. Separately, if a real provider failure occurs, capture its fallback warning.
- See: Unticked: last extraction is offline. Provider failure: offline_fallback_after_llm_unavailable. An explicitly confirmed form can still continue through governance.
- Proves: Offline parsing and the rest of the report workflow remain available without pretending to be successful LLM inference.
- Remember: Mark live extraction BLOCKED during provider failure. Do not break a shared token/network to stage an outage; use G15's mocked test.

## 39 | G12: Propose a migration without executing it
- Do: Restore the global requester. Open Estate decisions, search AST-0002, choose migrate and owner OWN-001, enter a rationale, then Create lifecycle proposal. Approve with the separate approver.
- See: A pending proposal becomes Approved proposal; not executed. Saved plans retains its specification and Audit trail.
- Proves: The estate workflow records an accountable decision proposal with approval evidence.
- Remember: It does not migrate any Power BI/Tableau file. The source estate contains synthetic inventory metadata, not 360 openable dashboard files.

## 40 | G13: Understand the other estate actions
- Do: Explore reuse, repair, consolidate, retire, and migrate. For consolidate, choose only a listed candidate target; review signals and dependencies before submitting.
- See: The UI offers supported proposals, warns when candidates are absent, and may refuse unsupported platforms or protected dependencies.
- Proves: Different lifecycle decisions are modeled with explicit evidence and guardrails.
- Remember: ALL are proposals, not execution. Estate action reuse is not report-plan REUSE. Shared metadata does not prove two dashboards can replace each other.

## 41 | G14: Inspect where the request and evidence came from
- Do: In Builder pack reports, expand Source business requests (original rows), select a sample, and Load request text. Explore source estate records and Ownership & deployment.
- See: Original request text and possibly conflicting context labels; source IDs, native units, simulated roles, and production gaps remain visible.
- Proves: You can inspect provenance instead of treating context labels or AI output as unquestionable truth.
- Remember: Keep the four exact baseline requests for acceptance tests. A named owner is not certification; downloaded files have no access control.

## 42 | G15: Run the offline API guardrail checks
- Do: In a second PowerShell at the project root, run these focused tests. They isolate invalid IDs, stale revisions, approval/render refusal, source drift, and export packaging.
```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_challenge.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_pbip_dashboard.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_launcher_config.py"
```
- See: Each suite reports OK, or concrete failing test names to investigate.
- Proves: The tested deterministic rules behave as asserted; mocked fallback tests exercise an outage without breaking credentials.
- Remember: These tests do not prove live Snowflake access or real production security. Never edit the workbook/evidence to stage source drift.

## 43 | G16: If something goes wrong, find the right cause
- Do: Check the printed UI/API ports and /api/capabilities first. If Snowflake is selected, check the visible error and private PAT/IP setup; use README troubleshooting.
- See: Wrong old UI: open the verified Snowflake URL. Busy port: choose a free pair. Provider failure: BLOCKED. Unexpected REUSE: inspect scope/owner/DB, do not delete plans.
- Proves: You can distinguish a launch/configuration issue, provider failure, and valid existing-state behavior.
- Remember: Restart only your own launcher after configuration/code changes. Use port-matched logs under artifacts/logs/. Never publish token values or kill unknown processes.

## 44 | G17: Finish with evidence, not just a happy screen
- Do: Complete the team results CSV for C1-C5, S1-S5, M1-M5, L1-L5, and G1-G17. Save screenshots, original/reused plan IDs, Audit trail, and five files per dataset.
- See: Each case has PASS, FAIL, BLOCKED, NOT RUN, or NOT APPLICABLE with an explanation. Fresh approval and existing REUSE have separate evidence.
- Proves: Another teammate can follow what you did, inspect the outputs, and understand exactly which claims are supported.
- Remember: Four Snowflake extractions passed our finite live check; that is not today's full-workflow result. Stop with Ctrl+C; preserve the recorded DB and downloaded evidence.
