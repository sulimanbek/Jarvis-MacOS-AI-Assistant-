import json
import threading
from http import HTTPStatus

import pytest
from websockets.sync.server import serve

from core.bridge_client import BridgeClient, BridgeError, BridgeUnavailable

TOKEN = "s3cret"


@pytest.fixture
def bridge(tmp_path):
    """A fake ui-bridge /core endpoint. Each test sets bridge.script(ws, msg)."""

    class Fake:
        received: list[dict] = []
        script = staticmethod(lambda ws, msg: None)

    fake = Fake()
    fake.received = []

    def handler(ws):
        ws.send(json.dumps({"type": "hello", "model": "test", "writes": False}))
        try:
            for raw in ws:
                msg = json.loads(raw)
                fake.received.append(msg)
                fake.script(ws, msg)
        except Exception:
            pass

    def process_request(connection, request):
        if request.headers.get("X-Jarvis-Token") != TOKEN:
            return connection.respond(HTTPStatus.UNAUTHORIZED, "no\n")
        return None

    server = serve(handler, "127.0.0.1", 0, process_request=process_request)
    port = server.socket.getsockname()[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    token_file = tmp_path / "token"
    token_file.write_text(TOKEN)
    fake.url = f"ws://127.0.0.1:{port}/core"
    fake.token_file = token_file
    fake.client = lambda **kw: BridgeClient(
        url=fake.url, token_file=str(token_file), connect_timeout=2, retry_cooldown=0.3, **kw
    )
    yield fake
    server.shutdown()


def test_ask_returns_final_text(bridge):
    def script(ws, msg):
        if msg["type"] == "ask":
            ws.send(json.dumps({"type": "text", "delta": "Hel", "ask": msg["id"]}))
            ws.send(json.dumps({"type": "done", "text": "Hello there.", "ask": msg["id"]}))

    bridge.script = script
    assert bridge.client().ask("hi") == "Hello there."


def test_ask_falls_back_to_streamed_text_when_done_is_empty(bridge):
    def script(ws, msg):
        ws.send(json.dumps({"type": "text", "delta": "Hi ", "ask": msg["id"]}))
        ws.send(json.dumps({"type": "text", "delta": "you.", "ask": msg["id"]}))
        ws.send(json.dumps({"type": "done", "text": "", "ask": msg["id"]}))

    bridge.script = script
    assert bridge.client().ask("hi") == "Hi you."


def test_stale_frames_from_an_earlier_turn_are_ignored(bridge):
    def script(ws, msg):
        ws.send(json.dumps({"type": "done", "text": "OLD ANSWER", "ask": "p-some-old-id"}))
        ws.send(json.dumps({"type": "done", "text": "right one", "ask": msg["id"]}))

    bridge.script = script
    assert bridge.client().ask("hi") == "right one"


def test_action_round_trip_mid_turn(bridge):
    seen = {}

    def script(ws, msg):
        if msg["type"] == "ask":
            seen["qid"] = msg["id"]
            ws.send(json.dumps({"type": "action", "id": "c1", "decision": {"tool": "app", "name": "Safari"}}))
        elif msg["type"] == "reply":
            ws.send(json.dumps({"type": "done", "text": f"result={msg['message']}", "ask": seen["qid"]}))

    bridge.script = script
    calls = []

    def on_action(decision):
        calls.append(decision)
        return {"ok": True, "message": "Opened Safari."}

    assert bridge.client().ask("open safari please", on_action=on_action) == "result=Opened Safari."
    assert calls == [{"tool": "app", "name": "Safari"}]
    reply = next(m for m in bridge.received if m["type"] == "reply")
    assert reply["id"] == "c1" and reply["ok"] is True


def test_action_handler_exception_becomes_a_failed_reply(bridge):
    seen = {}

    def script(ws, msg):
        if msg["type"] == "ask":
            seen["qid"] = msg["id"]
            ws.send(json.dumps({"type": "action", "id": "c9", "decision": {}}))
        elif msg["type"] == "reply":
            ws.send(json.dumps({"type": "done", "text": "ok", "ask": seen["qid"]}))

    bridge.script = script

    def boom(_):
        raise RuntimeError("kaput")

    assert bridge.client().ask("x", on_action=boom) == "ok"
    reply = next(m for m in bridge.received if m["type"] == "reply")
    assert reply["ok"] is False and "kaput" in reply["error"]


def test_action_without_handler_is_refused(bridge):
    seen = {}

    def script(ws, msg):
        if msg["type"] == "ask":
            seen["qid"] = msg["id"]
            ws.send(json.dumps({"type": "action", "id": "c2", "decision": {"tool": "app"}}))
        elif msg["type"] == "reply":
            ws.send(json.dumps({"type": "done", "text": "ok", "ask": seen["qid"]}))

    bridge.script = script
    bridge.client().ask("x")
    reply = next(m for m in bridge.received if m["type"] == "reply")
    assert reply["ok"] is False


def test_error_frame_raises_bridge_error(bridge):
    bridge.script = lambda ws, msg: ws.send(
        json.dumps({"type": "error", "message": "usage limit", "ask": msg["id"]})
    )
    with pytest.raises(BridgeError, match="usage limit"):
        bridge.client().ask("hi")


def test_timeout_interrupts_and_raises(bridge):
    bridge.script = lambda ws, msg: None  # never answers
    with pytest.raises(TimeoutError):
        bridge.client().ask("hi", timeout=0.4)
    # give the fake a moment to record the interrupt
    for _ in range(20):
        if any(m["type"] == "interrupt" for m in bridge.received):
            break
        threading.Event().wait(0.05)
    assert any(m["type"] == "interrupt" for m in bridge.received)


def test_missing_token_file_is_unavailable(tmp_path):
    c = BridgeClient(url="ws://127.0.0.1:1/core", token_file=str(tmp_path / "nope"), retry_cooldown=5)
    with pytest.raises(BridgeUnavailable, match="token"):
        c.ask("hi")


def test_wrong_token_is_rejected(bridge):
    bridge.token_file.write_text("not-the-token")
    with pytest.raises(BridgeUnavailable):
        bridge.client().ask("hi")


def test_nothing_listening_is_unavailable_and_cooldown_skips_redial(tmp_path):
    token = tmp_path / "t"
    token.write_text(TOKEN)
    c = BridgeClient(url="ws://127.0.0.1:1/core", token_file=str(token), retry_cooldown=60)
    with pytest.raises(BridgeUnavailable):
        c.ask("hi")
    # Second call must fail fast from the cooldown, not by dialling again.
    with pytest.raises(BridgeUnavailable, match="recently"):
        c.ask("hi")


def test_emit_never_raises_when_bridge_is_down(tmp_path):
    c = BridgeClient(url="ws://127.0.0.1:1/core", token_file=str(tmp_path / "nope"))
    c.emit("state", state="idle")  # must simply return


def test_emit_reaches_the_bridge(bridge):
    c = bridge.client()
    assert c.warm()
    c.emit("heard", text="open safari")
    for _ in range(20):
        if any(m["type"] == "event" for m in bridge.received):
            break
        threading.Event().wait(0.05)
    event = next(m for m in bridge.received if m["type"] == "event")["event"]
    assert event == {"kind": "heard", "text": "open safari"}


def test_reconnects_after_the_cooldown(bridge):
    c = bridge.client()
    bridge.token_file.write_text("bad")
    with pytest.raises(BridgeUnavailable):
        c.ask("hi")
    bridge.token_file.write_text(TOKEN)
    threading.Event().wait(0.4)  # past the 0.3s cooldown
    bridge.script = lambda ws, msg: ws.send(json.dumps({"type": "done", "text": "back", "ask": msg["id"]}))
    assert c.ask("hi") == "back"
