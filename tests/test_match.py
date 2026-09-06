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
        self.assertIn("nodejs22", versioned_candidates("node@22"))
        self.assertIn("php85", versioned_candidates("php@8.5"))


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

    def test_node_at_to_nodejs(self):
        catalog = from_dicts([{"name": "nodejs22", "version": "22.22.2", "homepage": ""}])
        pkg = Package(name="node@22", version="22.22.2", kind="formula", origin="brew")
        m = match_package(pkg, catalog, aliases={})
        self.assertEqual(m.port_name, "nodejs22")
        self.assertIn(m.rule_id, ("versioned_transform", "stem_transform"))

    def test_python_prefix_to_py_series(self):
        catalog = from_dicts(
            [
                {"name": "py-matplotlib", "version": "3.11.1", "homepage": "https://matplotlib.org/"},
                {"name": "py313-matplotlib", "version": "3.11.1", "homepage": "https://matplotlib.org/"},
                {"name": "py314-matplotlib", "version": "3.11.1", "homepage": "https://matplotlib.org/"},
            ]
        )
        pkg = Package(
            name="python-matplotlib",
            version="3.11.1",
            kind="formula",
            origin="brew",
            homepage="https://matplotlib.org/",
            runtime_deps=["python@3.14", "freetype"],
        )
        m = match_package(pkg, catalog, aliases={})
        self.assertEqual(m.port_name, "py314-matplotlib")

    def test_python_yq_does_not_map_to_yq_or_pyqt(self):
        catalog = from_dicts(
            [
                {"name": "yq", "version": "4.53.6", "homepage": "https://github.com/mikefarah/yq"},
                {"name": "py-pyqt4", "version": "4.12.1", "homepage": "https://www.riverbankcomputing.com/software/pyqt/intro"},
            ]
        )
        pkg = Package(
            name="python-yq",
            version="4.1.2",
            kind="formula",
            origin="brew",
            homepage="https://kislyuk.github.io/yq/",
            runtime_deps=["python@3.14", "libyaml"],
        )
        m = match_package(pkg, catalog, aliases={})
        self.assertIsNone(m.port_name)

    def test_ffmpeg_full_picks_devel_same_version(self):
        catalog = from_dicts(
            [
                {"name": "cws2fws", "version": "0", "homepage": "https://ffmpeg.org/"},
                {"name": "ffmpeg", "version": "8.1.2", "homepage": "https://ffmpeg.org/"},
                {"name": "ffmpeg-devel", "version": "9.0.1", "homepage": "https://ffmpeg.org/"},
                {"name": "ffmpeg8", "version": "8.1.2", "homepage": "https://ffmpeg.org/"},
            ]
        )
        pkg = Package(
            name="ffmpeg-full",
            version="9.0.1",
            kind="formula",
            origin="brew",
            homepage="https://ffmpeg.org/",
        )
        m = match_package(pkg, catalog, aliases={})
        self.assertEqual(m.port_name, "ffmpeg-devel")
        self.assertIn(m.rule_id, ("stem_transform", "homepage_family"))

    def test_scipy_py_family(self):
        catalog = from_dicts(
            [
                {"name": "py-scipy", "version": "1.18.1", "homepage": "https://www.scipy.org/"},
                {"name": "py313-scipy", "version": "1.18.1", "homepage": "https://www.scipy.org/"},
                {"name": "py314-scipy", "version": "1.18.1", "homepage": "https://www.scipy.org/"},
            ]
        )
        pkg = Package(
            name="scipy",
            version="1.18.1",
            kind="formula",
            origin="brew",
            homepage="https://www.scipy.org/",
            runtime_deps=["openblas"],
        )
        m = match_package(pkg, catalog, aliases={})
        self.assertIn(m.port_name, ("py-scipy", "py314-scipy", "py313-scipy"))
        self.assertEqual(m.rule_id, "homepage_family")

    def test_python_module_stem_from_dep(self):
        catalog = from_dicts([{"name": "py314-pygments", "version": "2.21.0", "homepage": ""}])
        pkg = Package(
            name="pygments",
            version="2.21.0",
            kind="formula",
            origin="brew",
            runtime_deps=["python@3.14"],
        )
        m = match_package(pkg, catalog, aliases={})
        self.assertEqual(m.port_name, "py314-pygments")
        self.assertEqual(m.rule_id, "stem_transform")


if __name__ == "__main__":
    unittest.main()
