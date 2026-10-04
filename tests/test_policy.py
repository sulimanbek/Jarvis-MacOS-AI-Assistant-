import json

import security.policy as policy


def test_get_tool_risk_known_tools():
    assert policy.get_tool_risk("system") == "low"
    assert policy.get_tool_risk("browser") == "medium"
    assert policy.get_tool_risk("shortcut") == "high"


def test_get_tool_risk_unknown_tool_defaults_high():
    assert policy.get_tool_risk("something_made_up") == "high"


def test_get_policy_merges_policy_json_over_defaults(monkeypatch, tmp_path):
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps({"require_confirmation_for_actions": False, "custom_key": "value"}))
    monkeypatch.setattr(policy, "_POLICY_PATH", policy_file)

    result = policy.get_policy()

    assert result["require_confirmation_for_actions"] is False
    assert result["custom_key"] == "value"
    # Defaults not overridden should still be present
    assert result["confirm_tools"] == policy._DEFAULT_POLICY["confirm_tools"]


def test_get_policy_returns_defaults_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(policy, "_POLICY_PATH", tmp_path / "does_not_exist.json")

    result = policy.get_policy()

    assert result == policy._DEFAULT_POLICY


def test_get_policy_returns_defaults_on_malformed_json(monkeypatch, tmp_path):
    policy_file = tmp_path / "policy.json"
    policy_file.write_text("{ not valid json ]")
    monkeypatch.setattr(policy, "_POLICY_PATH", policy_file)

    result = policy.get_policy()

    assert result == policy._DEFAULT_POLICY


def test_get_policy_returns_defaults_when_json_is_not_a_dict(monkeypatch, tmp_path):
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps(["not", "a", "dict"]))
    monkeypatch.setattr(policy, "_POLICY_PATH", policy_file)

    result = policy.get_policy()

    assert result == policy._DEFAULT_POLICY


def test_requires_confirmation_true_for_confirm_tool(monkeypatch):
    monkeypatch.setattr(policy, "get_policy", lambda: dict(policy._DEFAULT_POLICY))

    assert policy.requires_confirmation("shortcut") is True


def test_requires_confirmation_false_when_confirmation_disabled(monkeypatch):
    disabled = dict(policy._DEFAULT_POLICY)
    disabled["require_confirmation_for_actions"] = False
    monkeypatch.setattr(policy, "get_policy", lambda: disabled)

    assert policy.requires_confirmation("shortcut") is False


def test_requires_confirmation_false_for_empty_or_none_tool(monkeypatch):
    monkeypatch.setattr(policy, "get_policy", lambda: dict(policy._DEFAULT_POLICY))

    assert policy.requires_confirmation("") is False
    assert policy.requires_confirmation(None) is False


def test_requires_confirmation_false_for_tool_not_in_confirm_list(monkeypatch):
    monkeypatch.setattr(policy, "get_policy", lambda: dict(policy._DEFAULT_POLICY))

    assert policy.requires_confirmation("unknown_tool") is False
