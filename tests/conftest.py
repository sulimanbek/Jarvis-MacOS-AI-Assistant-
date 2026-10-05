import pytest


@pytest.fixture(autouse=True)
def _isolate_from_bridge(monkeypatch, tmp_path):
    """Tests must never talk to a real ui-bridge, even if one is running."""
    import core.bridge_client as bc
    import core.router as router

    monkeypatch.setattr(router, "BRAIN_MODE", "local")

    # Routing tests must be decided by the rules, never rescued by a real model. If a
    # phrase falls through to the LLM it must fail loudly, not pass by luck.
    def _no_llm(text):
        raise AssertionError(f"routing reached the real LLM for {text!r}")

    monkeypatch.setattr(router, "think_local", _no_llm)

    # Tests must never call ElevenLabs or play audio, even if a key is in the environment.
    import audio.tts as tts

    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(tts, "TTS_ENGINE", "system")
    monkeypatch.setattr(tts, "_cloud_down_until", 0.0)
    monkeypatch.setattr(tts, "_warned", set())

    # And never shell out to the real Shortcuts app.
    import core.executor as executor
    import core.system_actions as system_actions

    monkeypatch.setattr(executor, "list_shortcuts", lambda: [])
    monkeypatch.setattr(system_actions, "list_shortcuts", lambda: [])
    monkeypatch.setattr(
        bc, "_client", bc.BridgeClient(token_file=str(tmp_path / "no-such-token"))
    )
