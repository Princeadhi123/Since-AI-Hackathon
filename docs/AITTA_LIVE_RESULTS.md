# Aitta live-verification results

Authenticated end-to-end verification against **CSC / LUMI Aitta**
(provider `aitta`, model `meta-llama/Llama-3.3-70B-Instruct`) was completed
on 2026-11-07. Live checks contacted the real provider with
LLM extraction opted in; the offline parser was never counted as a live pass.
All prompts use synthetic demo fixtures only - no business data left the
machine, and identities/approvals remain simulated.

## Summary

| Check | Result | Live? |
|---|---|---|
| `tests/live_llm_check.py` smoke (4 hand-authored cases) | **4/4 pass** | yes |
| `tests/live_aitta_e2e.py` (8 workflow paths) | **8 paths verified** (6 original passes + 2 corrected frozen-intake replays) | live intake; two downstream replays |
| `tests/live_aitta_ui.py` (3 domains through Streamlit + running API) | **3/3 pass** | yes |
| `python -m unittest discover -s tests` baseline | 111 tests, OK | offline |
| `tests.test_llm_adapter` + `tests.test_llm_providers` (patch focus) | 26 tests, OK | offline |
| `tests/ui_smoke.py` / `tests/ui_resume_smoke.py` | 33 + 17 checks, no failures | offline regression checks |

### Live smoke (4/4)

Sales, logistics and quality paraphrase cases all produced the exact
expected intent (products, markets, metrics, months, grain); the ambiguous
"Show sales performance" request correctly produced an empty intent with
clarification. Evidence: `artifacts/live_aitta/smoke_stdout_patched.txt`.

### Live workflow E2E (8/8)

Six paths passed on the original live run - extend, build, clarify
(ambiguous -> follow-up -> REUSE), access-denied, plus logistics and
quality builds - with real `extraction_mode: "llm"`, approval gating,
negative authorization/hash checks, ZIP/CSV/HTML/spec exports, numeric
expectations, new-app persistence and stale-approval rejection.
Evidence: `artifacts/live_aitta/e2e-2deaf3e6048b/`.

Two paths initially failed due to **test-assumption mismatches, not
product or model defects**: opening a library asset intentionally confirms
its full catalog coverage (the originally scoped render stays Q1), and an
unsupported metric correctly yields CLARIFY/unsupported rather than an
extracted id. After the assertions were corrected to match intended
behaviour, both paths were re-verified by replaying the **frozen live
intake** (no redundant model derivation) and pass:
`artifacts/live_aitta/e2e-2de394779b08/`, logs
`artifacts/live_aitta/e2e_replay_stdout.txt`.

### Live UI through real provider (3/3)

Streamlit `AppTest` driving the real UI against the running API on
`http://127.0.0.1:8001` (app served on `http://127.0.0.1:8502`): sales,
logistics and quality requests each used `extraction_mode: "llm"`,
reached a confirmable intent, were confirmed, approved where required,
rendered a three-row preview and exposed all four download controls
(spec JSON, CSV, standalone HTML, ZIP bundle). Results:
`artifacts/live_aitta/live_ui_results.json`,
logs `artifacts/live_aitta/ui_live_stdout.txt`.

## What needed fixing

Two provider realities surfaced on first contact:

1. **Cold-start timeout** - the very first inference call exceeded the
   150 s client timeout once (`APITimeoutError`); subsequent calls
   answered in seconds. This matches the documented model warm-up
   behaviour.
2. **Markdown-fenced output** - Aitta returns the intent object wrapped in
   a ```` ```json ```` code fence, which the adapter previously fed straight
   to `json.loads`, producing `provider request failed (JSONDecodeError)`.
   The adapter now accepts **only** an entire fenced document
   (`re.fullmatch`, optional `json` tag, CRLF/whitespace tolerant) and
   parses its body; prose around fences, multiple blocks and truncated or
   malformed fences still fail. Strict Pydantic validation is unchanged
   and no arbitrary `{...}` is extracted from surrounding text. Covered by
   the new focused tests in `tests/test_llm_adapter.py`.

## How to try it

1. Configure `.env` per `docs/AITTA_SETUP.md`.
2. Start the demo: `PYTHONPATH=src python run_demo.py --api-port 8001 --ui-port 8502`
   then open `http://127.0.0.1:8502`.
3. Tick the sidebar checkbox **"Use LLM intent extraction (opt-in)"** -
   provider calls only happen while it is enabled; failures fall back to
   the offline parser safely. `GET /api/capabilities` reports
   `"configured": true` when the token is loaded.

## Caveats

- All data is synthetic demo fixture data; identities, roles and approvals
  are **simulated** - demonstration only, not real Bayer data, real
  authentication or real access control.
- Aitta is an R&D endpoint tied to the event project: tokens may expire
  with the project, there is no availability SLA, and model output can
  vary between runs.
