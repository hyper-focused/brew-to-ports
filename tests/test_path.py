import tempfile
import unittest
from pathlib import Path

from brew_to_ports.config_scan import scan_configs
from brew_to_ports.models import Decision, Package, STATUS_MIGRATE
from brew_to_ports.path_suggest import snippet, suggest_path


class PathTests(unittest.TestCase):
    def test_macports_first(self):
        advice = suggest_path(
            "/usr/local/bin:/usr/bin:/bin",
            rc_files=[],
            brew_prefix="/usr/local",
            ports_prefix="/opt/local",
        )
        parts = advice.suggested.split(":")
        self.assertEqual(parts[0], "/opt/local/bin")
        self.assertEqual(parts[1], "/opt/local/sbin")
        self.assertIn("/usr/local/bin", parts)
        self.assertGreater(parts.index("/usr/local/bin"), parts.index("/opt/local/bin"))
        self.assertNotIn("/opt/local/bin/", parts)
        text = snippet(advice)
        self.assertIn("brew-to-ports:", text)
        self.assertIn("export PATH=", text)

    def test_rc_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            zshrc = Path(tmp) / ".zshrc"
            zshrc.write_text('export PATH="/usr/local/bin:$PATH"\n', encoding="utf-8")
            advice = suggest_path("/usr/bin", rc_files=[(zshrc, zshrc.read_text())])
            self.assertEqual(advice.rc_hits, [str(zshrc)])

    def test_follows_zsh_path_include(self):
        from brew_to_ports.adapters.shell_env import read_rc_files

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            zsh_path = home / ".zsh_path"
            zsh_path.write_text('export PATH="/usr/local/bin:$PATH"\n', encoding="utf-8")
            (home / ".zshrc").write_text(
                '[[ -f ~/.zsh_path ]] && source ~/.zsh_path\n',
                encoding="utf-8",
            )
            files = read_rc_files(home=home)
            names = [p.name for p, _ in files]
            self.assertIn(".zshrc", names)
            self.assertIn(".zsh_path", names)
            advice = suggest_path("/usr/bin", rc_files=files)
            self.assertTrue(any(p.endswith(".zsh_path") for p in advice.rc_hits))
            self.assertTrue(any("zsh_path" in n for n in advice.notes))

    def test_strips_trailing_slash_dupes(self):
        advice = suggest_path(
            "/opt/local/bin/:/usr/local/bin:/usr/bin",
            rc_files=[],
            brew_prefix="/usr/local",
            ports_prefix="/opt/local",
        )
        parts = advice.suggested.split(":")
        self.assertEqual(parts.count("/opt/local/bin"), 1)
        self.assertNotIn("/opt/local/bin/", parts)


class ConfigScanTests(unittest.TestCase):
    def test_finds_conf_and_never_copy_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            conf = prefix / "etc" / "nginx.conf"
            conf.parent.mkdir(parents=True)
            conf.write_text("pid /usr/local/var/run/nginx.pid;\n", encoding="utf-8")
            pkg = Package(name="nginx", version="1.26", kind="formula", origin="brew", requested=True)
            decision = Decision(
                brew_name="nginx",
                status=STATUS_MIGRATE,
                match=None,
                reasons=[],
                hold_uninstall=True,
                requested=True,
            )
            findings = scan_configs([pkg], [decision], str(prefix), "/opt/local")
            self.assertTrue(findings)
            self.assertTrue(any(f.contains_brew_paths for f in findings))
            self.assertTrue(all(f.copy_safe is False for f in findings))

    def test_script_holds_stateful_uninstall(self):
        from brew_to_ports.models import Match, Plan, PlanOp
        from brew_to_ports.render.script import render_script

        plan = Plan(
            arch="x86_64",
            macos="15",
            brew_prefix="/usr/local",
            ports_prefix="/opt/local",
            ops=[
                PlanOp(action="port_install", brew_name="nginx", port_name="nginx", hold_uninstall=True),
                PlanOp(action="brew_uninstall", brew_name="nginx", port_name="nginx", hold_uninstall=True),
            ],
        )
        script = render_script(plan)
        self.assertIn("--i-acked-config", script)
        self.assertIn("HOLD:", script)


if __name__ == "__main__":
    unittest.main()
