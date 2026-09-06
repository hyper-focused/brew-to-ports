import unittest

from brew_to_ports.classify import classify_one
from brew_to_ports.models import Package, STATUS_EXCEPTION, STATUS_KEEP, STATUS_MIGRATE
from support import catalog


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.catalog = catalog()
        self.aliases = {"openssl@3": "openssl3", "python@3.12": "python312"}

    def test_wget_migrates(self):
        pkg = Package(
            name="wget",
            version="1.25.0",
            kind="formula",
            origin="brew",
            tap="homebrew/core",
            requested=True,
            bottle=True,
        )
        d = classify_one(pkg, self.catalog, aliases=self.aliases)
        self.assertEqual(d.status, STATUS_MIGRATE)
        self.assertEqual(d.match.port_name, "wget")

    def test_cask_stays(self):
        pkg = Package(
            name="visual-studio-code",
            version="1.96.0",
            kind="cask",
            origin="brew",
            tap="homebrew/cask",
            requested=True,
        )
        d = classify_one(pkg, self.catalog, aliases=self.aliases)
        self.assertEqual(d.status, STATUS_KEEP)
        self.assertEqual(d.category, "cask")

    def test_tap_is_exception(self):
        pkg = Package(
            name="local-foo",
            version="0.1.0",
            kind="formula",
            origin="brew",
            tap="local/tap",
            requested=True,
        )
        d = classify_one(pkg, self.catalog, aliases=self.aliases)
        self.assertEqual(d.status, STATUS_EXCEPTION)
        self.assertEqual(d.category, "tap")

    def test_python_runtime_exception_even_if_port_exists(self):
        pkg = Package(
            name="python@3.12",
            version="3.12.8",
            kind="formula",
            origin="brew",
            tap="homebrew/core",
            requested=True,
        )
        d = classify_one(pkg, self.catalog, aliases=self.aliases)
        self.assertEqual(d.status, STATUS_EXCEPTION)
        self.assertEqual(d.category, "runtime")
        self.assertEqual(d.match.port_name, "python312")

    def test_older_same_major_keep_by_default(self):
        pkg = Package(
            name="jq",
            version="1.8.0",
            kind="formula",
            origin="brew",
            tap="homebrew/core",
            requested=True,
        )
        d = classify_one(pkg, self.catalog, aliases=self.aliases)
        self.assertEqual(d.status, STATUS_KEEP)
        d2 = classify_one(pkg, self.catalog, aliases=self.aliases, allow_older_same_major=True)
        self.assertEqual(d2.status, STATUS_MIGRATE)

    def test_older_major_exception(self):
        pkg = Package(
            name="jq",
            version="2.0.0",
            kind="formula",
            origin="brew",
            tap="homebrew/core",
            requested=True,
        )
        d = classify_one(pkg, self.catalog, aliases=self.aliases)
        self.assertEqual(d.status, STATUS_EXCEPTION)


if __name__ == "__main__":
    unittest.main()
