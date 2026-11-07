"""Optional LLM intent-extraction adapter (OpenAI or CSC/LUMI Aitta).

Used only when a request explicitly opts in (use_llm=true). The system prompt
is exactly the lead-authored intent_prompt.txt package resource; no other
instructions are added. Catalog choices sent contain metadata only - never
source business figures - but the user's own request text may contain
whatever they typed; the UI warns not to enter secrets. Provider errors are
sanitized and never include credentials.
"""

import json
import os
import re
from importlib import resources

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from smart_librarian.llm.providers import (
    ProviderConfigurationError,
    resolve_provider,
)
from smart_librarian.workflow.service import LLMUnavailable

_REQUEST_MAX_RETRIES = 0


class _IntentExtraction(BaseModel):
    """Exact fields the lead-authored prompt requires the model to return."""

    model_config = ConfigDict(extra="forbid")

    product_ids: list[str] = Field(max_length=100)
    market_ids: list[str] = Field(max_length=100)
    metric_ids: list[str] = Field(max_length=100)
    months: list[str] = Field(max_length=100)
    grain: str | None = Field(default=None, max_length=50)
    unresolved: list[str] = Field(max_length=50)
    unsupported: list[str] = Field(max_length=50)


def _system_prompt() -> str:
    return (
        resources.files("smart_librarian.llm")
        .joinpath("intent_prompt.txt")
        .read_text(encoding="utf-8")
    )


def _build_client(provider):
    """Credential check plus SDK construction for the resolved provider.

    The key always comes from that provider's own credential env var - there
    is no cross-provider fallback, so a token can never be routed to the
    wrong endpoint.
    """
    api_key = (os.environ.get(provider.credential_env) or "").strip()
    if not api_key:
        raise LLMUnavailable(f"{provider.credential_env} is not configured.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMUnavailable("openai package is not installed.") from exc
    try:
        kwargs = {
            "api_key": api_key,
            "base_url": provider.base_url,
            "timeout": provider.timeout_seconds,
            "max_retries": _REQUEST_MAX_RETRIES,
        }
        if provider.provider == "snowflake":
            kwargs["default_headers"] = {
                "X-Snowflake-Authorization-Token-Type":
                    "PROGRAMMATIC_ACCESS_TOKEN",
            }
        return OpenAI(**kwargs)
    except Exception as exc:  # sanitized: provider error class only
        raise LLMUnavailable(
            f"provider request failed ({type(exc).__name__})"
        ) from exc


def _request_extraction(client, provider, model: str, payload: dict) -> object:
    """Provider call plus strict JSON parse; sanitized failures."""
    # Snowflake Cortex renamed the parameter; never send both spellings.
    token_limit_key = (
        "max_completion_tokens" if provider.provider == "snowflake"
        else "max_tokens"
    )
    kwargs = {
        "model": model,
        token_limit_key: provider.max_tokens,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": json.dumps(payload)},
        ],
    }
    if provider.json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        response = client.chat.completions.create(**kwargs)
        content = (response.choices[0].message.content or "{}").strip()
        fenced = re.fullmatch(
            r"```(?:json)?[ \t]*\r?\n(?P<body>.*?)\r?\n```",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        return json.loads(fenced.group("body") if fenced else content)
    except LLMUnavailable:
        raise
    except Exception as exc:  # sanitized: provider error class only
        raise LLMUnavailable(
            f"provider request failed ({type(exc).__name__})"
        ) from exc


def _validate_extraction(data) -> dict:
    try:
        extraction = _IntentExtraction.model_validate(data)
    except ValidationError as exc:
        raise LLMUnavailable("LLM returned an invalid intent object.") from exc
    result = extraction.model_dump()
    result["invalidated"] = [
        field for field in ("product_ids", "market_ids", "metric_ids", "months")
        if field in (result["unresolved"] or [])
    ]
    return result


class OpenAIIntentExtractor:
    def __init__(self, model: str | None = None):
        from smart_librarian.settings import load_settings

        self._explicit_model = model
        self.model = model or load_settings().llm_model

    def extract_intent(self, conversation: list[str],
                       catalog_choices: dict) -> dict:
        # Provider is resolved on every call so config changes are honored;
        # the selected provider's credential env is the only key source.
        try:
            provider = resolve_provider()
        except ProviderConfigurationError as exc:
            # Resolution messages are authored to be sanitized - they never
            # contain environment values - so surface them directly.
            raise LLMUnavailable(str(exc)) from exc
        client = _build_client(provider)
        payload = {
            "conversation": conversation,
            "catalog_choices": catalog_choices,
            "response_schema": _IntentExtraction.model_json_schema(),
        }
        model = self._explicit_model or provider.model
        data = _request_extraction(client, provider, model, payload)
        return _validate_extraction(data)
