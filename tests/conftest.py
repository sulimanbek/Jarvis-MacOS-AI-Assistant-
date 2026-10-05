import pytest


@pytest.fixture(autouse=True)
def _isolate_from_bridge(monkeypatch, tmp_path):
    """Tests must never talk to a real ui-bridge, even if one is running."""
    import core.bridge_client as bc
    import core.router as router

    monkeypatch.setattr(router, "BRAIN_MODE", "local")

    # And never shell out to the real Shortcuts app.
    import core.executor as executor
    import core.system_actions as system_actions

    monkeypatch.setattr(executor, "list_shortcuts", lambda: [])
    monkeypatch.setattr(system_actions, "list_shortcuts", lambda: [])
    monkeypatch.setattr(
        bc, "_client", bc.BridgeClient(token_file=str(tmp_path / "no-such-token"))
    )
