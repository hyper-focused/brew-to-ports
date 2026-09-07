import unittest

from brew_to_ports.adapters.macports import parse_select_summary
from brew_to_ports.select import runtime_select_links


class SelectLinkTests(unittest.TestCase):
    def test_newest_python_and_php(self):
        links = runtime_select_links(["wget", "php84", "python313", "python314", "nodejs24"])
        by_group = {l.group: l.option for l in links}
        self.assertEqual(by_group["php"], "php84")
        self.assertEqual(by_group["python"], "python314")
        self.assertEqual(by_group["python3"], "python314")
        self.assertEqual(by_group["pip"], "pip314")
        self.assertEqual(by_group["pip3"], "pip314")
        self.assertNotIn("nodejs24", by_group)
        self.assertTrue(all(l.command.startswith("sudo port select --set ") for l in links))

    def test_live_summary_fills_in_after_apply(self):
        summary = [
            ("php", "none", ["php84", "none"]),
            ("python", "python313", ["python313", "python314", "none"]),
            ("python3", "python313", ["python313", "python314", "none"]),
        ]
        links = runtime_select_links([], summary)
        by_group = {l.group: l for l in links}
        self.assertEqual(by_group["php"].option, "php84")
        self.assertEqual(by_group["php"].selected, "none")
        self.assertEqual(by_group["python"].option, "python314")
        self.assertEqual(by_group["python"].selected, "python313")
        from brew_to_ports.select import format_select_block

        block = "\n".join(format_select_block(links))
        self.assertIn("sudo port select --set php php84", block)
        self.assertIn("sudo port select --set python3 python314", block)
        self.assertIn("# currently python313", block)

    def test_parse_select_summary(self):
        text = """
Name        Selected   Options
====        ========   =======
php         php84      php84 none
python      python314  python313 python314 none
pip2        none       none
"""
        rows = parse_select_summary(text)
        by_name = {r[0]: r for r in rows}
        self.assertEqual(by_name["php"][1], "php84")
        self.assertEqual(list(by_name["python"][2]), ["python313", "python314", "none"])
        self.assertEqual(by_name["pip2"][1], "none")
