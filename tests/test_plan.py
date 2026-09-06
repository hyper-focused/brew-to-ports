import unittest

from brew_to_ports.cli import run_scan
from brew_to_ports.models import STATUS_EXCEPTION, STATUS_KEEP, STATUS_MIGRATE
from brew_to_ports.render.commands import render_commands
from brew_to_ports.render.script import render_script
from support import brew_payload, catalog, write_portindex_sample


class PlanSliceTests(unittest.TestCase):
    def setUp(self):
        self.plan = run_scan(
            brew_payload(),
            catalog(),
            arch="x86_64",
            macos="15.0",
            brew_pfx="/usr/local",
            ports_pfx="/opt/local",
            path_env="/usr/local/bin:/usr/bin",
            rc_files=[],
        )

    def test_vertical_slice_decisions(self):
        by_name = {d.brew_name: d for d in self.plan.decisions}
        self.assertEqual(by_name["wget"].status, STATUS_MIGRATE)
        self.assertEqual(by_name["visual-studio-code"].status, STATUS_KEEP)
        self.assertEqual(by_name["visual-studio-code"].category, "cask")
        self.assertEqual(by_name["local-foo"].status, STATUS_EXCEPTION)
        self.assertEqual(by_name["local-foo"].category, "tap")
        self.assertEqual(by_name["python@3.12"].status, STATUS_EXCEPTION)
        # git has no port → keep; openssl is a dep of git so it is pinned
        self.assertEqual(by_name["git"].status, STATUS_KEEP)
        self.assertIn("openssl@3", self.plan.keep_set)
        self.assertEqual(by_name["openssl@3"].status, STATUS_KEEP)
        self.assertIn("keep_because_dep_of_keeper", by_name["openssl@3"].reasons)

    def test_commands_include_wget_not_vscode(self):
        text = render_commands(self.plan)
        self.assertIn("sudo port install wget", text)
        self.assertNotIn("port install visual-studio-code", text)
        uninstalls = [op for op in self.plan.ops if op.action == "brew_uninstall"]
        names = [op.brew_name for op in uninstalls]
        self.assertIn("wget", names)
        self.assertNotIn("openssl@3", names)
        self.assertNotIn("git", names)

    def test_migrating_parent_does_not_pin_its_brew_dep(self):
        """A migrates; unrequested B was only a brew dep of A → B is leftover, not keep."""
        from brew_to_ports.models import Decision, KIND_FORMULA, Package
        from brew_to_ports.plan import build_plan

        wget = Package(
            name="wget",
            version="1.25.0",
            kind=KIND_FORMULA,
            origin="brew",
            requested=True,
            runtime_deps=["libfoo"],
        )
        libfoo = Package(
            name="libfoo",
            version="1.0",
            kind=KIND_FORMULA,
            origin="brew",
            requested=False,
            runtime_deps=[],
        )
        decisions = [
            Decision(brew_name="wget", status=STATUS_MIGRATE, match=None, reasons=[], requested=True),
            Decision(
                brew_name="libfoo",
                status=STATUS_KEEP,
                match=None,
                reasons=["no equivalent"],
                requested=False,
            ),
        ]
        # match needed for port_install
        from brew_to_ports.models import Match

        decisions[0].match = Match(
            brew_name="wget",
            port_name="wget",
            confidence="exact",
            rule_id="exact_name",
            version_delta="equal",
        )
        plan = build_plan(
            [wget, libfoo],
            decisions,
            arch="x86_64",
            macos="15",
            brew_prefix="/usr/local",
            ports_prefix="/opt/local",
        )
        self.assertNotIn("libfoo", plan.keep_set)
        uninstalls = [op.brew_name for op in plan.ops if op.action == "brew_uninstall"]
        self.assertIn("wget", uninstalls)
        self.assertIn("libfoo", uninstalls)
        self.assertEqual(uninstalls.index("wget") < uninstalls.index("libfoo"), True)

    def test_keeper_still_pins_shared_dep(self):
        from brew_to_ports.models import Decision, KIND_FORMULA, Match, Package
        from brew_to_ports.plan import build_plan

        wget = Package(
            name="wget", version="1", kind=KIND_FORMULA, origin="brew",
            requested=True, runtime_deps=["openssl@3"],
        )
        git = Package(
            name="git", version="1", kind=KIND_FORMULA, origin="brew",
            requested=True, runtime_deps=["openssl@3"],
        )
        ossl = Package(
            name="openssl@3", version="3", kind=KIND_FORMULA, origin="brew",
            requested=False, runtime_deps=[],
        )
        decisions = [
            Decision(
                brew_name="wget", status=STATUS_MIGRATE, requested=True, match=Match(
                    brew_name="wget", port_name="wget", confidence="exact",
                    rule_id="exact_name", version_delta="equal",
                ), reasons=[],
            ),
            Decision(brew_name="git", status=STATUS_KEEP, requested=True, match=None, reasons=["no equivalent"]),
            Decision(brew_name="openssl@3", status=STATUS_MIGRATE, requested=False, match=None, reasons=[]),
        ]
        plan = build_plan(
            [wget, git, ossl], decisions,
            arch="x86_64", macos="15", brew_prefix="/usr/local", ports_prefix="/opt/local",
        )
        self.assertIn("openssl@3", plan.keep_set)
        uninstalls = [op.brew_name for op in plan.ops if op.action == "brew_uninstall"]
        self.assertIn("wget", uninstalls)
        self.assertNotIn("openssl@3", uninstalls)
        self.assertNotIn("git", uninstalls)

    def test_cask_depends_on_pins_formula(self):
        from brew_to_ports.models import KIND_CASK, Decision, KIND_FORMULA, Match, Package
        from brew_to_ports.plan import build_plan

        cask = Package(
            name="gpg-suite",
            version="1",
            kind=KIND_CASK,
            origin="brew",
            requested=True,
            runtime_deps=["gnupg"],
        )
        gnupg = Package(
            name="gnupg",
            version="2",
            kind=KIND_FORMULA,
            origin="brew",
            requested=False,
            runtime_deps=[],
        )
        decisions = [
            Decision(brew_name="gpg-suite", status=STATUS_KEEP, requested=True, match=None, reasons=["cask"], kind=KIND_CASK),
            Decision(
                brew_name="gnupg",
                status=STATUS_MIGRATE,
                requested=False,
                match=Match(
                    brew_name="gnupg", port_name="gnupg", confidence="exact",
                    rule_id="exact_name", version_delta="equal",
                ),
                reasons=[],
            ),
        ]
        plan = build_plan(
            [cask, gnupg], decisions,
            arch="x86_64", macos="15", brew_prefix="/usr/local", ports_prefix="/opt/local",
        )
        self.assertIn("gnupg", plan.keep_set)
        uninstalls = [op.brew_name for op in plan.ops if op.action == "brew_uninstall"]
        self.assertNotIn("gnupg", uninstalls)

    def test_migrating_cask_emits_cask_uninstall(self):
        from brew_to_ports.models import KIND_CASK, Decision, Match, Package
        from brew_to_ports.plan import build_plan

        cask = Package(
            name="transmission",
            version="4",
            kind=KIND_CASK,
            origin="brew",
            requested=True,
            runtime_deps=[],
        )
        decisions = [
            Decision(
                brew_name="transmission",
                status=STATUS_MIGRATE,
                requested=True,
                kind=KIND_CASK,
                match=Match(
                    brew_name="transmission", port_name="transmission",
                    confidence="exact", rule_id="exact_name", version_delta="equal",
                ),
                reasons=[],
            ),
        ]
        plan = build_plan(
            [cask], decisions,
            arch="x86_64", macos="15", brew_prefix="/usr/local", ports_prefix="/opt/local",
        )
        uninstalls = [op for op in plan.ops if op.action == "brew_uninstall"]
        self.assertEqual(len(uninstalls), 1)
        self.assertEqual(uninstalls[0].kind, KIND_CASK)
        script = render_script(plan)
        self.assertIn("uninstall_brew transmission cask", script)

    def test_unrequested_migrate_is_not_a_port_install(self):
        """Regression: KIND_CASK must be imported; this line is skipped for requested formulae."""
        from brew_to_ports.classify import classify_all
        from brew_to_ports.inventory import from_brew_json
        from brew_to_ports.plan import build_plan

        payload = brew_payload()
        for f in payload["formulae"]:
            if f["name"] == "wget":
                f["installed"][0]["installed_on_request"] = False
        packages = from_brew_json(payload)
        decisions = classify_all(packages, catalog())
        plan = build_plan(
            packages,
            decisions,
            arch="x86_64",
            macos="15",
            brew_prefix="/usr/local",
            ports_prefix="/opt/local",
            catalog_source="fixture",
        )
        installs = [op.port_name for op in plan.ops if op.action == "port_install"]
        self.assertNotIn("wget", installs)

    def test_script_defaults_to_dry_run(self):
        script = render_script(self.plan)
        self.assertIn("APPLY=0", script)
        self.assertIn("DRY-RUN", script)
        self.assertIn("exec /bin/zsh", script)
        self.assertIn("/usr/bin/uname -m", script)
        self.assertIn("x86_64", script)
        self.assertIn("/usr/local/bin/brew", script)
        self.assertIn("/opt/local/bin/port", script)
        self.assertIn("install_port wget", script)
        self.assertIn("uninstall_brew wget", script)
        self.assertIn("stop_brew_service", script)
        self.assertIn("autoremove_brew", script)
        self.assertIn("already installed", script)

    def test_portindex_sample_roundtrip(self):
        path = write_portindex_sample()
        self.assertTrue(path.is_file())
        self.assertIn("wget", path.read_text(encoding="utf-8"))


class HostGateTests(unittest.TestCase):
    def test_apple_silicon_fails(self):
        from brew_to_ports.cli import require_intel

        with self.assertRaises(SystemExit) as ctx:
            require_intel("arm64")
        self.assertIn("Intel x86_64", str(ctx.exception))

    def test_intel_ok(self):
        from brew_to_ports.cli import require_intel

        self.assertEqual(require_intel("x86_64"), "x86_64")


if __name__ == "__main__":
    unittest.main()
