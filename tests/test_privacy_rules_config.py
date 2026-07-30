import unittest
from copy import deepcopy

import pytest
import yaml

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

    def test_protected_default_uses_citi_control_3_cap(self) -> None:
        validator = PrivacyValidator(rule_name="10/40", protected_entities=["Citibank"])
        self.assertEqual(float(validator.max_concentration), 40.0)
        self.assertEqual(float(validator.protected_max_concentration), 25.0)


if __name__ == "__main__":
    unittest.main()


def test_weaker_external_privacy_rules_fail_closed(
    tmp_path,
    monkeypatch,
) -> None:
    weak_rules = {
        name: dict(config)
        for name, config in PrivacyValidator.DEFAULT_RULES.items()
    }
    weak_rules["5/25"] = {
        "min_entities": 4,
        "max_concentration": 99.0,
    }
    rules_path = tmp_path / "weak_rules.yaml"
    rules_path.write_text(
        yaml.safe_dump({"rules": weak_rules}),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        PrivacyValidator.RULES_ENV_VAR,
        str(rules_path),
    )

    with pytest.raises(ValueError, match="official-policy"):
        PrivacyValidator.reload_rules()


def test_extra_weak_rule_cannot_enter_legacy_selection(
    tmp_path,
    monkeypatch,
) -> None:
    PrivacyValidator._RULES_CACHE = deepcopy(
        PrivacyValidator.DEFAULT_RULES
    )
    rules = deepcopy(PrivacyValidator.DEFAULT_RULES)
    rules["1/100"] = {
        "min_entities": 1,
        "max_concentration": 100.0,
    }
    rules_path = tmp_path / "extra_weak_rule.yaml"
    rules_path.write_text(
        yaml.safe_dump({"rules": rules}),
        encoding="utf-8",
    )
    monkeypatch.setenv(PrivacyValidator.RULES_ENV_VAR, str(rules_path))

    with pytest.raises(ValueError, match="official-policy"):
        PrivacyValidator.reload_rules()

    assert set(PrivacyValidator.get_rules()) == set(
        PrivacyValidator.DEFAULT_RULES
    )
    assert PrivacyValidator.select_rule(1) == "insufficient"
    assert PrivacyValidator.select_rule(3) == "insufficient"


@pytest.mark.parametrize(
    ("rule_name", "field_path", "invalid_value"),
    [
        ("5/25", ("max_concentration",), float("nan")),
        ("5/25", ("max_concentration",), float("inf")),
        ("5/25", ("max_concentration",), float("-inf")),
        ("5/25", ("max_concentration",), True),
        ("5/25", ("min_entities",), True),
        ("6/30", ("additional", "min_count_above_threshold", 0), float("nan")),
        ("6/30", ("additional", "min_count_above_threshold", 0), float("inf")),
        ("6/30", ("additional", "min_count_above_threshold", 0), float("-inf")),
        ("6/30", ("additional", "min_count_above_threshold", 0), True),
        ("6/30", ("additional", "min_count_above_threshold", 1), float("nan")),
        ("6/30", ("additional", "min_count_above_threshold", 1), float("inf")),
        ("6/30", ("additional", "min_count_above_threshold", 1), float("-inf")),
        ("6/30", ("additional", "min_count_above_threshold", 1), True),
        ("7/35", ("additional", "min_count_15"), float("nan")),
        ("10/40", ("additional", "min_count_10"), float("inf")),
    ],
)
def test_nonfinite_and_boolean_rule_fields_fail_closed(
    tmp_path,
    monkeypatch,
    rule_name,
    field_path,
    invalid_value,
) -> None:
    rules = deepcopy(PrivacyValidator.DEFAULT_RULES)
    target = rules[rule_name]
    for key in field_path[:-1]:
        if isinstance(key, int):
            target = list(target)
        else:
            target = target[key]
    final_key = field_path[-1]
    if isinstance(final_key, int):
        constraint_name = field_path[-2]
        additional = rules[rule_name]["additional"]
        pair = list(additional[constraint_name])
        pair[final_key] = invalid_value
        additional[constraint_name] = pair
    else:
        target[final_key] = invalid_value

    rules_path = tmp_path / "invalid_rules.yaml"
    rules_path.write_text(
        yaml.safe_dump({"rules": rules}),
        encoding="utf-8",
    )
    monkeypatch.setenv(PrivacyValidator.RULES_ENV_VAR, str(rules_path))

    with pytest.raises(ValueError, match="official-policy"):
        PrivacyValidator.reload_rules()
