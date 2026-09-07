import os
import unittest
from unittest.mock import patch

from brew_to_ports.adapters.brew import BrewError, brew_prefix, load_installed_json
from brew_to_ports.adapters.os_tools import (
    INTEL_BREW,
    OS_PATH,
    USER_PATH_ENV,
    migrator_path,
    subprocess_env,
    user_path,
)
from brew_to_ports.adapters.shell_env import current_path
from brew_to_ports.paths import repo_root


class OsToolsTests(unittest.TestCase):
    def test_os_path_is_apple_first_no_gnubin(self):
        self.assertTrue(OS_PATH.startswith("/usr/bin:/bin"))
        self.assertNotIn("gnubin", OS_PATH)
        self.assertNotIn("/usr/local/opt", OS_PATH)

    def test_migrator_path_appends_prefix_bins_after_os(self):
        p = migrator_path("/usr/local/bin", "/opt/local/bin")
        self.assertTrue(p.startswith(OS_PATH))
        self.assertLess(p.index("/usr/bin"), p.index("/usr/local/bin"))
        self.assertNotIn("gnubin", p)

    def test_user_path_prefers_stashed_launch_path(self):
        env = {
            USER_PATH_ENV: "/usr/local/opt/coreutils/libexec/gnubin:/usr/bin",
            "PATH": "/usr/bin:/bin",
        }
        self.assertEqual(user_path(env), env[USER_PATH_ENV])

    def test_current_path_reads_stashed_launch_path(self):
        gnubin = "/usr/local/opt/coreutils/libexec/gnubin:/usr/bin"
        with patch.dict(os.environ, {USER_PATH_ENV: gnubin, "PATH": "/usr/bin:/bin"}, clear=False):
            self.assertEqual(current_path(), gnubin)

    def test_subprocess_env_drops_gnubin(self):
        with patch.dict(
            os.environ,
            {"PATH": "/usr/local/opt/coreutils/libexec/gnubin:/usr/bin"},
            clear=False,
        ):
            env = subprocess_env("/usr/local/bin")
        self.assertTrue(env["PATH"].startswith(OS_PATH))
        self.assertNotIn("gnubin", env["PATH"])
        self.assertIn("/usr/local/bin", env["PATH"])

    def test_brew_uses_intel_binary_not_path_which(self):
        with patch("brew_to_ports.adapters.brew.os.path.isfile", return_value=False):
            self.assertEqual(brew_prefix(), "/usr/local")
        with patch("brew_to_ports.adapters.brew.os.path.isfile", return_value=True), patch(
            "brew_to_ports.adapters.brew.subprocess.check_output", return_value="/usr/local\n"
        ) as chk:
            self.assertEqual(brew_prefix(), "/usr/local")
            argv = chk.call_args[0][0]
            self.assertEqual(argv[0], INTEL_BREW)
            env = chk.call_args.kwargs["env"]
            self.assertTrue(env["PATH"].startswith(OS_PATH))
            self.assertNotIn("gnubin", env["PATH"])

    def test_load_installed_json_requires_intel_brew(self):
        with patch("brew_to_ports.adapters.brew.os.path.isfile", return_value=False):
            with self.assertRaises(BrewError) as ctx:
                load_installed_json()
        self.assertIn(INTEL_BREW, str(ctx.exception))

    def test_wrapper_pins_os_path_and_stashes_user_path(self):
        wrapper = (repo_root() / "brew-to-ports").read_text(encoding="utf-8")
        self.assertIn("unsetopt aliases", wrapper)
        self.assertIn("BREW_TO_PORTS_USER_PATH", wrapper)
        self.assertIn("PATH=/usr/bin:/bin:/usr/sbin:/sbin", wrapper)
        self.assertIn("hash -r", wrapper)
        self.assertNotIn("command -v brew", wrapper)
        self.assertIn("/usr/local/bin/brew", wrapper)
