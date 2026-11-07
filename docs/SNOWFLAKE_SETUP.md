# Snowflake Cortex provider setup

The demo can use **Snowflake Cortex** as its optional LLM
intent-extraction provider through the standard OpenAI SDK against the
Cortex REST API. It is opt-in only: no provider call happens unless the
sidebar checkbox is ticked, and every failure falls back to the offline
parser. Requests are paid Cortex calls on your account — set this up only
when you are ready to use it.

## Official references

- Cortex REST API (OpenAI-compatible):
  <https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-rest-api>
- Programmatic access tokens (PAT):
  <https://docs.snowflake.com/en/user-guide/programmatic-access-tokens>

## What you need

- A Snowflake account hostname in the **public org-account** form
  `<org>-<account>.snowflakecomputing.com`. This integration intentionally
  supports that single-label public form only — not private-link,
  government, or regional URL variants.
- A **programmatic access token (PAT)**. Create one in Snowsight:
  user/profile menu → Settings/profile → Authentication →
  *Programmatic access tokens* (labels vary between Snowsight versions).
  Generate a local short-lived token restricted to a dedicated
  least-privilege role that has `SNOWFLAKE.CORTEX_REST_API_USER` (or the
  older `CORTEX_USER`) granted. Do **not** create an ACCOUNTADMIN token,
  and do not modify account-wide network or authentication policies.
- PAT creation can be constrained by account network/authentication
  policies — if generation or use is refused, ask your Snowflake admin;
  share only the error text (never the token) and do not bypass security
  controls.
- Playground success is **not** proof of REST/PAT access — they are
  different surfaces. Trial credit terms vary; we cannot guarantee your
  trial credit covers Cortex REST calls — monitor usage/billing in
  Snowsight.

## Configure (no secrets in files preferred)

The local `.env` is git-ignored and must never be committed. Prefer process
environment (which always wins over `.env`). If you edit an existing
`.env`, merge only the keys you need without overwriting other credentials.
Never paste tokens into shared files.

In PowerShell, in the same terminal you will launch from:

```powershell
# Non-secret configuration
$env:LLM_PROVIDER = 'snowflake'
$env:SNOWFLAKE_ACCOUNT_HOST = 'TNRTNCL-SX96827.snowflakecomputing.com'
$env:LLM_MODEL = 'claude-sonnet-4-6'
```

```powershell
# Token entry without leaving it in command history
$cortexToken = Read-Host 'Snowflake PAT' -AsSecureString
$env:SNOWFLAKE_PAT = [System.Net.NetworkCredential]::new('', $cortexToken).Password
```

Then launch the demo in that same terminal:

```powershell
.\.venv\Scripts\python.exe run_demo.py --mode challenge --api-port 8021 --ui-port 8521
```

- Process env overrides `.env`, so this works even with a local `.env`
  present. Use the **foreground** launcher — the scheduled `--background`
  task does not inherit shell-only variables.
- Never start a second copy over an already-running instance; the
  launcher refuses busy ports rather than killing unknown processes.

Equivalent `.env` lines (merge, do not overwrite):

```dotenv
LLM_PROVIDER=snowflake
SNOWFLAKE_ACCOUNT_HOST=TNRTNCL-SX96827.snowflakecomputing.com
LLM_MODEL=claude-sonnet-4-6
SNOWFLAKE_PAT=<store locally; never share>
```

## How it is wired

- Endpoint is derived from `SNOWFLAKE_ACCOUNT_HOST` only after strict
  hostname validation → `https://<host>/api/v2/cortex/v1`. There is no
  arbitrary URL override, and a rejected host value is never echoed in
  errors.
- The token comes only from `SNOWFLAKE_PAT` and is sent only to that
  endpoint (Bearer + `X-Snowflake-Authorization-Token-Type:
  PROGRAMMATIC_ACCESS_TOKEN`). It can never be routed to another
  provider, and other providers' keys are never routed to Snowflake.
- Default model `claude-sonnet-4-6` (the one confirmed in the user's
  Playground test); override with `LLM_MODEL`. Timeout 150 s, no retries,
  no JSON-mode assumption — responses are validated locally as before.
  The Snowflake request uses `max_completion_tokens` (Cortex's current
  parameter name) with the same bounded 2048 value other providers send
  as `max_tokens`.
- `GET /api/capabilities` reports provider label/model/credential env
  *name* — never the token.

## First live check (when you are ready — costs tokens)

Run one manual extraction through the challenge Builder page with the
opt-in ticked and confirm the caption reads `last extraction: llm`. An
`offline_fallback_after_llm_unavailable` caption is an honest fallback,
**not** a live pass. Four exact challenge-domain extraction requests passed
live testing with `claude-sonnet-4-6` on 7 November 2026. This does not
verify general extraction accuracy, approvals, exports, or REUSE.
