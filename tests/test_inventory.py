import unittest

from brew_to_ports.inventory import from_brew_json


class InventoryDepTests(unittest.TestCase):
    def test_unions_declared_and_runtime_deps(self):
        payload = {
            "formulae": [
                {
                    "name": "wget",
                    "tap": "homebrew/core",
                    "dependencies": ["libidn2"],
                    "recommended_dependencies": ["libgpg-error"],
                    "optional_dependencies": ["pcre2"],
                    "installed": [
                        {
                            "version": "1.0",
                            "installed_on_request": True,
                            "runtime_dependencies": [{"full_name": "openssl@3"}],
                        }
                    ],
                },
                {"name": "libidn2", "installed": [{"version": "1", "installed_on_request": False}]},
                {"name": "libgpg-error", "installed": [{"version": "1", "installed_on_request": False}]},
                {"name": "pcre2", "installed": [{"version": "1", "installed_on_request": False}]},
                {"name": "openssl@3", "installed": [{"version": "3", "installed_on_request": False}]},
            ],
            "casks": [],
        }
        pkgs = {p.name: p for p in from_brew_json(payload)}
        deps = set(pkgs["wget"].runtime_deps)
        self.assertEqual(deps, {"openssl@3", "libidn2", "libgpg-error", "pcre2"})

    def test_skips_recommended_not_installed(self):
        payload = {
            "formulae": [
                {
                    "name": "wget",
                    "dependencies": [],
                    "recommended_dependencies": ["ghostscript"],
                    "installed": [{"version": "1", "installed_on_request": True, "runtime_dependencies": []}],
                }
            ],
            "casks": [],
        }
        pkgs = {p.name: p for p in from_brew_json(payload)}
        self.assertNotIn("ghostscript", pkgs["wget"].runtime_deps)

    def test_cask_depends_on_formula(self):
        payload = {
            "formulae": [
                {"name": "gnupg", "installed": [{"version": "2", "installed_on_request": False}]},
            ],
            "casks": [
                {
                    "token": "gpg-suite",
                    "tap": "homebrew/cask",
                    "installed": "1",
                    "depends_on": {"formula": ["gnupg"]},
                }
            ],
        }
        pkgs = {p.name: p for p in from_brew_json(payload)}
        self.assertEqual(pkgs["gpg-suite"].runtime_deps, ["gnupg"])


if __name__ == "__main__":
    unittest.main()
