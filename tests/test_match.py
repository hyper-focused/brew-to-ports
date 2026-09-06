import unittest

from brew_to_ports.catalog import from_dicts
from brew_to_ports.match import compare_versions, match_package, parse_version, versioned_candidates
from brew_to_ports.models import DELTA_EQUAL, DELTA_OLDER_MAJOR, DELTA_OLDER_SAME_MAJOR, DELTA_PORT_NEWER, Package


class VersionTests(unittest.TestCase):
    def test_parse_strips_rebuild(self):
        self.assertEqual(parse_version("1.25.0_1"), (1, 25, 0))
        self.assertEqual(parse_version("v3.4.1"), (3, 4, 1))

    def test_compare(self):
        self.assertEqual(compare_versions("1.25.0", "1.25.0"), DELTA_EQUAL)
        self.assertEqual(compare_versions("1.24.0", "1.25.0"), DELTA_PORT_NEWER)
        self.assertEqual(compare_versions("1.25.0", "1.24.0"), DELTA_OLDER_SAME_MAJOR)
        self.assertEqual(compare_versions("2.0.0", "1.9.0"), DELTA_OLDER_MAJOR)

    def test_versioned_candidates(self):
        cands = versioned_candidates("python@3.12")
        self.assertIn("python312", cands)
        self.assertIn("python3.12", cands)
        self.assertIn("openssl3", versioned_candidates("openssl@3"))


class CascadeTests(unittest.TestCase):
    def setUp(self):
        self.catalog = from_dicts(
            [
                {"name": "wget", "version": "1.25.0", "homepage": "https://www.gnu.org/software/wget/"},
                {"name": "openssl3", "version": "3.4.1", "homepage": "https://www.openssl.org/"},
                {"name": "pkgconfig", "version": "0.29", "homepage": "https://pkgconfig.freedesktop.org/"},
                {"name": "foo-bar", "version": "1.0", "homepage": ""},
            ]
        )
        self.aliases = {"openssl@3": "openssl3", "pkgconf": "pkgconfig"}

    def test_exact_name(self):
        pkg = Package(name="wget", version="1.25.0", kind="formula", origin="brew")
        m = match_package(pkg, self.catalog, aliases=self.aliases)
        self.assertEqual(m.rule_id, "exact_name")
        self.assertEqual(m.port_name, "wget")

    def test_alias(self):
        pkg = Package(name="openssl@3", version="3.4.1", kind="formula", origin="brew")
        m = match_package(pkg, self.catalog, aliases=self.aliases)
        self.assertEqual(m.rule_id, "alias")
        self.assertEqual(m.port_name, "openssl3")

    def test_versioned_transform(self):
        catalog = from_dicts([{"name": "python312", "version": "3.12.8", "homepage": ""}])
        pkg = Package(name="python@3.12", version="3.12.8", kind="formula", origin="brew")
        m = match_package(pkg, catalog, aliases={})
        self.assertEqual(m.rule_id, "versioned_transform")
        self.assertEqual(m.port_name, "python312")

    def test_separator(self):
        pkg = Package(name="foo_bar", version="1.0", kind="formula", origin="brew")
        m = match_package(pkg, self.catalog, aliases={})
        self.assertEqual(m.rule_id, "separator")
        self.assertEqual(m.port_name, "foo-bar")

    def test_homepage(self):
        pkg = Package(
            name="wget-custom",
            version="1.25.0",
            kind="formula",
            origin="brew",
            homepage="https://www.gnu.org/software/wget/",
        )
        m = match_package(pkg, self.catalog, aliases={})
        self.assertEqual(m.rule_id, "homepage")
        self.assertEqual(m.port_name, "wget")

    def test_no_match(self):
        pkg = Package(name="definitely-not-a-port", version="1.0", kind="formula", origin="brew")
        m = match_package(pkg, self.catalog, aliases={})
        self.assertEqual(m.rule_id, "no_match")
        self.assertIsNone(m.port_name)


if __name__ == "__main__":
    unittest.main()
