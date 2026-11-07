# Persistent commands (PowerShell)

Run the full test suite:

    $env:PYTHONPATH = 'src'
    python -m unittest discover -s tests -p "test_*.py"

Narrow suites:

    python -m unittest discover -s tests -p "test_exports.py"
    python -m unittest discover -s tests -p "test_powerbi.py"
    python -m unittest discover -s tests -p "test_evidence_api.py"
    python -m unittest discover -s tests -p "test_ui_workspaces.py"

UI smoke scripts need a RUNNING API (default http://127.0.0.1:8000).
The modern real-data-only smoke targets the default create_app API
(here assumed on port 8011):

    $env:SMART_LIBRARIAN_API_URL = 'http://127.0.0.1:8011'
    python tests\ui_real_demo_smoke.py

The two legacy smokes below require a LEGACY API
(create_app(include_synthetic=True)) - they fail on a real-only API:

    $env:SMART_LIBRARIAN_API_URL = 'http://127.0.0.1:8002'
    python tests\ui_smoke.py
    python tests\ui_resume_smoke.py

Launch the demo (refuses if a port is already in use; never kill unknown
processes). `--mode` selects the app factory; default is challenge:

    python run_demo.py --mode challenge --api-port 8021 --ui-port 8521
    python run_demo.py --mode public --api-port 8002 --ui-port 8503
    python run_demo.py --mode legacy --api-port 8002 --ui-port 8503

Challenge mode serves `create_challenge_app()` (include_synthetic=True,
challenge_mode=True) which mounts the additional /api/challenge/*
router: catalog, source requests, fixed simulated actors, estate
search/detail, offline/opt-in-LLM extraction, governed plans with
approval + frozen renders, and HTML/CSV/ZIP/Power Query kit/PBIP exports.
Source workbook: data\Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx
(read-only, fingerprint-pinned; the runtime DB must never resolve inside
data/ in challenge mode).

Challenge tests:

    python -m unittest discover -s tests -p "test_challenge.py"

Or manually:

    $env:PYTHONPATH = 'src'
    python -m uvicorn smart_librarian.api.app:app --host 127.0.0.1 --port 8002
    $env:SMART_LIBRARIAN_API_URL = 'http://127.0.0.1:8002'
    python -m streamlit run apps\streamlit_app.py --server.address 127.0.0.1 --server.port 8503 --server.headless true

Evidence files (read-only, served via GET /api/evidence/{challenge|public}):
data\evidence\challenge_estate.json, data\evidence\public_financials.json.
Do not regenerate or edit them; the preparing pipeline refuses overwrite.
