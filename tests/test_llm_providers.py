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

ALL_KEYS = ("OPENAI_API_KEY", "AITTA_API_TOKEN", "FEATHERLESS_API_KEY",
            "SNOWFLAKE_ACCOUNT_HOST", "SNOWFLAKE_PAT",
            "LLM_PROVIDER", "LLM_MODEL")
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
        self.assertNotIn("max_completion_tokens", capture)

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
        self.assertNotIn("max_completion_tokens", capture)

    def test_featherless_sdk_construction_exact(self):
        import json

        capture, ctor_args = {}, {}
        def fake_openai(**kwargs):
            ctor_args.update(kwargs)
            return _fake_client(content=json.dumps(VALID),
                                capture=capture)
        os.environ.update({
            "LLM_PROVIDER": "featherless",
            "FEATHERLESS_API_KEY": "fl-tok",
        })
        with mock.patch("openai.OpenAI", side_effect=fake_openai):
            OpenAIIntentExtractor().extract_intent(["hi"], {})
        self.assertEqual(ctor_args["api_key"], "fl-tok")
        self.assertEqual(
            ctor_args["base_url"], "https://api.featherless.ai/v1"
        )
        self.assertEqual(ctor_args["timeout"], 60.0)
        self.assertEqual(ctor_args["max_retries"], 0)
        self.assertEqual(capture["model"], "Qwen/Qwen2.5-72B-Instruct")
        self.assertEqual(capture["max_tokens"], 2048)
        # No JSON-mode assumed for Featherless; validation is local.
        self.assertNotIn("response_format", capture)
        self.assertNotIn("max_completion_tokens", capture)

    def test_featherless_selected_with_only_aitta_token_fails_pre_network(self):
        os.environ.update({
            "LLM_PROVIDER": "featherless", "AITTA_API_TOKEN": "aitta-tok",
        })
        with mock.patch("openai.OpenAI") as ctor:
            extractor = OpenAIIntentExtractor()
            with self.assertRaises(LLMUnavailable) as ctx:
                extractor.extract_intent(["hi"], {})
        self.assertIn("FEATHERLESS_API_KEY", str(ctx.exception))
        ctor.assert_not_called()  # fails before any client/network exists

    def test_aitta_selected_with_only_openai_key_fails_pre_network(self):
        os.environ.update({
            "LLM_PROVIDER": "aitta", "OPENAI_API_KEY": "sk-openai",
        })
        with mock.patch("openai.OpenAI") as ctor:
            extractor = OpenAIIntentExtractor()
            with self.assertRaises(LLMUnavailable) as ctx:
                extractor.extract_intent(["hi"], {})
        self.assertIn("AITTA_API_TOKEN", str(ctx.exception))
        ctor.assert_not_called()  # fails before any client/network exists

    def test_aitta_whitespace_token_fails_pre_network(self):
        os.environ.update({
            "LLM_PROVIDER": "aitta", "AITTA_API_TOKEN": "   \t  ",
        })
        with mock.patch("openai.OpenAI") as ctor:
            extractor = OpenAIIntentExtractor()
            with self.assertRaises(LLMUnavailable) as ctx:
                extractor.extract_intent(["hi"], {})
        self.assertIn("AITTA_API_TOKEN", str(ctx.exception))
        ctor.assert_not_called()

    def test_openai_selected_with_only_aitta_token_fails_pre_network(self):
        os.environ.update({"AITTA_API_TOKEN": "aitta-tok"})
        with mock.patch("openai.OpenAI") as ctor:
            extractor = OpenAIIntentExtractor()
            with self.assertRaises(LLMUnavailable) as ctx:
                extractor.extract_intent(["hi"], {})
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))
        ctor.assert_not_called()

    def test_invalid_provider_errors_without_value_leak(self):
        os.environ["LLM_PROVIDER"] = "bogus-provider-value"
        extractor = OpenAIIntentExtractor()
        with self.assertRaises(LLMUnavailable) as ctx:
            extractor.extract_intent(["hi"], {})
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
                    extractor = OpenAIIntentExtractor()
                    with self.assertRaises(LLMUnavailable) as ctx:
                        extractor.extract_intent(["hi"], {})
                self.assertNotIn("tok", str(ctx.exception))


class SnowflakeProviderTests(unittest.TestCase):
    """Snowflake Cortex routing: validated host, own PAT, PAT header."""

    HOST = "myorg-myacct.snowflakecomputing.com"
    PAT = "sf-pat-secret-xyz"

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
        os.environ.update({
            "LLM_PROVIDER": "snowflake",
            "SNOWFLAKE_ACCOUNT_HOST": self.HOST,
            "SNOWFLAKE_PAT": self.PAT,
        })

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()
        self.env.stop()

    def _sdk_capture(self, content=None):
        import json

        capture, ctor_args = {}, {}

        def fake_openai(**kwargs):
            ctor_args.update(kwargs)
            return _fake_client(
                content=json.dumps(VALID) if content is None else content,
                capture=capture,
            )

        return fake_openai, ctor_args, capture

    # 1: exact SDK construction + request shape
    def test_sdk_construction_exact(self):
        # Bogus other-provider keys must never be picked up.
        os.environ.update({
            "OPENAI_API_KEY": "sk-bogus",
            "AITTA_API_TOKEN": "aitta-bogus",
            "FEATHERLESS_API_KEY": "fl-bogus",
            "SNOWFLAKE_ACCOUNT_HOST": "MYORG-MYACCT.SNOWFLAKECOMPUTING.COM",
        })
        fake, ctor_args, capture = self._sdk_capture()
        with mock.patch("openai.OpenAI", side_effect=fake):
            result = OpenAIIntentExtractor().extract_intent(["hi"], {})
        self.assertEqual(ctor_args["api_key"], self.PAT)
        self.assertEqual(
            ctor_args["base_url"],
            "https://myorg-myacct.snowflakecomputing.com/api/v2/cortex/v1",
        )
        self.assertEqual(ctor_args["timeout"], 150.0)
        self.assertEqual(ctor_args["max_retries"], 0)
        self.assertEqual(
            ctor_args["default_headers"],
            {"X-Snowflake-Authorization-Token-Type":
             "PROGRAMMATIC_ACCESS_TOKEN"},
        )
        self.assertEqual(capture["model"], "claude-sonnet-4-6")
        # Snowflake uses the renamed parameter only - never both spellings.
        self.assertEqual(capture["max_completion_tokens"], 2048)
        self.assertNotIn("max_tokens", capture)
        self.assertNotIn("response_format", capture)
        self.assertEqual(capture["messages"][0]["role"], "system")
        self.assertEqual(capture["messages"][1]["role"], "user")
        import json as _json
        self.assertEqual(
            _json.loads(capture["messages"][1]["content"])["conversation"],
            ["hi"],
        )
        self.assertEqual(result["product_ids"], VALID["product_ids"])
        self.assertEqual(result["market_ids"], VALID["market_ids"])
        self.assertEqual(result["months"], VALID["months"])

    # 2: LLM_MODEL env and explicit extractor model override
    def test_model_override_env_and_explicit(self):
        os.environ["LLM_MODEL"] = "fake-cortex-model-a"
        provider = resolve_provider()
        self.assertEqual(provider.model, "fake-cortex-model-a")
        fake, _ctor, capture = self._sdk_capture()
        with mock.patch("openai.OpenAI", side_effect=fake):
            OpenAIIntentExtractor(model="fake-cortex-model-b"
                                  ).extract_intent(["hi"], {})
        self.assertEqual(capture["model"], "fake-cortex-model-b")

    # 3: missing/blank PAT refuses before SDK; no cross-key routing
    def test_missing_pat_fails_pre_network(self):
        for value in (None, "", "   \t "):
            with self.subTest(value=value):
                os.environ.update({
                    "OPENAI_API_KEY": "sk-x", "AITTA_API_TOKEN": "a-x",
                    "FEATHERLESS_API_KEY": "f-x",
                })
                if value is None:
                    os.environ.pop("SNOWFLAKE_PAT", None)
                else:
                    os.environ["SNOWFLAKE_PAT"] = value
                with mock.patch("openai.OpenAI") as ctor:
                    extractor = OpenAIIntentExtractor()
                    with self.assertRaises(LLMUnavailable) as ctx:
                        extractor.extract_intent(["hi"], {})
                self.assertIn("SNOWFLAKE_PAT", str(ctx.exception))
                ctor.assert_not_called()

    def test_snowflake_pat_not_routed_to_other_providers(self):
        for provider, cred in (("openai", "OPENAI_API_KEY"),
                               ("aitta", "AITTA_API_TOKEN"),
                               ("featherless", "FEATHERLESS_API_KEY")):
            with self.subTest(provider=provider):
                os.environ["LLM_PROVIDER"] = provider
                with mock.patch("openai.OpenAI") as ctor:
                    extractor = OpenAIIntentExtractor()
                    with self.assertRaises(LLMUnavailable) as ctx:
                        extractor.extract_intent(["hi"], {})
                self.assertIn(cred, str(ctx.exception))
                ctor.assert_not_called()
        os.environ["LLM_PROVIDER"] = "snowflake"

    # 4: host validation - attack strings rejected, never echoed
    def test_invalid_hosts_rejected_before_sdk(self):
        bad = [
            "", "   ",
            "https://myorg-myacct.snowflakecomputing.com",
            "myorg-myacct.snowflakecomputing.com/path",
            "myorg-myacct.snowflakecomputing.com:443",
            "user@myorg-myacct.snowflakecomputing.com",
            "myorg-myacct.snowflakecomputing.com?query=1",
            "myorg-myacct.evil.com",
            "snowflakecomputing.com",
            "localhost",
            "127.0.0.1",
            "my_org-myacct.snowflakecomputing.com",
        ]
        expected_msg = (
            "SNOWFLAKE_ACCOUNT_HOST must be an account hostname ending "
            "in .snowflakecomputing.com (no scheme or path)."
        )
        for host in bad:
            with self.subTest(host=host):
                os.environ["SNOWFLAKE_ACCOUNT_HOST"] = host
                with self.assertRaises(ProviderConfigurationError) as ctx:
                    resolve_provider()
                # Fixed authored message - never echoes the input value.
                self.assertEqual(str(ctx.exception), expected_msg)
                status = provider_status()
                self.assertFalse(status["configured"])
                self.assertEqual(status["error"], expected_msg)
                with mock.patch("openai.OpenAI") as ctor:
                    extractor = OpenAIIntentExtractor()
                    with self.assertRaises(LLMUnavailable) as exc_ctx:
                        extractor.extract_intent(["hi"], {})
                self.assertEqual(str(exc_ctx.exception), expected_msg)
                if host.strip() and host.strip() not in expected_msg:
                    self.assertNotIn(host.strip(), str(status))
                ctor.assert_not_called()
        os.environ["SNOWFLAKE_ACCOUNT_HOST"] = self.HOST

    def test_valid_host_without_pat_not_configured_no_network(self):
        os.environ.pop("SNOWFLAKE_PAT", None)
        status = provider_status()
        self.assertEqual(status["provider"], "snowflake")
        self.assertFalse(status["configured"])

    # 5: status exposes names only, never the token
    def test_status_reports_names_only(self):
        status = provider_status()
        self.assertTrue(status["configured"])
        self.assertEqual(status["provider"], "snowflake")
        self.assertEqual(status["label"], "Snowflake Cortex")
        self.assertEqual(status["credential_env"], "SNOWFLAKE_PAT")
        self.assertEqual(status["model"], "claude-sonnet-4-6")
        self.assertEqual(status["timeout_seconds"], 150.0)
        self.assertNotIn(self.PAT, str(status))

    # 6: provider exceptions and bad payloads stay sanitized
    def test_provider_error_with_token_in_message_is_sanitized(self):
        def create(**kwargs):
            raise RuntimeError(f"401 invalid token {self.PAT}")

        bad_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        with mock.patch("openai.OpenAI", return_value=bad_client):
            extractor = OpenAIIntentExtractor()
            with self.assertRaises(LLMUnavailable) as ctx:
                extractor.extract_intent(["hi"], {})
        self.assertNotIn(self.PAT, str(ctx.exception))

    def test_non_json_or_invalid_schema_fails_safely(self):
        for content in ("not json", "<html>err</html>", '{"x": 1}', ""):
            with self.subTest(content=content[:20]):
                fake, _ctor, _cap = self._sdk_capture(content=content)
                with mock.patch("openai.OpenAI", side_effect=fake):
                    extractor = OpenAIIntentExtractor()
                    with self.assertRaises(LLMUnavailable) as ctx:
                        extractor.extract_intent(["hi"], {})
                self.assertNotIn(self.PAT, str(ctx.exception))

    # 7: real request path via httpx.MockTransport (no network)
    def test_full_http_request_path_with_mock_transport(self):
        try:
            import httpx
            import openai as openai_mod
        except ImportError:
            self.skipTest("httpx/openai not installed")
        import json

        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            seen["type"] = request.headers.get(
                "x-snowflake-authorization-token-type")
            seen["body"] = json.loads(request.content.decode())
            return httpx.Response(200, json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "claude-sonnet-4-6",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant",
                                "content": json.dumps(VALID)},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                          "total_tokens": 2},
            })

        transport = httpx.MockTransport(handler)
        real_openai = openai_mod.OpenAI  # capture before patching

        def patched_openai(**kwargs):
            kwargs["http_client"] = httpx.Client(transport=transport)
            return real_openai(**kwargs)

        with mock.patch("openai.OpenAI", side_effect=patched_openai):
            result = OpenAIIntentExtractor().extract_intent(["hi"], {})
        self.assertEqual(
            seen["url"],
            "https://myorg-myacct.snowflakecomputing.com"
            "/api/v2/cortex/v1/chat/completions",
        )
        self.assertEqual(seen["auth"], f"Bearer {self.PAT}")
        self.assertEqual(seen["type"], "PROGRAMMATIC_ACCESS_TOKEN")
        self.assertEqual(seen["body"]["model"], "claude-sonnet-4-6")
        self.assertEqual(seen["body"]["max_completion_tokens"], 2048)
        self.assertNotIn("max_tokens", seen["body"])
        self.assertNotIn("response_format", seen["body"])
        self.assertEqual(result["product_ids"], VALID["product_ids"])


if __name__ == "__main__":
    unittest.main()
