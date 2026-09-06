import tempfile
import unittest
from pathlib import Path

from brew_to_ports.models import KIND_FORMULA, Package
from brew_to_ports.source_try import (
    SHAPE_AUTORECONF,
    SHAPE_GITHUB_NOARCH,
    SHAPE_GOLANG,
    recipe_for,
    write_overlay,
)


def _pkg(**kwargs):
    base = dict(
        name="x",
        version="1",
        kind=KIND_FORMULA,
        origin="brew",
        requested=True,
        source_url="",
        sha256="abc",
        license="MIT",
        build_deps=[],
        description="d",
    )
    base.update(kwargs)
    return Package(**base)


class RecipeTests(unittest.TestCase):
    def test_pyenv_github_noarch(self):
        rec = recipe_for(
            _pkg(
                name="pyenv",
                source_url="https://github.com/pyenv/pyenv/archive/refs/tags/v2.8.5.tar.gz",
                sha256="deadbeef",
            )
        )
        self.assertIsNotNone(rec)
        self.assertEqual(rec.shape, SHAPE_GITHUB_NOARCH)
        self.assertIn("github.setup        pyenv pyenv 2.8.5 v", rec.portfile)

    def test_chroma_golang(self):
        rec = recipe_for(
            _pkg(
                name="chroma",
                source_url="https://github.com/alecthomas/chroma/archive/refs/tags/v2.27.0.tar.gz",
                build_deps=["go"],
            )
        )
        self.assertEqual(rec.shape, SHAPE_GOLANG)
        self.assertIn("go.setup            github.com/alecthomas/chroma 2.27.0 v", rec.portfile)

    def test_bgpq4_autoreconf(self):
        rec = recipe_for(
            _pkg(
                name="bgpq4",
                source_url="https://github.com/bgp/bgpq4/archive/refs/tags/1.16.tar.gz",
                build_deps=["autoconf", "automake", "libtool"],
            )
        )
        self.assertEqual(rec.shape, SHAPE_AUTORECONF)
        self.assertIn("use_autoreconf      yes", rec.portfile)

    def test_cmake_skipped(self):
        rec = recipe_for(
            _pkg(
                name="quick-lint-js",
                source_url="https://github.com/quick-lint/quick-lint-js/archive/refs/tags/3.2.0.tar.gz",
                build_deps=["cmake"],
            )
        )
        self.assertIsNone(rec)

    def test_pypi_skipped(self):
        rec = recipe_for(
            _pkg(
                name="pydantic",
                source_url="https://files.pythonhosted.org/packages/xx/pydantic-2.13.5.tar.gz",
                build_deps=["rust"],
            )
        )
        self.assertIsNone(rec)

    def test_write_overlay(self):
        pkg = _pkg(
            name="pyenv",
            source_url="https://github.com/pyenv/pyenv/archive/refs/tags/v2.8.5.tar.gz",
            sha256="abc123",
        )
        with tempfile.TemporaryDirectory() as tmp:
            dest = write_overlay(pkg, Path(tmp))
            self.assertTrue((dest / "Portfile").is_file())
            self.assertIn("pyenv", dest.parts)
