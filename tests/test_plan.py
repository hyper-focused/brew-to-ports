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
        self.assertIn("uname -m", script)
        self.assertIn("x86_64", script)
        self.assertIn("port install wget", script)

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
