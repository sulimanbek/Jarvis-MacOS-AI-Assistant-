import pytest


@pytest.fixture(autouse=True)
def _isolate_from_bridge(monkeypatch, tmp_path):
    """Tests must never talk to a real ui-bridge, even if one is running."""
    import core.bridge_client as bc
    import core.router as router

    monkeypatch.setattr(router, "BRAIN_MODE", "local")
    monkeypatch.setattr(
        bc, "_client", bc.BridgeClient(token_file=str(tmp_path / "no-such-token"))
    )
