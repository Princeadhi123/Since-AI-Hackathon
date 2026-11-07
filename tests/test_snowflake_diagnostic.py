"""Offline checks for tests/live_snowflake_diagnostic.py.

All seams mocked - no network, no real tokens, no .env reads. This is a
regression test for the diagnostic script's request shape and redaction,
not a provider eval harness.
"""

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPT = (
    Path(__file__).resolve().parent / "live_snowflake_diagnostic.py"
)
spec = importlib.util.spec_from_file_location("snowflake_diag", SCRIPT)
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


def _provider(provider="snowflake", configured=True,
              model="claude-sonnet-4-6", max_tokens=2048):
    return SimpleNamespace(
        provider=provider, configured=configured, model=model,
        max_tokens=max_tokens, credential_env="SNOWFLAKE_PAT",
    )


class DiagnosticMainTests(unittest.TestCase):
    def run_main(self, argv, prov=None, client_cm=None):
        builder = mock.Mock()
        if client_cm is not None:
            builder.return_value = client_cm
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(diag, "load_settings") as ls, \
                mock.patch.object(
                    diag, "resolve_provider", return_value=prov), \
                mock.patch.object(diag, "_build_client", builder):
            import io
            buf = io.StringIO()
            with mock.patch.object(sys, "stdout", buf):
                rc = diag.main()
            return rc, buf.getvalue(), ls, builder

    def test_no_flag_returns_2_no_config_or_client(self):
        rc, out, ls, builder = self.run_main(
            ["live_snowflake_diagnostic.py"])
        self.assertEqual(rc, 2)
        self.assertIn("allow-provider-call", out)
        ls.assert_not_called()
        builder.assert_not_called()

    def test_non_snowflake_provider_returns_2(self):
        rc, _out, _ls, builder = self.run_main(
            ["x", "--allow-provider-call"], prov=_provider("openai"))
        self.assertEqual(rc, 2)
        builder.assert_not_called()

    def test_unconfigured_snowflake_returns_2(self):
        rc, _out, _ls, builder = self.run_main(
            ["x", "--allow-provider-call"],
            prov=_provider(configured=False))
        self.assertEqual(rc, 2)
        builder.assert_not_called()

    def test_valid_snowflake_request_kwargs_and_success(self):
        captured = {}

        def create(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="Cortex is working"))])

        client = SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=create)))
        cm = mock.MagicMock()
        cm.__enter__.return_value = client
        rc, out, _ls, _b = self.run_main(
            ["x", "--allow-provider-call"], prov=_provider(), client_cm=cm)
        self.assertEqual(rc, 0)
        self.assertIn("Live Cortex response", out)
        self.assertEqual(captured["model"], "claude-sonnet-4-6")
        self.assertEqual(captured["max_completion_tokens"], 2048)
        self.assertNotIn("max_tokens", captured)
        self.assertEqual(
            captured["messages"],
            [{"role": "user",
              "content": "Reply with exactly: Cortex is working"}],
        )

    def test_empty_response_returns_1(self):
        client = SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kw: SimpleNamespace(
                    choices=[SimpleNamespace(
                        message=SimpleNamespace(content=""))]))))
        cm = mock.MagicMock()
        cm.__enter__.return_value = client
        rc, out, _ls, _b = self.run_main(
            ["x", "--allow-provider-call"], prov=_provider(), client_cm=cm)
        self.assertEqual(rc, 1)
        self.assertIn("not confirmed", out)

    def test_error_output_sanitized(self):
        err = RuntimeError("request failed pat-secret-1")
        err.body = {"error": {
            "code": "bad_request",
            "message": ("denied pat-secret-1 eyJaa.bb.cc "
                        "Bearer opaque-9"),
        }}
        err.status_code = 400

        def create(**_kw):
            raise err

        client = SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=create)))
        cm = mock.MagicMock()
        cm.__enter__.return_value = client
        with mock.patch.dict(os.environ, {"SNOWFLAKE_PAT": "pat-secret-1"}):
            rc, out, _ls, _b = self.run_main(
                ["x", "--allow-provider-call"], prov=_provider(),
                client_cm=cm)
        self.assertEqual(rc, 1)
        self.assertIn("bad_request", out)
        for secret in ("pat-secret-1", "eyJaa.bb.cc", "opaque-9"):
            self.assertNotIn(secret, out)


class SafeErrorDetailTests(unittest.TestCase):
    def test_top_level_body_shape(self):
        exc = RuntimeError("x")
        exc.body = {"code": "123456",
                    "message": "default role does not match"}
        detail = diag.safe_error_detail(exc)
        self.assertEqual(detail["code"], "123456")
        self.assertIn("does not match", detail["message"])

    def test_non_dict_error_ignored(self):
        exc = RuntimeError("x")
        exc.body = {"error": "plain-string"}
        detail = diag.safe_error_detail(exc)
        self.assertEqual(set(detail), {"exception"})

    def test_opaque_exception_name_only(self):
        detail = diag.safe_error_detail(RuntimeError("SECRET"))
        self.assertEqual(detail, {"exception": "RuntimeError"})
        self.assertNotIn("SECRET", json.dumps(detail))


if __name__ == "__main__":
    unittest.main()
