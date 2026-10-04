import pytest

from core import mac_actions


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    mac_actions.set_confirmer(None)
    spoken, executed = [], []
    monkeypatch.setattr(mac_actions, "speak", lambda t: spoken.append(t))

    def fake_execute(decision, user_input):
        executed.append((decision, user_input))
        return {"ok": True, "message": "Done."}

    monkeypatch.setattr(mac_actions, "execute", fake_execute)
    yield {"spoken": spoken, "executed": executed}
    mac_actions.set_confirmer(None)


def test_plain_app_open_runs_without_confirmation(_reset):
    result = mac_actions.run_model_action({"tool": "app", "name": "Safari"}, "open safari")
    assert result == {"ok": True, "message": "Done."}
    assert _reset["executed"][0][0] == {"tool": "app", "name": "Safari"}


def test_music_and_volume_run_without_confirmation(_reset):
    assert mac_actions.run_model_action({"tool": "music", "query": "Starboy"})["ok"]
    assert mac_actions.run_model_action({"tool": "system", "action": "volume_up"})["ok"]


@pytest.mark.parametrize("action", ["clipboard_read", "screenshot"])
def test_private_system_actions_are_refused_for_claude(action, _reset):
    result = mac_actions.run_model_action({"tool": "system", "action": action})
    assert result["ok"] is False
    assert _reset["executed"] == []


@pytest.mark.parametrize(
    "decision",
    [
        {"tool": "browser", "target": "youtube"},
        {"tool": "open", "target": "some blog"},
        {"tool": "shortcut", "name": "Do Thing"},
    ],
)
def test_risky_tools_refused_when_no_way_to_ask(decision, _reset):
    result = mac_actions.run_model_action(decision)
    assert result["ok"] is False
    assert _reset["executed"] == []


def test_risky_tool_runs_after_a_spoken_yes(_reset):
    asked = []
    mac_actions.set_confirmer(lambda d: asked.append(d) or True)
    result = mac_actions.run_model_action({"tool": "browser", "target": "youtube", "query": "cats"})
    assert result["ok"] is True
    assert asked and asked[0]["tool"] == "browser"
    # The user hears what they are being asked to approve.
    assert "youtube" in _reset["spoken"][0].lower() and "cats" in _reset["spoken"][0].lower()


def test_risky_tool_blocked_after_a_no(_reset):
    mac_actions.set_confirmer(lambda d: False)
    result = mac_actions.run_model_action({"tool": "open", "target": "some blog"})
    assert result["ok"] is False and "no" in result["error"].lower()
    assert _reset["executed"] == []


def test_unknown_tool_and_missing_fields_are_rejected(_reset):
    assert mac_actions.run_model_action({"tool": "rm -rf"})["ok"] is False
    assert mac_actions.run_model_action({"tool": "app"})["ok"] is False
    assert _reset["executed"] == []
