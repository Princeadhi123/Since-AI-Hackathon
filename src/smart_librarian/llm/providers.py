"""Reviewed provider endpoints and bounded request configuration.

Aitta is an optional R&D service, not a guaranteed production endpoint.
No provider is contacted merely by resolving configuration.
"""

import os
import re
from dataclasses import dataclass


class ProviderConfigurationError(ValueError):
    """Invalid provider selection; never echo environment values."""


@dataclass(frozen=True)
class ProviderSettings:
    provider: str
    label: str
    base_url: str
    credential_env: str
    model: str
    timeout_seconds: float
    json_mode: bool
    max_tokens: int

    @property
    def configured(self) -> bool:
        return bool(os.environ.get(self.credential_env, "").strip())


def _snowflake_base_url() -> str:
    """Build the Cortex REST base URL from a validated account hostname.

    Only a single-label org-account public snowflakecomputing.com host is
    accepted - no scheme, port, path, query, userinfo, or alternate suffix
    can ever turn a PAT-bearing request toward an arbitrary endpoint. The
    rejected value is never echoed.
    """
    host = os.environ.get("SNOWFLAKE_ACCOUNT_HOST", "").strip().lower()
    if not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.snowflakecomputing\.com",
        host,
    ):
        raise ProviderConfigurationError(
            "SNOWFLAKE_ACCOUNT_HOST must be an account hostname ending in "
            ".snowflakecomputing.com (no scheme or path)."
        )
    return f"https://{host}/api/v2/cortex/v1"


def resolve_provider() -> ProviderSettings:
    """Resolve only allowlisted endpoints; never route a key to an arbitrary URL."""
    provider = os.environ.get("LLM_PROVIDER", "openai").strip().lower()
    if provider == "aitta":
        return ProviderSettings(
            provider="aitta",
            label="CSC / LUMI Aitta",
            base_url="https://aitta-api.csc.fi/openai/v1",
            credential_env="AITTA_API_TOKEN",
            model=os.environ.get("LLM_MODEL", "").strip()
            or "meta-llama/Llama-3.3-70B-Instruct",
            timeout_seconds=150.0,
            # OpenAI-compatible does not guarantee JSON-mode support per model.
            # Validate the entire response as JSON/schema locally instead.
            json_mode=False,
            max_tokens=2048,
        )
    if provider == "openai":
        return ProviderSettings(
            provider="openai",
            label="OpenAI",
            base_url="https://api.openai.com/v1",
            credential_env="OPENAI_API_KEY",
            model=os.environ.get("LLM_MODEL", "").strip() or "gpt-4.1-mini",
            timeout_seconds=20.0,
            json_mode=True,
            max_tokens=2048,
        )
    if provider == "featherless":
        return ProviderSettings(
            provider="featherless",
            label="Featherless AI",
            base_url="https://api.featherless.ai/v1",
            credential_env="FEATHERLESS_API_KEY",
            # HF-style model ids; hosted catalog varies, LLM_MODEL overrides.
            model=os.environ.get("LLM_MODEL", "").strip()
            or "Qwen/Qwen2.5-72B-Instruct",
            timeout_seconds=60.0,
            # OpenAI-compatible does not guarantee JSON-mode support per model.
            # Validate the entire response as JSON/schema locally instead.
            json_mode=False,
            max_tokens=2048,
        )
    if provider == "snowflake":
        return ProviderSettings(
            provider="snowflake",
            label="Snowflake Cortex",
            base_url=_snowflake_base_url(),
            credential_env="SNOWFLAKE_PAT",
            model=os.environ.get("LLM_MODEL", "").strip()
            or "claude-sonnet-4-6",
            timeout_seconds=150.0,
            # OpenAI-compatible does not guarantee JSON-mode support per
            # model. Validate the entire response as JSON/schema locally.
            json_mode=False,
            max_tokens=2048,
        )
    raise ProviderConfigurationError(
        "LLM_PROVIDER must be 'openai', 'aitta', 'featherless' or "
        "'snowflake'."
    )
