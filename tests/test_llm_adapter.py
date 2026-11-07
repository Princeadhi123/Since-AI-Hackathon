"""Unit tests for the opt-in LLM adapter with a stubbed SDK.

No external requests are made; the OpenAI client is replaced by a fake.
"""

import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from smart_librarian.llm.client import OpenAIIntentExtractor
from smart_librarian.workflow.service import LLMUnavailable

VALID = {
    "product_ids": ["DEMO-P-NUB"],
    "market_ids": ["DE"],
    "metric_ids": ["DEMO-NET-SALES"],
    "months": ["2026-01-01"],
    "grain": "month",
    "unresolved": [],
    "unsupported": [],
}


def _fake_client(content):
    message = SimpleNamespace(message=SimpleNamespace(content=content))
    completions = SimpleNamespace(create=lambda **_: SimpleNamespace(choices=[message]))
    chat = SimpleNamespace(completions=completions)
    return SimpleNamespace(chat=chat)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.extractor = OpenAIIntentExtractor(model="stub-model")
        self.env = mock.patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-key", "LLM_PROVIDER": "openai"},
        )
        self.env.start()
        os.environ.pop("AITTA_API_TOKEN", None)

    def tearDown(self):
        self.env.stop()

    def call(self, content):
        with mock.patch("openai.OpenAI", return_value=_fake_client(content)):
            return self.extractor.extract_intent(["show me sales"], {"choices": True})

    def test_valid_payload_parses(self):
        result = self.call(json.dumps(VALID))
        self.assertEqual(result["product_ids"], ["DEMO-P-NUB"])
        self.assertEqual(result["grain"], "month")

    def test_non_object_payload_rejected(self):
        payload = json.dumps(["not", "an", "object"])
        with self.assertRaises(LLMUnavailable):
            self.call(payload)

    def test_extra_keys_rejected(self):
        payload = json.dumps({**VALID, "report_name": "leak"})
        with self.assertRaises(LLMUnavailable):
            self.call(payload)

    def test_missing_fields_rejected(self):
        incomplete = {key: value for key, value in VALID.items() if key != "months"}
        payload = json.dumps(incomplete)
        with self.assertRaises(LLMUnavailable):
            self.call(payload)

    def test_malformed_json_rejected(self):
        with self.assertRaises(LLMUnavailable):
            self.call("{not json")

    def test_json_fenced_document_parses(self):
        result = self.call(f"```json\n{json.dumps(VALID)}\n```")
        self.assertEqual(result["product_ids"], ["DEMO-P-NUB"])
        self.assertEqual(result["grain"], "month")

    def test_bare_fenced_document_parses(self):
        result = self.call(f"```\n{json.dumps(VALID)}\n```")
        self.assertEqual(result["product_ids"], ["DEMO-P-NUB"])

    def test_fenced_crlf_and_whitespace_parses(self):
        result = self.call(f"  ```json \t\r\n{json.dumps(VALID)}\r\n```  ")
        self.assertEqual(result["product_ids"], ["DEMO-P-NUB"])

    def test_prose_around_fence_rejected(self):
        for payload in (
            f"Here is the intent:\n```json\n{json.dumps(VALID)}\n```",
            f"```json\n{json.dumps(VALID)}\n```\nLet me know if that helps.",
            f"Note\n```json\n{json.dumps(VALID)}\n```\nDone",
        ):
            with self.assertRaises(LLMUnavailable):
                self.call(payload)

    def test_multiple_fences_rejected(self):
        payload = (
            f"```json\n{json.dumps(VALID)}\n```"
            f"\n```json\n{json.dumps(VALID)}\n```"
        )
        with self.assertRaises(LLMUnavailable):
            self.call(payload)

    def test_truncated_fence_rejected(self):
        with self.assertRaises(LLMUnavailable):
            self.call(f"```json\n{json.dumps(VALID)}")

    def test_malformed_fenced_json_rejected(self):
        with self.assertRaises(LLMUnavailable):
            self.call("```json\n{not json}\n```")

    def test_fenced_extra_schema_fields_rejected(self):
        payload = json.dumps({**VALID, "report_name": "leak"})
        with self.assertRaises(LLMUnavailable):
            self.call(f"```json\n{payload}\n```")

    def test_fenced_non_object_rejected(self):
        with self.assertRaises(LLMUnavailable):
            self.call('```json\n["not", "an", "object"]\n```')

    def test_missing_key_is_safe_error(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OPENAI_API_KEY", None)
            with self.assertRaises(LLMUnavailable) as ctx:
                self.extractor.extract_intent(["hi"], {})
        self.assertNotIn("test-key", str(ctx.exception))

    def test_client_construction_error_sanitized(self):
        with mock.patch(
            "openai.OpenAI",
            side_effect=RuntimeError("sensitive credential detail"),
        ):
            with self.assertRaises(LLMUnavailable) as ctx:
                self.extractor.extract_intent(["hi"], {})
        self.assertNotIn("sensitive", str(ctx.exception))
        self.assertIn("RuntimeError", str(ctx.exception))

    def test_provider_error_sanitized(self):
        def boom(**_):
            raise RuntimeError("secret api-key-value should not leak")

        completions = SimpleNamespace(create=boom)
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        with mock.patch("openai.OpenAI", return_value=client):
            with self.assertRaises(LLMUnavailable) as ctx:
                self.extractor.extract_intent(["hi"], {})
        self.assertNotIn("api-key-value", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
