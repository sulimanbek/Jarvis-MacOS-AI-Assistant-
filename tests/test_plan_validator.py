import core.plan_validator as plan_validator


def test_validate_plan_accepts_valid_multi_step_plan():
    plan = {
        "goal": "open safari and play music",
        "steps": [
            {"tool": "app", "name": "Safari"},
            {"tool": "music", "query": "Starboy"},
        ],
    }
    result = plan_validator.validate_plan(plan)
    assert result.valid is True
    assert result.error is None


def test_validate_plan_rejects_non_dict_plan():
    result = plan_validator.validate_plan(["not", "a", "dict"])
    assert result.valid is False
    assert result.error == "Plan is not a dict"


def test_validate_plan_rejects_missing_goal():
    result = plan_validator.validate_plan({"steps": [{"tool": "app", "name": "Safari"}]})
    assert result.valid is False
    assert result.error == "Plan missing 'goal' string"


def test_validate_plan_rejects_missing_steps():
    result = plan_validator.validate_plan({"goal": "do something"})
    assert result.valid is False
    assert result.error == "Plan missing 'steps' list"


def test_validate_plan_rejects_empty_steps():
    result = plan_validator.validate_plan({"goal": "do something", "steps": []})
    assert result.valid is False
    assert result.error == "Plan has zero steps"


def test_validate_plan_enforces_max_steps():
    steps = [{"tool": "app", "name": f"App{i}"} for i in range(6)]
    result = plan_validator.validate_plan({"goal": "do a lot", "steps": steps})
    assert result.valid is False
    assert result.error == "Too many steps (6 > 5)"


def test_validate_plan_accepts_exactly_max_steps():
    steps = [{"tool": "app", "name": f"App{i}"} for i in range(5)]
    result = plan_validator.validate_plan({"goal": "do a lot", "steps": steps})
    assert result.valid is True


def test_validate_plan_rejects_unknown_tool():
    result = plan_validator.validate_plan(
        {"goal": "do something", "steps": [{"tool": "shell", "command": "rm -rf /"}]}
    )
    assert result.valid is False
    assert "unknown tool 'shell'" in result.error


def test_validate_plan_rejects_missing_required_field():
    result = plan_validator.validate_plan(
        {"goal": "open an app", "steps": [{"tool": "app"}]}
    )
    assert result.valid is False
    assert "requires non-empty 'name'" in result.error


def test_validate_plan_rejects_blank_required_field():
    result = plan_validator.validate_plan(
        {"goal": "open an app", "steps": [{"tool": "app", "name": "   "}]}
    )
    assert result.valid is False
    assert "requires non-empty 'name'" in result.error


def test_validate_plan_rejects_unknown_system_action():
    result = plan_validator.validate_plan(
        {"goal": "do something", "steps": [{"tool": "system", "action": "teleport"}]}
    )
    assert result.valid is False
    assert "unknown system action 'teleport'" in result.error


def test_validate_plan_accepts_known_system_action():
    result = plan_validator.validate_plan(
        {"goal": "increase volume", "steps": [{"tool": "system", "action": "volume_up"}]}
    )
    assert result.valid is True


def test_validate_plan_rejects_step_that_is_not_a_dict():
    result = plan_validator.validate_plan({"goal": "do something", "steps": ["not a dict"]})
    assert result.valid is False
    assert result.error == "Step 0 is not a dict"


def test_validate_plan_rejects_step_missing_tool():
    result = plan_validator.validate_plan({"goal": "do something", "steps": [{"name": "Safari"}]})
    assert result.valid is False
    assert result.error == "Step 0: missing 'tool'"
