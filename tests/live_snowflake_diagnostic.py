"""Opt-in single-request Cortex connectivity diagnostic, not an accuracy test.

Run in the private terminal holding the replacement PAT:
    python tests/live_snowflake_diagnostic.py --allow-provider-call
Only a fixed, non-confidential user message is sent. This costs tokens.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smart_librarian.llm.client import _build_client
from smart_librarian.llm.providers import resolve_provider
from smart_librarian.settings import load_settings


def safe_error_detail(exc):
    """Extract bounded error fields, never headers, request bodies, or tokens."""
    body = getattr(exc, "body", None)
    error = body.get("error", body) if isinstance(body, dict) else {}
    if not isinstance(error, dict):
        error = {}
    fields = {"exception": type(exc).__name__}
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        fields["http_status"] = status
    for key in ("code", "message"):
        value = error.get(key)
        if not isinstance(value, (str, int)):
            continue
        text = str(value)
        for name in (
            "SNOWFLAKE_PAT", "AITTA_API_TOKEN", "OPENAI_API_KEY",
            "FEATHERLESS_API_KEY",
        ):
            secret = os.environ.get(name, "").strip()
            if secret:
                text = text.replace(secret, "[REDACTED]")
        text = re.sub(
            r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
            "[REDACTED_TOKEN_OR_HOST]",
            text,
        )
        text = re.sub(
            r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", text,
        )
        fields[key] = text[:1600]
    return fields


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-provider-call", action="store_true")
    args = parser.parse_args()
    if not args.allow_provider_call:
        print("NOT RUN: --allow-provider-call is required. No request made.")
        return 2
    try:
        load_settings()
        provider = resolve_provider()
        if provider.provider != "snowflake" or not provider.configured:
            print("NOT RUN: select Snowflake and configure its replacement PAT.")
            return 2
        with _build_client(provider) as client:
            response = client.chat.completions.create(
                model=provider.model,
                max_completion_tokens=provider.max_tokens,
                messages=[{
                    "role": "user",
                    "content": "Reply with exactly: Cortex is working",
                }],
            )
            if not response.choices or not response.choices[0].message.content:
                print("No response text received; connectivity not confirmed.")
                return 1
        print(json.dumps({
            "result": "Live Cortex response received",
            "scope": "Connectivity only; four-domain extraction not verified.",
        }, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps(safe_error_detail(exc), indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
