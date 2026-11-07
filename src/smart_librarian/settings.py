"""Environment-driven settings. Stdlib .env loading; process env always wins."""

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Only these keys may be set from a .env file. Anything else is ignored so a
# stray file cannot inject unrelated environment variables.
_DOTENV_ALLOWED_KEYS = frozenset(
    {"OPENAI_API_KEY", "AITTA_API_TOKEN", "FEATHERLESS_API_KEY",
     "SNOWFLAKE_ACCOUNT_HOST", "SNOWFLAKE_PAT",
     "LLM_PROVIDER", "LLM_MODEL", "DEMO_DATA_DIR", "RUNTIME_DB_PATH"}
)


@dataclass(frozen=True)
class Settings:
    demo_dir: Path
    runtime_db: Path
    llm_model: str

    @property
    def catalog_path(self) -> Path:
        return self.demo_dir / "catalog.json"

    @property
    def demo_db_path(self) -> Path:
        return self.demo_dir / "demo.sqlite"


def _resolve(value: str | None, default: Path) -> Path:
    if not value:
        return default
    path = Path(value)
    return path if path.is_absolute() else (REPO_ROOT / path)


def _parse_dotenv_line(line: str) -> tuple[str, str] | None:
    """Parse one .env line. Returns (key, value) or None.

    Accepts ``KEY=value`` with an optional ``export `` prefix and optional
    single or double quotes around the value. No shell expansion, no
    variable substitution, no command execution.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export "):].lstrip()
    if "=" not in line:
        return None
    key, _, value = line.partition("=")
    key = key.strip()
    if key not in _DOTENV_ALLOWED_KEYS:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return key, value


def load_dotenv(path: Path | None = None) -> set:
    """Load allowed keys from a .env file into os.environ.

    Process environment always wins: a key already present in os.environ is
    never overwritten. Only the names of loaded keys are returned - values
    (which may be secrets) are never exposed by this function. Missing file
    is a no-op.
    """
    path = Path(path) if path else (REPO_ROOT / ".env")
    loaded: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return loaded
    for line in text.splitlines():
        parsed = _parse_dotenv_line(line)
        if parsed is None:
            continue
        key, value = parsed
        loaded.add(key)
        os.environ.setdefault(key, value)
    return loaded


def load_settings() -> Settings:
    """Resolve paths relative to the repository root regardless of cwd."""
    load_dotenv()
    return Settings(
        demo_dir=_resolve(os.environ.get("DEMO_DATA_DIR"), REPO_ROOT / "data" / "demo_v1"),
        runtime_db=_resolve(
            os.environ.get("RUNTIME_DB_PATH"), REPO_ROOT / "var" / "runtime.sqlite"
        ),
        llm_model=_resolve_model(),
    )


def _resolve_model() -> str:
    """Model for settings; an invalid provider never breaks startup."""
    from smart_librarian.llm.providers import (
        ProviderConfigurationError,
        resolve_provider,
    )

    try:
        return resolve_provider().model
    except ProviderConfigurationError:
        # Inert fallback: nothing is contacted at settings time.
        return os.environ.get("LLM_MODEL", "gpt-4.1-mini")


def provider_status() -> dict:
    """LLM provider configuration status. No network calls, no secrets."""
    from smart_librarian.llm.providers import (
        ProviderConfigurationError,
        resolve_provider,
    )

    load_dotenv()
    try:
        provider = resolve_provider()
    except ProviderConfigurationError as exc:
        # Resolution messages are authored sanitized - never user values.
        return {
            "configured": False,
            "provider": None,
            "label": None,
            "model": _resolve_model(),
            "timeout_seconds": None,
            "credential_env": None,
            "error": str(exc),
        }
    return {
        "configured": provider.configured,
        "provider": provider.provider,
        "label": provider.label,
        "model": provider.model,
        "timeout_seconds": provider.timeout_seconds,
        "credential_env": provider.credential_env,
    }
