from core import brain_claude, router
from core.bridge_client import BridgeError, BridgeUnavailable


class FakeClient:
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc, self.asked = reply, exc, []

    def ask(self, text, on_action=None, timeout=None):
        self.asked.append(text)
        if self.exc:
            raise self.exc
        return self.reply


def _use(monkeypatch, client):
    monkeypatch.setattr(brain_claude, "get_client", lambda: client)


def test_success_becomes_a_spoken_response_decision(monkeypatch):
    _use(monkeypatch, FakeClient(reply="Paris."))
    assert brain_claude.think_claude("capital of France?") == {
        "tool": None, "response": "Paris.", "_source": "claude",
    }


def test_unavailable_and_failed_turns_fall_back(monkeypatch):
    _use(monkeypatch, FakeClient(exc=BridgeUnavailable("down")))
    assert brain_claude.think_claude("hi") is None
    _use(monkeypatch, FakeClient(exc=BridgeError("usage limit")))
    assert brain_claude.think_claude("hi") is None


def test_empty_reply_falls_back(monkeypatch):
    _use(monkeypatch, FakeClient(reply=""))
    assert brain_claude.think_claude("hi") is None


def test_timeout_apologises_instead_of_falling_back(monkeypatch):
    _use(monkeypatch, FakeClient(exc=TimeoutError()))
    decision = brain_claude.think_claude("hi")
    assert decision["tool"] is None
    assert decision["_unhandled_reason"] == "claude_timeout"


# ── router integration ──────────────────────────────────────────────────────

def test_router_uses_claude_for_non_fast_path_requests(monkeypatch):
    monkeypatch.setattr(router, "BRAIN_MODE", "claude")
    monkeypatch.setattr(router, "think_claude", lambda t: {"tool": None, "response": "Claude says hi", "_source": "claude"})
    monkeypatch.setattr(router, "think_local", lambda t: (_ for _ in ()).throw(AssertionError("local used")))
    assert router.route("how do magnets work")["response"] == "Claude says hi"


def test_router_falls_back_to_local_when_claude_returns_none(monkeypatch):
    monkeypatch.setattr(router, "BRAIN_MODE", "claude")
    monkeypatch.setattr(router, "think_claude", lambda t: None)
    monkeypatch.setattr(router, "think_local", lambda t: {"tool": None, "response": "local answer"})
    assert router.route("how do magnets work")["response"] == "local answer"


def test_fast_path_never_reaches_claude(monkeypatch):
    monkeypatch.setattr(router, "BRAIN_MODE", "claude")
    monkeypatch.setattr(router, "think_claude", lambda t: (_ for _ in ()).throw(AssertionError("claude used")))
    assert router.route("volume up") == {"tool": "system", "action": "volume_up"}


def test_multi_step_stays_on_the_local_agent(monkeypatch):
    monkeypatch.setattr(router, "BRAIN_MODE", "claude")
    monkeypatch.setattr(router, "think_claude", lambda t: (_ for _ in ()).throw(AssertionError("claude used")))
    assert router.route("open safari and then play mozart")["tool"] == "__agent__"


def test_local_mode_never_contacts_claude(monkeypatch):
    monkeypatch.setattr(router, "BRAIN_MODE", "local")
    monkeypatch.setattr(router, "think_claude", lambda t: (_ for _ in ()).throw(AssertionError("claude used")))
    monkeypatch.setattr(router, "think_local", lambda t: {"tool": None, "response": "offline"})
    assert router.route("how do magnets work")["response"] == "offline"
