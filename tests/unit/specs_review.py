"""Regression cases for effective store rules and app overrides."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import specs


class SpecsReview(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.app = Path(temp.name)
        (self.app / ".listing-kit").mkdir()
        self.rules = specs.load()

    def override(self, slot):
        (self.app / specs.OVERRIDE).write_text(json.dumps(
            {"stores": {"play": {"screenshots": {"slots": [slot]}}}}))

    def test_unsafe_rule_destinations(self):
        for key, value in (("folder", "/outside"), ("folder", "../other"), ("folder", "C:drive"),
                           ("folder", "NUL.txt"), ("id", "../untrusted")):
            with self.subTest(key=key, value=value):
                slot = specs.slot(self.rules, "play", "phone").copy()
                slot[key] = value
                self.override(slot)
                with self.assertRaises(specs.SpecsError):
                    specs.load(self.app)

    def test_partial_override_keeps_sibling_limits(self):
        self.override({"id": "phone", "side": {"min": 500}})
        self.rules = specs.load(self.app)
        self.assertEqual(specs.slot(self.rules, "play", "phone")["side"], {"min": 500, "max": 3840})

    def test_typed_rule_sections(self):
        for path, value in (
            ("sources", []), ("appleCategories", 0), ("stores.apple.locales", [True]),
            ("stores.play.graphics.0.alpha", 3), ("stores.play.fields.0.scope", []),
            ("stores.play.changelogs.limit", False), ("stores.apple.screenshots.alpha", 1),
            ("stores.play.screenshots.slots.0.capture.nativeSize", [1]),
            ("stores.play.screenshots.slots.0.side.max", None),
            ("stores.play.screenshots.slots.0.maxRaito", 2),
        ):
            with self.subTest(path=path):
                rules = copy.deepcopy(self.rules)
                obj = rules
                keys = path.split(".")
                for key in keys[:-1]:
                    obj = obj[int(key)] if isinstance(obj, list) else obj[key]
                obj[keys[-1]] = value
                self.assertTrue(specs.check(rules))

    def test_malformed_requirement_is_reported(self):
        for rule in ([], "always", {"rule": "if"}, {"rule": "always", "unless": []}):
            with self.subTest(rule=rule):
                with self.assertRaises(specs.SpecsError):
                    specs.requirement(rule, {})

    def test_unknown_requirements(self):
        for date in ({}, {"from":"2027-01-01"}):
            for rule in ({"rule":"always", "unless":"skip"}, {"rule":"if", "condition":"unknown"}):
                with self.subTest(rule=rule, date=date):
                    self.assertEqual(specs.requirement(dict(rule, **date), {})[0], "upcoming")
        with self.assertRaises(specs.SpecsError):
            specs.requirement({"rule":"sometimes"}, {})


if __name__ == "__main__":
    unittest.main()
