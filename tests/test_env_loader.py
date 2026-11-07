"""Env loading and provider status: whitelisted keys, process env wins."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from smart_librarian.settings import (
    load_dotenv,
    load_settings,
    provider_status,
)

SECRET = "sk-test-secret-value-123"


class EnvLoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / ".env"
        self.env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self.env_patch.start()
        for key in ("OPENAI_API_KEY", "AITTA_API_TOKEN",
                    "FEATHERLESS_API_KEY", "SNOWFLAKE_ACCOUNT_HOST",
                    "SNOWFLAKE_PAT", "LLM_PROVIDER",
                    "LLM_MODEL", "DEMO_DATA_DIR", "RUNTIME_DB_PATH"):
            os.environ.pop(key, None)
        # Point the default .env lookup at the empty temp dir so a real
        # repo .env can never leak into these tests.
        import smart_librarian.settings as settings_module

        self.root_patch = mock.patch.object(
            settings_module, "REPO_ROOT", Path(self.temp.name)
        )
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.env_patch.stop()
        self.temp.cleanup()

    def write(self, text):
        self.path.write_text(text, encoding="utf-8")
        return self.path

    def test_loads_allowed_keys_only(self):
        self.write(
            "OPENAI_API_KEY=abc\n"
            "LLM_MODEL=gpt-test\n"
            "DEMO_DATA_DIR=data/demo_v1\n"
            "RUNTIME_DB_PATH=var/x.sqlite\n"
            "EVIL_KEY=should-not-load\n"
            "PATH=/tmp/evil\n"
        )
        loaded = load_dotenv(self.path)
        self.assertEqual(os.environ["LLM_MODEL"], "gpt-test")
        self.assertNotIn("EVIL_KEY", loaded)
        self.assertNotIn("PATH", loaded)
        self.assertNotIn("EVIL_KEY", os.environ)

    def test_process_env_wins(self):
        os.environ["LLM_MODEL"] = "from-process"
        self.write("LLM_MODEL=from-file\n")
        load_dotenv(self.path)
        self.assertEqual(os.environ["LLM_MODEL"], "from-process")

    def test_quotes_and_export_prefix(self):
        self.write(
            'export LLM_MODEL="quoted model"\n'
            "DEMO_DATA_DIR='data/demo_v1'\n"
            "# a comment\n"
            "not a line at all\n"
        )
        load_dotenv(self.path)
        self.assertEqual(os.environ["LLM_MODEL"], "quoted model")
        self.assertEqual(os.environ["DEMO_DATA_DIR"], "data/demo_v1")

    def test_missing_file_is_noop(self):
        self.assertEqual(load_dotenv(self.path), set())

    def test_no_secret_in_returned_names_or_output(self):
        self.write(f"OPENAI_API_KEY={SECRET}\n")
        loaded = load_dotenv(self.path)
        # Only key names come back; values stay inside os.environ.
        self.assertEqual(loaded, {"OPENAI_API_KEY"})
        self.assertNotIn(SECRET, str(loaded))
        self.assertEqual(os.environ["OPENAI_API_KEY"], SECRET)
        status = provider_status()
        rendered = str(status)
        self.assertNotIn(SECRET, rendered)
        self.assertTrue(status["configured"])
        self.assertIsInstance(status["model"], str)

    def test_settings_paths_and_precedence(self):
        load_dotenv(self.write(
            "DEMO_DATA_DIR=custom_demo\n"
            "RUNTIME_DB_PATH=custom.sqlite\n"
        ))
        settings = load_settings()
        self.assertTrue(settings.demo_dir.as_posix().endswith("custom_demo"))
        self.assertTrue(settings.runtime_db.as_posix().endswith("custom.sqlite"))
        os.environ["DEMO_DATA_DIR"] = "env_demo"
        settings = load_settings()
        self.assertTrue(settings.demo_dir.as_posix().endswith("env_demo"))
        # Absolute paths are respected.
        os.environ["RUNTIME_DB_PATH"] = str(self.path)
        settings = load_settings()
        self.assertEqual(settings.runtime_db, self.path.resolve())

    def test_provider_status_unconfigured(self):
        status = provider_status()
        self.assertFalse(status["configured"])
        self.assertIn("model", status)

    def test_snowflake_keys_loaded_and_process_env_wins(self):
        self.write(
            "LLM_PROVIDER=snowflake\n"
            "SNOWFLAKE_ACCOUNT_HOST=myorg-myacct.snowflakecomputing.com\n"
            f"SNOWFLAKE_PAT={SECRET}\n"
        )
        loaded = load_dotenv(self.path)
        self.assertIn("SNOWFLAKE_ACCOUNT_HOST", loaded)
        self.assertIn("SNOWFLAKE_PAT", loaded)
        self.assertNotIn(SECRET, str(loaded))
        status = provider_status()
        self.assertEqual(status["provider"], "snowflake")
        self.assertTrue(status["configured"])
        self.assertNotIn(SECRET, str(status))
        # Process env wins over the file.
        os.environ["SNOWFLAKE_ACCOUNT_HOST"] = (
            "otherorg-otheracct.snowflakecomputing.com"
        )
        self.write(
            "SNOWFLAKE_ACCOUNT_HOST=myorg-myacct.snowflakecomputing.com\n"
        )
        load_dotenv(self.path)
        self.assertEqual(
            os.environ["SNOWFLAKE_ACCOUNT_HOST"],
            "otherorg-otheracct.snowflakecomputing.com",
        )


if __name__ == "__main__":
    unittest.main()
