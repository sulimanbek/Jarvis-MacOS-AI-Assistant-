import core.agent as agent


def _silence(monkeypatch):
    monkeypatch.setattr(agent, "speak", lambda *a, **k: None)
    monkeypatch.setattr(agent, "save_action", lambda *a, **k: None)


def test_parse_plan_json_direct():
    raw = '{"goal": "g", "steps": []}'
    assert agent._parse_plan_json(raw) == {"goal": "g", "steps": []}


def test_parse_plan_json_extracts_embedded_object():
    raw = 'Sure, here is the plan:\n{"goal": "g", "steps": []}\nHope that helps!'
    assert agent._parse_plan_json(raw) == {"goal": "g", "steps": []}


def test_parse_plan_json_returns_none_for_garbage():
    assert agent._parse_plan_json("not json at all") is None
    assert agent._parse_plan_json(None) is None
    assert agent._parse_plan_json("") is None


def test_run_agent_replans_on_failure_and_succeeds(monkeypatch):
    _silence(monkeypatch)

    monkeypatch.setattr(
        agent, "_call_planner",
        lambda user_text: {"goal": "open an app", "steps": [{"tool": "app", "name": "BrokenApp"}]},
    )

    replanner_calls = []

    def fake_replanner(user_text, goal, completed, failed_step, failure_reason):
        replanner_calls.append(
            {"goal": goal, "completed": list(completed), "failed_step": failed_step, "reason": failure_reason}
        )
        return {"goal": goal, "steps": [{"tool": "app", "name": "Safari"}]}

    monkeypatch.setattr(agent, "_call_replanner", fake_replanner)

    def fake_execute(step, user_text):
        if step.get("name") == "BrokenApp":
            return {"ok": False, "message": "app not found", "retryable": False}
        return {"ok": True, "message": f"opened {step.get('name')}"}

    monkeypatch.setattr(agent, "execute", fake_execute)
    monkeypatch.setattr(agent, "verify_step", lambda step, result: result.get("ok", False))

    result = agent.run_agent("open some app")

    assert result == {"ok": True, "message": "opened Safari"}
    assert len(replanner_calls) == 1
    assert replanner_calls[0]["failed_step"] == {"tool": "app", "name": "BrokenApp"}
    assert replanner_calls[0]["reason"] == "app not found"


def test_run_agent_stops_after_replan_budget_exhausted(monkeypatch):
    _silence(monkeypatch)

    monkeypatch.setattr(
        agent, "_call_planner",
        lambda user_text: {"goal": "open an app", "steps": [{"tool": "app", "name": "BrokenApp"}]},
    )

    replanner_calls = {"n": 0}

    def fake_replanner(user_text, goal, completed, failed_step, failure_reason):
        replanner_calls["n"] += 1
        # Replan also fails, so the agent must give up rather than replan forever
        return {"goal": goal, "steps": [{"tool": "app", "name": "AlsoBroken"}]}

    monkeypatch.setattr(agent, "_call_replanner", fake_replanner)
    monkeypatch.setattr(
        agent, "execute",
        lambda step, user_text: {"ok": False, "message": f"{step.get('name')} not found", "retryable": False},
    )
    monkeypatch.setattr(agent, "verify_step", lambda step, result: result.get("ok", False))

    result = agent.run_agent("open some app")

    assert result["ok"] is False
    assert replanner_calls["n"] == agent.MAX_REPLANS
    assert "AlsoBroken" in result["message"]


def test_run_agent_no_replan_when_planner_gives_nothing_useful(monkeypatch):
    _silence(monkeypatch)

    monkeypatch.setattr(
        agent, "_call_planner",
        lambda user_text: {"goal": "open an app", "steps": [{"tool": "app", "name": "BrokenApp"}]},
    )
    # Replanner comes back empty -> agent should stop rather than loop
    monkeypatch.setattr(agent, "_call_replanner", lambda *a, **k: {"goal": "g", "steps": []})
    monkeypatch.setattr(
        agent, "execute",
        lambda step, user_text: {"ok": False, "message": "app not found", "retryable": False},
    )
    monkeypatch.setattr(agent, "verify_step", lambda step, result: result.get("ok", False))

    result = agent.run_agent("open some app")

    assert result == {"ok": False, "message": "app not found"}


def test_run_agent_succeeds_without_needing_a_replan(monkeypatch):
    _silence(monkeypatch)

    monkeypatch.setattr(
        agent, "_call_planner",
        lambda user_text: {"goal": "open safari", "steps": [{"tool": "app", "name": "Safari"}]},
    )

    def fail_if_called(*a, **k):
        raise AssertionError("replanner should not be called on a successful plan")

    monkeypatch.setattr(agent, "_call_replanner", fail_if_called)
    monkeypatch.setattr(agent, "execute", lambda step, user_text: {"ok": True, "message": "opened Safari"})
    monkeypatch.setattr(agent, "verify_step", lambda step, result: True)

    result = agent.run_agent("open safari")

    assert result == {"ok": True, "message": "opened Safari"}


def test_parse_plan_dict_returns_none_for_json_array():
    assert agent._parse_plan_dict("[1, 2, 3]") is None


def test_parse_plan_dict_returns_none_for_json_number():
    assert agent._parse_plan_dict("42") is None


def test_parse_plan_dict_returns_dict_for_valid_plan_json():
    raw = '{"goal": "g", "steps": []}'
    assert agent._parse_plan_dict(raw) == {"goal": "g", "steps": []}


def test_run_agent_handles_planner_returning_json_array_gracefully(monkeypatch):
    _silence(monkeypatch)

    monkeypatch.setattr(agent, "think_with_system", lambda user_text, prompt, include_context=True: "[1,2,3]")

    result = agent.run_agent("do something ambiguous")

    assert result == {"ok": False, "message": "Planner returned no plan"}


def test_run_agent_confirm_step_true_proceeds_normally(monkeypatch):
    _silence(monkeypatch)

    monkeypatch.setattr(
        agent, "_call_planner",
        lambda user_text: {"goal": "open safari", "steps": [{"tool": "app", "name": "Safari"}]},
    )

    execute_calls = []

    def fake_execute(step, user_text):
        execute_calls.append(step)
        return {"ok": True, "message": "opened Safari"}

    monkeypatch.setattr(agent, "execute", fake_execute)
    monkeypatch.setattr(agent, "verify_step", lambda step, result: True)

    result = agent.run_agent("open safari", confirm_step=lambda step: True)

    assert result == {"ok": True, "message": "opened Safari"}
    assert len(execute_calls) == 1


def test_run_agent_confirm_step_false_denies_and_never_executes(monkeypatch):
    _silence(monkeypatch)

    monkeypatch.setattr(
        agent, "_call_planner",
        lambda user_text: {"goal": "open safari", "steps": [{"tool": "app", "name": "Safari"}]},
    )

    def fail_if_called(*a, **k):
        raise AssertionError("execute should never be called when confirm_step denies the step")

    monkeypatch.setattr(agent, "execute", fail_if_called)

    result = agent.run_agent("open safari", confirm_step=lambda step: False)

    assert result == {"ok": False, "message": "Step 1 was not confirmed."}
