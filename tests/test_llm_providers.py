"""Provider routing tests: exact SDK construction, credential isolation,
sanitized failures. No external requests - the SDK client is stubbed."""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

from smart_librarian.llm.client import OpenAIIntentExtractor
from smart_librarian.llm.providers import (
    ProviderConfigurationError,
    resolve_provider,
)
from smart_librarian.settings import provider_status
from smart_librarian.workflow.service import LLMUnavailable

ALL_KEYS = ("OPENAI_API_KEY", "AITTA_API_TOKEN", "LLM_PROVIDER", "LLM_MODEL")
VALID = {
    "product_ids": ["DEMO-P-NUB"], "market_ids": ["DE"],
    "metric_ids": ["DEMO-NET-SALES"], "months": ["2026-01-01"],
    "grain": "month", "unresolved": [], "unsupported": [],
}


def _fake_client(content=None, capture=None):
    def create(**kwargs):
        if capture is not None:
            capture.update(kwargs)
        message = SimpleNamespace(message=SimpleNamespace(content=content))
        return SimpleNamespace(choices=[message])
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


class ProviderRoutingTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for key in ALL_KEYS:
            os.environ.pop(key, None)
        # Repo .env (e.g. a real Aitta config) must never leak into tests.
        import tempfile
        import smart_librarian.settings as settings_module
        from pathlib import Path

        self.temp = tempfile.TemporaryDirectory()
        self.root_patch = mock.patch.object(
            settings_module, "REPO_ROOT", Path(self.temp.name)
        )
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()
        self.env.stop()

    def test_openai_sdk_construction_exact(self):
        import json

        capture = {}
        ctor_args = {}
        def fake_openai(**kwargs):
            ctor_args.update(kwargs)
            return _fake_client(content=json.dumps(VALID),
                                capture=capture)
        os.environ.update({"OPENAI_API_KEY": "sk-openai"})
        with mock.patch("openai.OpenAI", side_effect=fake_openai):
            OpenAIIntentExtractor().extract_intent(["hi"], {})
        self.assertEqual(ctor_args["api_key"], "sk-openai")
        self.assertEqual(ctor_args["base_url"], "https://api.openai.com/v1")
        self.assertEqual(ctor_args["timeout"], 20.0)
        self.assertEqual(ctor_args["max_retries"], 0)
        self.assertEqual(capture["model"], "gpt-4.1-mini")
        self.assertEqual(capture["max_tokens"], 2048)
        self.assertEqual(
            capture["response_format"], {"type": "json_object"}
        )

    def test_aitta_sdk_construction_exact(self):
        import json

        capture, ctor_args = {}, {}
        def fake_openai(**kwargs):
            ctor_args.update(kwargs)
            return _fake_client(content=json.dumps(VALID),
                                capture=capture)
        os.environ.update({
            "LLM_PROVIDER": "aitta", "AITTA_API_TOKEN": "aitta-tok",
        })
        with mock.patch("openai.OpenAI", side_effect=fake_openai):
            OpenAIIntentExtractor().extract_intent(["hi"], {})
        self.assertEqual(ctor_args["api_key"], "aitta-tok")
        self.assertEqual(
            ctor_args["base_url"], "https://aitta-api.csc.fi/openai/v1"
        )
        self.assertEqual(ctor_args["timeout"], 150.0)
        self.assertEqual(ctor_args["max_retries"], 0)
        self.assertEqual(
            capture["model"], "meta-llama/Llama-3.3-70B-Instruct"
        )
        self.assertEqual(capture["max_tokens"], 2048)
        # No JSON-mode assumed for Aitta; validation is local.
        self.assertNotIn("response_format", capture)

    def test_aitta_selected_with_only_openai_key_fails_pre_network(self):
        os.environ.update({
            "LLM_PROVIDER": "aitta", "OPENAI_API_KEY": "sk-openai",
        })
        with mock.patch("openai.OpenAI") as ctor:
            with self.assertRaises(LLMUnavailable) as ctx:
                OpenAIIntentExtractor().extract_intent(["hi"], {})
        self.assertIn("AITTA_API_TOKEN", str(ctx.exception))
        ctor.assert_not_called()  # fails before any client/network exists

    def test_aitta_whitespace_token_fails_pre_network(self):
        os.environ.update({
            "LLM_PROVIDER": "aitta", "AITTA_API_TOKEN": "   \t  ",
        })
        with mock.patch("openai.OpenAI") as ctor:
            with self.assertRaises(LLMUnavailable) as ctx:
                OpenAIIntentExtractor().extract_intent(["hi"], {})
        self.assertIn("AITTA_API_TOKEN", str(ctx.exception))
        ctor.assert_not_called()

    def test_openai_selected_with_only_aitta_token_fails_pre_network(self):
        os.environ.update({"AITTA_API_TOKEN": "aitta-tok"})
        with mock.patch("openai.OpenAI") as ctor:
            with self.assertRaises(LLMUnavailable) as ctx:
                OpenAIIntentExtractor().extract_intent(["hi"], {})
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))
        ctor.assert_not_called()

    def test_invalid_provider_errors_without_value_leak(self):
        os.environ["LLM_PROVIDER"] = "bogus-provider-value"
        with self.assertRaises(LLMUnavailable) as ctx:
            OpenAIIntentExtractor().extract_intent(["hi"], {})
        self.assertNotIn("bogus-provider-value", str(ctx.exception))
        with self.assertRaises(ProviderConfigurationError):
            resolve_provider()
        status = provider_status()
        self.assertFalse(status["configured"])
        self.assertIn("error", status)
        self.assertNotIn("bogus-provider-value", str(status))

    def test_status_reports_names_only(self):
        os.environ.update({
            "LLM_PROVIDER": "aitta",
            "AITTA_API_TOKEN": "super-secret-token",
        })
        status = provider_status()
        self.assertEqual(status["provider"], "aitta")
        self.assertEqual(status["credential_env"], "AITTA_API_TOKEN")
        self.assertTrue(status["configured"])
        self.assertEqual(status["timeout_seconds"], 150.0)
        self.assertNotIn("super-secret-token", str(status))

    def test_payload_carries_response_schema_not_business_values(self):
        import json

        capture = {}
        os.environ["OPENAI_API_KEY"] = "k"
        with mock.patch(
            "openai.OpenAI",
            return_value=_fake_client(content=json.dumps(VALID),
                                      capture=capture),
        ):
            OpenAIIntentExtractor().extract_intent(["hi"], {})
        user_content = json.loads(capture["messages"][1]["content"])
        self.assertIn("response_schema", user_content)
        schema = user_content["response_schema"]
        self.assertIn("product_ids", schema.get("properties", {}))
        self.assertNotIn("107000", json.dumps(schema))

    def test_non_json_aitta_content_fails_safely(self):
        os.environ.update({
            "LLM_PROVIDER": "aitta", "AITTA_API_TOKEN": "tok",
        })
        for content in ("I cannot help with that", "<html>err</html>",
                        '{"product_ids": [', ""):
            with self.subTest(content=content[:20]):
                with mock.patch(
                    "openai.OpenAI",
                    return_value=_fake_client(content=content),
                ):
                    with self.assertRaises(LLMUnavailable) as ctx:
                        OpenAIIntentExtractor().extract_intent(["hi"], {})
                self.assertNotIn("tok", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
