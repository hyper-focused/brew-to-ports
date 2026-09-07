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
        self.assertIn("brew-to-ports", text)
        self.assertIn("Comment:", text)

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
            advice = suggest_path(
                "/usr/bin",
                rc_files=files,
                home=home,
                path_file=home / ".zsh_path.brew-to-ports",
            )
            self.assertTrue(any(p.endswith(".zsh_path") for p in advice.path_owners + advice.rc_hits))
            self.assertTrue(any(l.kind == "source_owner" for l in advice.comment_out))
            self.assertIn("path=(", advice.load_zsh)

    def test_zshenv_collected_antidote_not_followed(self):
        from brew_to_ports.adapters.shell_env import read_rc_files

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".zshenv").write_text("source ~/.zsh_path\n", encoding="utf-8")
            (home / ".zsh_path").write_text(
                "path=(\n  $HOME/.local/bin\n  /usr/local/bin\n  $path\n)\n",
                encoding="utf-8",
            )
            (home / ".zshrc").write_text(
                "fpath=(~/.grok/completions/zsh $fpath)\n"
                "source /usr/local/opt/antidote/share/antidote/antidote.zsh\n"
                'alias cat="/usr/local/bin/bat --color=auto"\n',
                encoding="utf-8",
            )
            (home / ".zprofile").write_text(
                'eval "$(/usr/local/bin/brew shellenv)"\n'
                "source ~/.zsh_path\n"
                "# MacPorts Installer addition on 2026-09-05\n"
                'export PATH="/opt/local/bin:/opt/local/sbin:$PATH"\n',
                encoding="utf-8",
            )
            files = read_rc_files(home=home)
            names = [p.name for p, _ in files]
            self.assertIn(".zshenv", names)
            self.assertIn(".zsh_path", names)
            self.assertTrue(all("antidote" not in str(p) for p, _ in files))
            dest = home / ".zsh_path.brew-to-ports"
            advice = suggest_path(
                "/usr/local/bin:/usr/bin",
                rc_files=files,
                home=home,
                path_file=dest,
            )
            self.assertEqual(advice.idiom, "zsh-array")
            self.assertTrue(any(p.endswith(".zsh_path") for p in advice.path_owners))
            self.assertTrue(any("brew shellenv" in w for w in advice.extra_writers))
            self.assertTrue(any("MacPorts installer" in w for w in advice.extra_writers))
            self.assertTrue(advice.alias_hits)
            kinds = {l.kind for l in advice.comment_out}
            self.assertIn("shellenv", kinds)
            self.assertIn("export", kinds)
            self.assertIn("source_owner", kinds)
            self.assertIn("/opt/local/bin", advice.path_file_contents)
            self.assertIn("/opt/local/sbin", advice.path_file_contents)
            self.assertNotIn("/usr/bin", advice.path_file_contents)
            text = snippet(advice)
            self.assertIn("path=(", text)
            self.assertIn(".zsh_path.brew-to-ports", text)
            self.assertIn("$path", advice.load_zsh)
            self.assertTrue(any(r.kind == "alias" and "/opt/local/bin/bat" in (r.suggested or "") for r in advice.rewrites))
            self.assertIn("/opt/local/bin/bat", text)

    def test_prefix_swap_keg_and_linker(self):
        from brew_to_ports.path_suggest import rewrite_brew_prefix

        self.assertEqual(
            rewrite_brew_prefix('alias curl="/usr/local/opt/curl/bin/curl"'),
            'alias curl="/opt/local/bin/curl"',
        )
        self.assertEqual(
            rewrite_brew_prefix('alias head="/usr/local/opt/coreutils/libexec/gnubin/head"'),
            'alias head="/opt/local/libexec/gnubin/head"',
        )
        self.assertEqual(
            rewrite_brew_prefix('export LDFLAGS="-L/usr/local/opt/ruby/lib"'),
            'export LDFLAGS="-L/opt/local/lib"',
        )

    def test_fpath_is_not_path_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            zshrc = Path(tmp) / ".zshrc"
            zshrc.write_text("fpath=(~/.grok/completions/zsh $fpath)\n", encoding="utf-8")
            advice = suggest_path("/usr/bin", rc_files=[(zshrc, zshrc.read_text())])
            self.assertEqual(advice.path_owners, [])
            self.assertNotIn(str(zshrc), advice.rc_hits)

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
    def _migrate(self, name, version="1.0"):
        pkg = Package(name=name, version=version, kind="formula", origin="brew", requested=True)
        decision = Decision(
            brew_name=name,
            status=STATUS_MIGRATE,
            match=None,
            reasons=[],
            hold_uninstall=True,
            requested=True,
        )
        return pkg, decision

    def test_finds_conf_and_never_copy_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            conf = prefix / "etc" / "nginx.conf"
            conf.parent.mkdir(parents=True)
            conf.write_text("pid /usr/local/var/run/nginx.pid;\n", encoding="utf-8")
            pkg, decision = self._migrate("nginx", "1.26")
            findings = scan_configs([pkg], [decision], str(prefix), "/opt/local")
            self.assertTrue(findings)
            self.assertTrue(any(f.contains_brew_paths for f in findings))
            self.assertTrue(all(f.copy_safe is False for f in findings))
            self.assertIn("nginx.conf", findings[0].brew_path)

    def test_skips_completions_and_keg_etc(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            comp = prefix / "etc" / "bat" / "bash_completion.d" / "bat"
            comp.parent.mkdir(parents=True)
            comp.write_text("complete -F _bat bat\n", encoding="utf-8")
            keg = prefix / "opt" / "lynx" / "etc" / "lynx.cfg"
            keg.parent.mkdir(parents=True)
            keg.write_text("STARTFILE:https://example.invalid/\n", encoding="utf-8")
            pkg, decision = self._migrate("bat")
            lynx, lynx_d = self._migrate("lynx")
            findings = scan_configs(
                [pkg, lynx], [decision, lynx_d], str(prefix), "/opt/local"
            )
            self.assertEqual(findings, [])

    def test_php_versioned_etc_and_stock_production(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            ini_dir = prefix / "etc" / "php" / "8.4"
            ini_dir.mkdir(parents=True)
            stock = 'memory_limit = 128M\nextension_dir = "/usr/local/lib/php/pecl"\n'
            (ini_dir / "php.ini").write_text(stock, encoding="utf-8")
            (ini_dir / "php.ini-production").write_text(stock, encoding="utf-8")
            pkg, decision = self._migrate("php@8.4", "8.4.25")
            from brew_to_ports.models import Match

            decision.match = Match(
                brew_name="php@8.4",
                port_name="php84",
                confidence="versioned",
                rule_id="versioned",
                version_delta="equal",
            )
            findings = scan_configs([pkg], [decision], str(prefix), "/opt/local")
            self.assertEqual(findings, [])
            (ini_dir / "php.ini").write_text(
                stock.replace("128M", "512M"), encoding="utf-8"
            )
            findings = scan_configs([pkg], [decision], str(prefix), "/opt/local")
            self.assertEqual(len(findings), 1)
            self.assertTrue(findings[0].brew_path.endswith("php/8.4/php.ini"))
            self.assertEqual(findings[0].guessed_ports_path, "/opt/local/etc/php84/php.ini")
            self.assertFalse(findings[0].copy_safe)

    def test_php_ini_development_values_are_stock(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            ini_dir = prefix / "etc" / "php" / "8.4"
            ini_dir.mkdir(parents=True)
            production = (
                "; Default Value: Off\n"
                "; Development Value: On\n"
                "; Production Value: Off\n"
                "display_errors = Off\n"
                "memory_limit = 128M\n"
            )
            live = "display_errors = On\nmemory_limit = 128M\n"
            (ini_dir / "php.ini-production").write_text(production, encoding="utf-8")
            (ini_dir / "php.ini").write_text(live, encoding="utf-8")
            pkg, decision = self._migrate("php@8.4", "8.4.25")
            findings = scan_configs([pkg], [decision], str(prefix), "/opt/local")
            self.assertEqual(findings, [])

    def test_default_sibling_and_bottle_are_stock(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            etc = prefix / "etc"
            etc.mkdir()
            live = etc / "freetds.conf"
            live.write_text("[global]\ntds version = auto\n", encoding="utf-8")
            (etc / "freetds.conf.default").write_text(live.read_text(), encoding="utf-8")
            pkg, decision = self._migrate("freetds", "1.5.19")
            findings = scan_configs([pkg], [decision], str(prefix), "/opt/local")
            self.assertEqual(findings, [])
            (etc / "freetds.conf.default").unlink()
            bottle = prefix / "Cellar" / "nano" / "9.2" / ".bottle" / "etc"
            bottle.mkdir(parents=True)
            nanorc = etc / "nanorc"
            text = "include /usr/local/share/nano/*.nanorc\n"
            nanorc.write_text(text, encoding="utf-8")
            (bottle / "nanorc").write_text(text, encoding="utf-8")
            nano, nano_d = self._migrate("nano", "9.2")
            findings = scan_configs([nano], [nano_d], str(prefix), "/opt/local")
            self.assertEqual(findings, [])
            nanorc.write_text(text + "set linenumbers\n", encoding="utf-8")
            findings = scan_configs([nano], [nano_d], str(prefix), "/opt/local")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].brew_package, "nano")
            self.assertTrue(findings[0].brew_path.endswith("nanorc"))

    def test_nanorc_formula_does_not_claim_nano_etc(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            etc = prefix / "etc"
            etc.mkdir()
            live = etc / "nanorc"
            stock = "include /usr/local/share/nano/*.nanorc\n"
            live.write_text(stock + "set linenumbers\n", encoding="utf-8")
            bottle = prefix / "Cellar" / "nano" / "9.2" / ".bottle" / "etc"
            bottle.mkdir(parents=True)
            (bottle / "nanorc").write_text(stock, encoding="utf-8")
            nano, nano_d = self._migrate("nano", "9.2")
            extra, extra_d = self._migrate("nanorc", "2020.10.10")
            findings = scan_configs(
                [nano, extra], [nano_d, extra_d], str(prefix), "/opt/local"
            )
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].brew_package, "nano")
            live.write_text(stock, encoding="utf-8")
            findings = scan_configs(
                [nano, extra], [nano_d, extra_d], str(prefix), "/opt/local"
            )
            self.assertEqual(findings, [])

    def test_keg_extension_dropin_is_stock(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            dropin = prefix / "etc" / "php" / "8.4" / "conf.d" / "ext-opcache.ini"
            dropin.parent.mkdir(parents=True)
            dropin.write_text(
                "[opcache]\n"
                'zend_extension="/usr/local/opt/php@8.4/lib/php/20240924/opcache.so"\n',
                encoding="utf-8",
            )
            other = prefix / "etc" / "php" / "8.3" / "php.ini"
            other.parent.mkdir(parents=True)
            other.write_text("memory_limit = 512M\n", encoding="utf-8")
            pkg, decision = self._migrate("php@8.4", "8.4.25")
            findings = scan_configs([pkg], [decision], str(prefix), "/opt/local")
            self.assertEqual(findings, [])

    def test_php_ini_user_memory_limit_is_custom(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            ini_dir = prefix / "etc" / "php" / "8.4"
            ini_dir.mkdir(parents=True)
            production = (
                "; This is the php.ini-production INI file.\n"
                "; display_errors\n"
                ";   Development Value: On\n"
                ";   Production Value: Off\n"
                "display_errors = Off\n"
                "memory_limit = 128M\n"
            )
            live = (
                "; This is the php.ini-development INI file.\n"
                "display_errors = On\n"
                "memory_limit = 512M\n"
            )
            (ini_dir / "php.ini-production").write_text(production, encoding="utf-8")
            (ini_dir / "php.ini").write_text(live, encoding="utf-8")
            pkg, decision = self._migrate("php@8.4", "8.4.25")
            findings = scan_configs([pkg], [decision], str(prefix), "/opt/local")
            self.assertEqual(len(findings), 1)
            self.assertTrue(findings[0].brew_path.endswith("php.ini"))

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
