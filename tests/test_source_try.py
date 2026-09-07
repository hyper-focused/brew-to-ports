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

    def test_mysql_family_never_gets_an_overlay(self):
        for name in ("mysql", "mysql-client", "mariadb", "percona"):
            rec = recipe_for(
                _pkg(
                    name=name,
                    source_url="https://github.com/mysql/mysql-server/archive/refs/tags/8.4.0.tar.gz",
                )
            )
            self.assertIsNone(rec, name)

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


class PlanTrySourceTests(unittest.TestCase):
    def _keep_decision(self, name):
        from brew_to_ports.models import Decision, STATUS_KEEP

        return Decision(
            brew_name=name,
            status=STATUS_KEEP,
            match=None,
            reasons=["no equivalent above match threshold"],
            category="no_equivalent",
            requested=True,
        )

    def test_source_built_unmatched_gets_overlay(self):
        from brew_to_ports.models import STATUS_MIGRATE
        from brew_to_ports.plan import build_plan

        pkg = _pkg(
            name="pyenv",
            bottle=False,
            source_url="https://github.com/pyenv/pyenv/archive/refs/tags/v2.8.5.tar.gz",
            sha256="abc123",
        )
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_plan(
                [pkg],
                [self._keep_decision("pyenv")],
                arch="x86_64",
                macos="15",
                brew_prefix="/usr/local",
                ports_prefix="/opt/local",
                try_source_root=Path(tmp),
            )
        by = {d.brew_name: d for d in plan.decisions}
        self.assertEqual(by["pyenv"].status, STATUS_MIGRATE)
        self.assertEqual(by["pyenv"].category, "try_source")
        self.assertTrue(any(op.action == "try_source" for op in plan.ops))

    def test_bottled_unmatched_stays_on_brew(self):
        from brew_to_ports.models import STATUS_KEEP
        from brew_to_ports.plan import build_plan

        pkg = _pkg(
            name="pyenv",
            bottle=True,
            source_url="https://github.com/pyenv/pyenv/archive/refs/tags/v2.8.5.tar.gz",
            sha256="abc123",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = build_plan(
                [pkg],
                [self._keep_decision("pyenv")],
                arch="x86_64",
                macos="15",
                brew_prefix="/usr/local",
                ports_prefix="/opt/local",
                try_source_root=root,
            )
            by = {d.brew_name: d for d in plan.decisions}
            self.assertEqual(by["pyenv"].status, STATUS_KEEP)
            self.assertFalse(any(op.action == "try_source" for op in plan.ops))
            self.assertEqual(list(root.rglob("Portfile")), [])

    def test_allow_try_source_alias(self):
        from brew_to_ports.cli import build_parser

        args = build_parser().parse_args(["--allow-try-source"])
        self.assertEqual(args.try_source, "DEFAULT")
        args = build_parser().parse_args(["--try-source", "/tmp/overlay"])
        self.assertEqual(args.try_source, "/tmp/overlay")
