import io
import unittest

from brew_to_ports.cutover import CutoverAbort, decide_cutover
from brew_to_ports.family import RuntimeFamily, cutover_families, python_families
from brew_to_ports.models import (
    CUTOVER_MIGRATE,
    CUTOVER_SKIP,
    KIND_FORMULA,
    STATUS_DROP,
    STATUS_EXCEPTION,
    STATUS_KEEP,
    STATUS_MIGRATE,
    Decision,
    Match,
    Package,
)
from brew_to_ports.plan import build_plan


def _pkg(name, requested=True, deps=None):
    return Package(
        name=name,
        version="1.0",
        kind=KIND_FORMULA,
        origin="brew",
        requested=requested,
        runtime_deps=list(deps or []),
        tap="homebrew/core",
    )


def _dec(name, status, category="", requested=True, port=None, delta="equal", hold=False):
    match = None
    if port:
        match = Match(
            brew_name=name,
            port_name=port,
            confidence="exact",
            rule_id="exact_name",
            version_delta=delta,
            brew_version="1.0",
            port_version="1.0",
        )
    elif status in (STATUS_KEEP,) and category == "no_equivalent":
        match = Match(
            brew_name=name,
            port_name=None,
            confidence="none",
            rule_id="no_match",
            version_delta="n/a",
        )
    return Decision(
        brew_name=name,
        status=status,
        match=match,
        reasons=[],
        category=category,
        requested=requested,
        kind=KIND_FORMULA,
        hold_uninstall=hold,
    )


class CutoverPromptTests(unittest.TestCase):
    def test_noninteractive_skips_by_default(self):
        fam = RuntimeFamily(runtime="python@3.13", can=["pytest"], drop=["python-yq"])
        choices = decide_cutover([fam], interactive=False)
        self.assertEqual(choices[0].action, CUTOVER_SKIP)

    def test_flag_requires_drop_ack(self):
        fam = RuntimeFamily(runtime="python@3.13", can=["pytest"], drop=["python-yq"])
        choices = decide_cutover([fam], migrate_runtime=["python@3.13"], interactive=False)
        self.assertEqual(choices[0].action, CUTOVER_SKIP)
        choices = decide_cutover(
            [fam],
            migrate_runtime=["python@3.13"],
            acked_drop=["python@3.13"],
            interactive=False,
        )
        self.assertEqual(choices[0].action, CUTOVER_MIGRATE)

    def test_prompt_m_yes(self):
        fam = RuntimeFamily(runtime="python@3.13", can=["pytest"], drop=["python-yq"])
        stdin = io.StringIO("m\nyes\n")
        err = io.StringIO()
        choices = decide_cutover([fam], interactive=True, stdin=stdin, stderr=err)
        self.assertEqual(choices[0].action, CUTOVER_MIGRATE)

    def test_prompt_y_then_skip(self):
        fam = RuntimeFamily(runtime="python@3.13", drop=["python-yq"])
        stdin = io.StringIO("m\ny\nn\n")
        err = io.StringIO()
        choices = decide_cutover([fam], interactive=True, stdin=stdin, stderr=err)
        self.assertEqual(choices[0].action, CUTOVER_SKIP)
        self.assertIn("skipping python@3.13", err.getvalue())

    def test_quit_aborts(self):
        fam = RuntimeFamily(runtime="python@3.13")
        stdin = io.StringIO("q\n")
        err = io.StringIO()
        with self.assertRaises(CutoverAbort):
            decide_cutover([fam], interactive=True, stdin=stdin, stderr=err)


class CutoverPlanTests(unittest.TestCase):
    def test_python_cutover_drops_unmatched_child(self):
        packages = [
            _pkg("python@3.13", deps=[]),
            _pkg("pytest", deps=["python@3.13"]),
            _pkg("python-yq", deps=["python@3.13"]),
        ]
        decisions = [
            _dec("python@3.13", STATUS_EXCEPTION, category="runtime", port="python313"),
            _dec("pytest", STATUS_MIGRATE, port="py313-pytest"),
            _dec("python-yq", STATUS_KEEP, category="no_equivalent"),
        ]
        from brew_to_ports.models import CutoverChoice

        plan = build_plan(
            packages,
            decisions,
            arch="x86_64",
            macos="15",
            brew_prefix="/usr/local",
            ports_prefix="/opt/local",
            cutover=[
                CutoverChoice(
                    runtime="python@3.13",
                    action=CUTOVER_MIGRATE,
                    can=["pytest"],
                    drop=["python-yq"],
                )
            ],
        )
        by = {d.brew_name: d for d in plan.decisions}
        self.assertEqual(by["python@3.13"].status, STATUS_MIGRATE)
        self.assertEqual(by["python-yq"].status, STATUS_DROP)
        self.assertNotIn("python@3.13", plan.keep_set)
        uninstalls = [op.brew_name for op in plan.ops if op.action == "brew_uninstall"]
        self.assertIn("python-yq", uninstalls)
        installs = [op.port_name for op in plan.ops if op.action == "port_install"]
        self.assertIn("python313", installs)

    def test_preflight_skips_if_cask_pins_runtime(self):
        from brew_to_ports.models import KIND_CASK, CutoverChoice

        packages = [
            _pkg("python@3.13"),
            Package(
                name="some-cask",
                version="1",
                kind=KIND_CASK,
                origin="brew",
                requested=True,
                runtime_deps=["python@3.13"],
            ),
        ]
        decisions = [
            _dec("python@3.13", STATUS_EXCEPTION, category="runtime", port="python313"),
            Decision(
                brew_name="some-cask",
                status=STATUS_KEEP,
                match=None,
                reasons=["cask"],
                category="cask",
                requested=True,
                kind=KIND_CASK,
            ),
        ]
        plan = build_plan(
            packages,
            decisions,
            arch="x86_64",
            macos="15",
            brew_prefix="/usr/local",
            ports_prefix="/opt/local",
            cutover=[
                CutoverChoice(runtime="python@3.13", action=CUTOVER_MIGRATE, drop=[], can=[])
            ],
        )
        by = {d.brew_name: d for d in plan.decisions}
        self.assertEqual(by["python@3.13"].status, STATUS_EXCEPTION)
        self.assertEqual(plan.cutover[0].action, CUTOVER_SKIP)
        self.assertIn("python@3.13", plan.keep_set)

    def test_families_python_php_node_not_ruby(self):
        packages = [
            _pkg("python@3.13"),
            _pkg("php"),
            _pkg("node@22"),
            _pkg("ruby"),
            _pkg("pytest", deps=["python@3.13"]),
        ]
        decisions = [
            _dec("python@3.13", STATUS_EXCEPTION, category="runtime", port="python313"),
            _dec("php", STATUS_EXCEPTION, category="runtime", port="php", delta="port_older_same_major"),
            _dec("node@22", STATUS_EXCEPTION, category="runtime", port="nodejs22", delta="port_older_same_major"),
            _dec("ruby", STATUS_EXCEPTION, category="runtime", port="ruby", delta="port_older_major"),
            _dec("pytest", STATUS_MIGRATE, port="py313-pytest"),
        ]
        self.assertEqual([f.runtime for f in python_families(packages, decisions)], ["python@3.13"])
        without = cutover_families(packages, decisions)
        self.assertEqual([f.runtime for f in without], ["python@3.13"])
        with_flag = cutover_families(packages, decisions, allow_older_same_major=True)
        self.assertEqual([f.runtime for f in with_flag], ["python@3.13", "php", "node@22"])

    def test_php_cutover_keeps_hold(self):
        from brew_to_ports.models import CutoverChoice

        packages = [_pkg("php"), _pkg("prettier", deps=["php"])]
        decisions = [
            _dec("php", STATUS_EXCEPTION, category="runtime", port="php", hold=True),
            _dec("prettier", STATUS_KEEP, category="no_equivalent"),
        ]
        plan = build_plan(
            packages,
            decisions,
            arch="x86_64",
            macos="15",
            brew_prefix="/usr/local",
            ports_prefix="/opt/local",
            cutover=[
                CutoverChoice(
                    runtime="php",
                    action=CUTOVER_MIGRATE,
                    can=[],
                    drop=["prettier"],
                )
            ],
        )
        by = {d.brew_name: d for d in plan.decisions}
        self.assertEqual(by["php"].status, STATUS_MIGRATE)
        self.assertTrue(by["php"].hold_uninstall)
        self.assertEqual(by["prettier"].status, STATUS_DROP)
