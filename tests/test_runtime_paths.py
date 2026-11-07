"""Configuration guard tests: the runtime DB must never open inside the
read-only demo fixture directory."""

import unittest
from pathlib import Path

from smart_librarian.api.app import ConfigurationError, create_app

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "demo_v1"


class RuntimePathTests(unittest.TestCase):
    def test_runtime_db_inside_demo_dir_refused(self):
        with self.assertRaises(ConfigurationError):
            create_app(demo_dir=DEMO, runtime_db=DEMO / "runtime.sqlite")

    def test_runtime_db_equal_to_fixture_db_refused(self):
        with self.assertRaises(ConfigurationError):
            create_app(demo_dir=DEMO, runtime_db=DEMO / "demo.sqlite")

    def test_runtime_db_outside_demo_dir_accepted(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp:
            app = create_app(demo_dir=DEMO,
                             runtime_db=Path(temp) / "runtime.sqlite")
            self.assertIsNotNone(app)

    def test_runtime_db_inside_any_domain_fixture_refused(self):
        for domain_dir in (
            ROOT / "data" / "demo_logistics_v1",
            ROOT / "data" / "demo_quality_v1",
        ):
            if not domain_dir.exists():
                continue
            before = (domain_dir / "catalog.json").read_bytes()
            for target in (domain_dir / "demo.sqlite",
                           domain_dir / "nested" / "runtime.sqlite"):
                with self.assertRaises(ConfigurationError, msg=str(target)):
                    create_app(demo_dir=DEMO, runtime_db=target)
            # Validation happens before any store is opened or written.
            self.assertEqual(
                before, (domain_dir / "catalog.json").read_bytes()
            )
            self.assertFalse((domain_dir / "nested").exists())


if __name__ == "__main__":
    unittest.main()
