import threading
import time

from core.bridge_client import BridgeClient
from core.level_stream import GATE, LevelStreamer, shape


def test_room_noise_is_silence():
    assert shape(0.0) == 0.0
    assert shape(GATE) == 0.0
    assert shape(0.003) == 0.0


def test_speech_moves_the_level_and_it_is_monotonic_and_capped():
    levels = [shape(r) for r in (0.01, 0.02, 0.05, 0.1, 0.3, 1.0)]
    assert levels == sorted(levels)
    assert 0.2 < shape(0.03) < 0.8
    assert shape(1.0) == 1.0


def _wait_for(cond, timeout=1.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.005)
    return False


def test_streamer_sends_changes_and_the_return_to_silence():
    sent = []
    s = LevelStreamer(send=sent.append, interval=0.01)
    s.start()
    try:
        s.push(0.1)
        assert _wait_for(lambda: len(sent) >= 1)
        assert sent[0] > 0.3
        s.push(0.0)
        assert _wait_for(lambda: sent[-1] == 0.0)
    finally:
        s.stop()


def test_streamer_does_not_resend_an_unchanged_level():
    sent = []
    s = LevelStreamer(send=sent.append, interval=0.01)
    s.start()
    try:
        s.push(0.1)
        assert _wait_for(lambda: len(sent) == 1)
        time.sleep(0.15)  # many intervals with no change
        assert len(sent) == 1
    finally:
        s.stop()


def test_streamer_survives_a_failing_send_and_stops_cleanly():
    calls = []

    def boom(v):
        calls.append(v)
        raise RuntimeError("bridge exploded")

    s = LevelStreamer(send=boom, interval=0.01)
    s.start()
    thread = s._thread
    s.push(0.1)
    assert _wait_for(lambda: len(calls) >= 1)
    s.stop()
    assert thread is not None and not thread.is_alive()


def test_push_is_safe_when_never_started():
    LevelStreamer(send=lambda v: None).push(0.5)


# ── BridgeClient droppable emits ─────────────────────────────────────────────

def test_droppable_emit_never_dials_the_bridge(tmp_path):
    token = tmp_path / "t"
    token.write_text("x")
    c = BridgeClient(url="ws://127.0.0.1:1/core", token_file=str(token), retry_cooldown=60)
    c.emit_level(0.5)
    # A normal emit would have tried to connect and started the cooldown.
    assert c._down_until == 0.0
    assert c._ws is None


def test_droppable_emit_skips_when_the_lock_is_busy(tmp_path):
    c = BridgeClient(url="ws://127.0.0.1:1/core", token_file=str(tmp_path / "t"))
    got = []
    started = threading.Event()

    def hold():
        with c._lock:
            started.set()
            time.sleep(0.3)

    t = threading.Thread(target=hold)
    t.start()
    started.wait()
    t0 = time.monotonic()
    c.emit_level(0.5)  # must return at once, not wait for the lock
    got.append(time.monotonic() - t0)
    t.join()
    assert got[0] < 0.1


def test_level_event_reaches_the_bridge(tmp_path):
    import json
    from http import HTTPStatus

    from websockets.sync.server import serve

    received = []

    def handler(ws):
        ws.send(json.dumps({"type": "hello"}))
        for raw in ws:
            received.append(json.loads(raw))

    def gate(connection, request):
        if request.headers.get("X-Jarvis-Token") != "tok":
            return connection.respond(HTTPStatus.UNAUTHORIZED, "no\n")
        return None

    server = serve(handler, "127.0.0.1", 0, process_request=gate)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    token = tmp_path / "t"
    token.write_text("tok")
    try:
        c = BridgeClient(url=f"ws://127.0.0.1:{server.socket.getsockname()[1]}/core",
                         token_file=str(token), connect_timeout=2)
        assert c.warm()
        c.emit_level(1.7)  # clamped
        assert _wait_for(lambda: any(m.get("event", {}).get("kind") == "level" for m in received))
        event = next(m for m in received if m["event"]["kind"] == "level")["event"]
        assert event == {"kind": "level", "level": 1.0}
    finally:
        server.shutdown()
