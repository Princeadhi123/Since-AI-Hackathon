# Demo guide index — Smart Librarian (challenge mode)

This is a **team testing package**, not a 5-minute intro. It drives all
four challenge datasets (Commercial, Supply, Market Access, Launch)
through live-LLM extraction, explicit confirmation, simulated approval,
frozen reports, exports, and REUSE. Everything is a local, synthetic-data
demo — never real Bayer data, never exposed remotely.

| Resource | What it is |
| --- | --- |
| [TEAM_DEMO_TEST_RUNBOOK.md](TEAM_DEMO_TEST_RUNBOOK.md) | **Source of truth.** 44 numbered test sections with exact requests, scopes, expected results, and evidence to capture. |
| [DEMO_SLIDES.html](DEMO_SLIDES.html) | Slide deck rendering the same 44 sections — open in any browser, works fully offline; arrow keys/Space navigate, Contents jumps by chapter, Print gives one landscape page per section. |
| [DEMO_SLIDES.pptx](DEMO_SLIDES.pptx) | Editable PowerPoint version of the deck. |
| [DEMO_SLIDES.pdf](DEMO_SLIDES.pdf) | Printable PDF of the deck. |
| [TEAM_DEMO_RESULTS_TEMPLATE.csv](TEAM_DEMO_RESULTS_TEMPLATE.csv) | Blank results sheet: one row per case (C1–C5, S1–S5, M1–M5, L1–L5, G1–G17) — record actual results here, never pre-fill passes. |

## Where to start

1. **Setup path:** follow runbook sections 01–07 (PowerShell venv +
   install, isolated test DB via `RUNTIME_DB_PATH`, live-LLM
   configuration, what counts as live-extraction evidence).
2. **Run the datasets:** sections 08–27 — five explicit steps each
   (exact live request, scope confirmation, steward refusal + approval,
   render + five exports, repeat request + REUSE).
3. **Shared checks:** sections 28–44 (export inspection, Power BI
   handoff, saved plans, REUSE boundaries, refusal/rejection paths,
   offline vs fallback, estate proposals, troubleshooting, completion
   record).
4. **Record results** in the CSV template; keep evidence files per
   dataset.

To regenerate the deck after runbook edits:
`python docs/build_demo_slides.py` rewrites the **HTML and PPTX** only
(requires python-pptx). The PDF is produced separately: open
`DEMO_SLIDES.html` in a browser and use Print → Save as PDF
(landscape, one page per section).
