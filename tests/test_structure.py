"""Structural smoke tests for the Smart Librarian scaffold.

Stdlib-only: verifies the package skeleton imports without third-party
dependencies and that expected data/fixture paths exist. This is structural
verification, not a business evaluation harness.
"""

import importlib
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NAMESPACES = [
    "smart_librarian",
    "smart_librarian.api",
    "smart_librarian.catalog",
    "smart_librarian.domain",
    "smart_librarian.workflow",
    "smart_librarian.llm",
    "smart_librarian.reporting",
    "smart_librarian.persistence",
]


def _root(*parts):
    return os.path.join(ROOT, *parts)


class PackageStructureTests(unittest.TestCase):
    def test_namespaces_import_without_third_party(self):
        for name in NAMESPACES:
            with self.subTest(namespace=name):
                importlib.import_module(name)

    def test_version(self):
        import smart_librarian

        self.assertEqual(smart_librarian.__version__, "0.1.0")


class DataPathTests(unittest.TestCase):
    def test_demo_fixture_paths_exist(self):
        for rel in (
            ("data", "demo_v1", "catalog.json"),
            ("data", "demo_v1", "demo.sqlite"),
        ):
            with self.subTest(path=os.path.join(*rel)):
                self.assertTrue(os.path.isfile(_root(*rel)))

    def test_source_workbook_exists(self):
        workbooks = [
            name
            for name in os.listdir(_root("data"))
            if name.lower().endswith((".xlsx", ".xlsm", ".xls"))
        ]
        self.assertTrue(workbooks, "no source workbook found under data/")
        for name in workbooks:
            with self.subTest(workbook=name):
                self.assertTrue(os.path.isfile(_root("data", name)))

    def test_scenario_fixture_exists_and_outside_demo_data(self):
        fixture = _root("tests", "fixtures", "demo_scenarios.json")
        self.assertTrue(os.path.isfile(fixture))
        demo_dir = os.path.realpath(_root("data", "demo_v1"))
        self.assertFalse(os.path.realpath(fixture).startswith(demo_dir + os.sep))


class ConfigPlaceholderTests(unittest.TestCase):
    def test_env_example_has_blank_key(self):
        example = _root(".env.example")
        self.assertTrue(os.path.isfile(example))
        with open(example, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertIn("OPENAI_API_KEY=", lines)


if __name__ == "__main__":
    unittest.main()
