# Demo guide index — Smart Librarian (challenge mode)

A **team testing package** driving all four challenge datasets
(Commercial, Supply, Market Access, Launch) through live Snowflake Cortex
extraction, explicit confirmation, simulated approval, frozen reports,
exports, and REUSE. Local, synthetic data only — never real Bayer data,
never exposed remotely.

| Resource | What it is |
| --- | --- |
| [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) | **Easy guide — the deck's source.** 44 numbered steps; each says what to **Do**, what you should **See**, what it **Proves**, and what to **Remember**. |
| [DEMO_SLIDES.html](DEMO_SLIDES.html) | Slide deck rendering the same 44 steps (45 slides with cover) — open in any browser, fully self-contained; arrows/Space navigate, Contents jumps by chapter, Print gives one landscape page per step. |
| [DEMO_SLIDES.pptx](DEMO_SLIDES.pptx) | Editable PowerPoint version. |
| [DEMO_SLIDES.pdf](DEMO_SLIDES.pdf) | Printable PDF of the deck. |
| [TEAM_DEMO_TEST_RUNBOOK.md](TEAM_DEMO_TEST_RUNBOOK.md) | Detailed reference: 44 numbered sections covering the same 37 test cases — exact requests, scopes, expected results, and edge cases. |
| [TEAM_DEMO_RESULTS_TEMPLATE.csv](TEAM_DEMO_RESULTS_TEMPLATE.csv) | Blank results sheet: C1–C5, S1–S5, M1–M5, L1–L5, G1–G17 (37 rows) — record actual results here, never pre-fill. |

## Where to start

1. **Snowflake credentials first:** follow the README's
   [Snowflake setup for testers](../README.md#snowflake-setup-for-testers)
   — enter the provider env vars and your PAT in a private PowerShell
   *before* launching (`--api-port 8025 --ui-port 8525`, UI at
   <http://127.0.0.1:8525>). Cloning gives no credential.
2. **Walk the easy guide:** sections 01–07 (setup + reading the UI),
   then C1–C5, S1–S5, M1–M5, L1–L5 per dataset, then shared checks
   G1–G17.
3. **Record results** in the CSV template; keep evidence per dataset.

To regenerate the deck after editing `DEMO_WALKTHROUGH.md`:
`python docs/build_demo_slides.py` rewrites the **HTML and PPTX**
(requires python-pptx). The PDF is produced separately — open
`DEMO_SLIDES.html` in a browser and Print → Save as PDF.
