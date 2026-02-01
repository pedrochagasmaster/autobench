import unittest

from core.privacy_validator import PrivacyValidator


class TestPrivacyRulesConfig(unittest.TestCase):
    def test_externalized_rules_available(self) -> None:
        PrivacyValidator.reload_rules()
        rules = PrivacyValidator.get_rules()
        self.assertIn("5/25", rules)
        self.assertIn("10/40", rules)
        self.assertEqual(int(rules["6/30"]["min_entities"]), 6)

    def test_select_rule_uses_loaded_rules(self) -> None:
        self.assertEqual(PrivacyValidator.select_rule(10), "10/40")
        self.assertEqual(PrivacyValidator.select_rule(7), "7/35")
        self.assertEqual(PrivacyValidator.select_rule(4, merchant_mode=True), "4/35")

    def test_protected_default_uses_rule_cap(self) -> None:
        validator = PrivacyValidator(rule_name="10/40", protected_entities=["A"])
        self.assertEqual(float(validator.max_concentration), 40.0)
        self.assertEqual(float(validator.protected_max_concentration), 40.0)


if __name__ == "__main__":
    unittest.main()
