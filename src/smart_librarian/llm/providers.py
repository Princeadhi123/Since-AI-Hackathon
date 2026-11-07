"""Reviewed provider endpoints and bounded request configuration.

Aitta is an optional R&D service, not a guaranteed production endpoint.
No provider is contacted merely by resolving configuration.
"""

import os
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
    raise ProviderConfigurationError("LLM_PROVIDER must be 'openai' or 'aitta'.")
