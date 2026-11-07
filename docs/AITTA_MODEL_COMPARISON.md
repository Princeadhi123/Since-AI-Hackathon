# Aitta model comparison (fixed harness)

Head-to-head comparison of the four Aitta models listed as Online, run with
the lead-authored frozen harness `tests/compare_aitta_models.py`. One request
per case per model - **52 provider calls total** - using the identical
production system prompt, response schema, `max_tokens=2048` and the 150 s
client timeout. The four model workers ran **concurrently as independent
processes** (each internally serial). This is a small single-sample,
task-specific comparison - **not a general model benchmark** - and Aitta is
a shared R&D endpoint with no availability SLA; cold starts and service load
affect timings (the first request is included).

The 13 fixed cases cover: exact sales/logistics/quality extractions,
multi-turn clarification, market and scope corrections, unsupported metric
and grain handling, unknown product, missing-year handling and prompt
injection - all synthetic fixtures only.

## Results (authoritative, frozen)

| Model | Cases passed | Median request latency | Notes |
|---|---|---|---|
| **openai/gpt-oss-120b** | **13/13** | **6.092 s** | clean pass; see adjudication below |
| google/gemma-4-31b-it | 13/13 | 23.004 s | accurate but ~4x slower |
| meta-llama/Llama-3.3-70B-Instruct | 12/13 | 4.362 s | invented year 2026 when unspecified |
| Qwen/Qwen3.8-27B | 11/13 | 22.649 s | 2 empty-content responses, `finish_reason=length` at 2048 tokens |

Frozen evidence: `artifacts/live_aitta/comparison-1794011023/` -
per-model `manifest.json` + `results.json` under `llama/`, `gptoss/`,
`qwen/`, `gemma/`, raw per-case lines in `<model>.stdout.log`, and the
lead-authored adjudication in `summary.json`.

**Transparent adjudication:** in the `unknown_product` case, gpt-oss-120b
returned empty `product_ids` with `product_ids` in `unresolved` - a safe
clarification path. The original rubric only accepted naming the unknown
product in `unsupported`; the scorer was updated to accept either an
explicit clarification *or* an unsupported flag, applied equally to the
frozen outputs of all models. Original artifacts are unchanged; the
adjudication is recorded in `summary.json`.

## Selection: openai/gpt-oss-120b

Chosen on accuracy (joint best, 13/13) then latency (~4x faster than the
other 13/13 model). **google/gemma-4-31b-it is the manual backup** - it
was not silently auto-selected, and any switch to it should be a deliberate
manual config change since the app has not been regression-gated on it.

### Final gates on the selected model (all pass)

- `tests/live_aitta_e2e.py` with `LLM_MODEL=openai/gpt-oss-120b`:
  **8/8 paths pass**, real `mode: "llm"` - reuse, extend, build,
  clarify->REUSE, unsupported-metric clarify->NEEDS_REVIEW, access-denied,
  logistics and quality builds. Evidence:
  `artifacts/live_aitta/e2e-1b7642341f4d/`,
  `artifacts/live_aitta/comparison-1794011023/gptoss_final_e2e_stdout.txt`.
- `tests/live_aitta_ui.py` against the running app reconfigured for
  gpt-oss-120b: **3/3 domains pass**, `extraction_mode: "llm"`.
  Evidence: `artifacts/live_aitta/comparison-1794011023/gptoss-final-ui/`.
- Focused offline regression: `tests.test_llm_adapter`,
  `tests.test_llm_providers`, `tests.test_env_loader` - 33 tests, OK.

## Configuration

`.env` and `.env.example` now default to:

```
LLM_PROVIDER=aitta
LLM_MODEL=openai/gpt-oss-120b
```

The earlier Llama 3.3 run remains documented as historical evidence in
`docs/AITTA_LIVE_RESULTS.md`; the running demo on ports 8001/8502 serves
gpt-oss-120b (`GET /api/capabilities` reports model and `configured: true`).
