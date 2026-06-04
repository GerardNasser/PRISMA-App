from gui.screens.screening import _normalize_rules


def test_normalize_rules_handles_none_codebook():
    assert _normalize_rules(None) == []


def test_normalize_rules_handles_none_rules_value():
    assert _normalize_rules({"rules": None}) == []


def test_normalize_rules_handles_missing_rules_key():
    assert _normalize_rules({}) == []


def test_normalize_rules_passes_through_list():
    rules = [{"code": "POP", "direction": "exclude", "rationale": "wrong population"}]
    assert _normalize_rules({"rules": rules}) == rules
