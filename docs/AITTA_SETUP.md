# Aitta (CSC / LUMI) provider setup

The demo can use **CSC Aitta** as its optional LLM intent-extraction provider
through the standard OpenAI SDK, instead of api.openai.com. It is opt-in only:
no provider call happens unless the sidebar checkbox is ticked, and every
failure falls back to the offline parser.

## Official references

- Hackathon resources: <https://sinceai.ai/hackathon-2026/guide/resources#ai-resources>
  (access granted to eligible preregistered participants; joining
  instructions are private - there are no public event tokens)
- Aitta docs: <https://docs.lumi-supercomputer.eu/laif/inference/aitta/>
- OpenAI-compatible endpoint: `https://aitta-api.csc.fi/openai/v1`
- Token page: <https://aitta-auth.csc.fi/myToken>

## Access / cost

Aitta access is tied to the event registration (eligibility required
preregistration by Oct 30) - it is **not** an unrestricted free public API,
and tokens can expire when the event project ends, even before their normal
~90-day validity. Verified today: the public `/status` endpoint
reports the service available and `/model` lists
`meta-llama/Llama-3.3-70B-Instruct` among others. Authenticated inference
through this token has been verified end to end - see
`docs/AITTA_LIVE_RESULTS.md` and `docs/AITTA_MODEL_COMPARISON.md` for the
model selection. Per CSC's own guidance, Aitta is
for research and development use - do not send sensitive or personal data.

## Configure

Create a local `.env` (git-ignored - `.env.example` is only a template):

```
LLM_PROVIDER=aitta
AITTA_API_TOKEN=<your token from https://aitta-auth.csc.fi/myToken>
LLM_MODEL=openai/gpt-oss-120b
```

- The token is read only from `AITTA_API_TOKEN` and only sent to the fixed
  Aitta endpoint; an OpenAI key is never routed there (and vice versa).
- Model cold start: the first request may take a while - the client waits up
  to 150 s and the UI shows a warm-start spinner. Timeouts and failures fall
  back to the offline parser safely.
- `GET /api/capabilities` reports provider label, model, timeout and the
  credential env var *name* - never the secret value.

## Alternatives mentioned at the event (not implemented)

For completeness only - none of these are wired in and no accounts/coupons
are claimed here: Featherless (limited-time event credit), n8n (event team
offer), Google AI Studio (free tier). This project integrates Aitta for the
event; the existing OpenAI adapter remains as an alternative provider.
