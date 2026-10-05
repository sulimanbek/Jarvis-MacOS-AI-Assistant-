"""
core/bridge_client.py

Client for ui-bridge's private /core channel.

Two jobs:
  ask()   — put a request to Claude and wait for the spoken answer. While it
            waits, Claude may ask this process to do something on the Mac; those
            requests arrive as "action" frames and are handed to `on_action`.
  emit()  — tell the HUD what Jarvis is doing (state, what was heard, replies).

Both are best-effort. If the bridge isn't running, ask() raises BridgeUnavailable
(the caller falls back to Ollama) and emit() quietly does nothing. After a
failure the bridge isn't retried for CLAUDE_RETRY_COOLDOWN seconds, so a missing
bridge costs one short connect attempt, not one per command.
"""

import contextlib
import json
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from websockets.exceptions import WebSocketException
from websockets.sync.client import ClientConnection, connect

from config import (
    BRAIN_MODE,
    BRIDGE_EVENTS_URL,
    BRIDGE_TOKEN_FILE,
    BRIDGE_URL,
    CLAUDE_CONNECT_TIMEOUT,
    CLAUDE_RETRY_COOLDOWN,
    CLAUDE_TIMEOUT,
    HUD_EVENTS,
)

ActionHandler = Callable[[dict], dict]


class BridgeUnavailable(Exception):
    """The bridge isn't running, refused us, or dropped the connection."""


class BridgeError(Exception):
    """The bridge was reachable but Claude's turn failed."""


class BridgeClient:
    def __init__(
        self,
        url: str = BRIDGE_URL,
        token_file: str = BRIDGE_TOKEN_FILE,
        connect_timeout: float = CLAUDE_CONNECT_TIMEOUT,
        retry_cooldown: float = CLAUDE_RETRY_COOLDOWN,
    ):
        self._url = url
        self._token_file = Path(token_file)
        self._connect_timeout = connect_timeout
        self._retry_cooldown = retry_cooldown
        self._ws: ClientConnection | None = None
        self._down_until = 0.0
        self._lock = threading.RLock()

    # ── connection ───────────────────────────────────────────────────────────

    def _read_token(self) -> str:
        try:
            return self._token_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _drop(self) -> None:
        ws, self._ws = self._ws, None
        self._down_until = time.monotonic() + self._retry_cooldown
        if ws is not None:
            with contextlib.suppress(Exception):
                ws.close()

    def _ensure(self) -> ClientConnection:
        """Return a live connection, dialling if needed. Raises BridgeUnavailable."""
        if self._ws is not None:
            return self._ws
        if time.monotonic() < self._down_until:
            raise BridgeUnavailable("bridge recently unreachable")

        token = self._read_token()
        if not token:
            self._down_until = time.monotonic() + self._retry_cooldown
            raise BridgeUnavailable(f"no bridge token at {self._token_file} (is the bridge running?)")

        try:
            ws = connect(
                self._url,
                additional_headers={"X-Jarvis-Token": token},
                open_timeout=self._connect_timeout,
                compression=None,
                max_size=2**22,
            )
            hello = json.loads(ws.recv(timeout=self._connect_timeout))
            if hello.get("type") != "hello":
                ws.close()
                raise BridgeUnavailable("unexpected greeting from bridge")
        except BridgeUnavailable:
            self._down_until = time.monotonic() + self._retry_cooldown
            raise
        except (OSError, TimeoutError, WebSocketException, ValueError) as e:
            self._down_until = time.monotonic() + self._retry_cooldown
            raise BridgeUnavailable(str(e) or type(e).__name__) from e

        self._ws = ws
        return ws

    def warm(self) -> bool:
        """Connect now, so the first real request doesn't pay for the dial."""
        with self._lock:
            try:
                self._ensure()
                return True
            except BridgeUnavailable:
                return False

    def emit_level(self, level: float) -> None:
        """The microphone level, 0..1. Dropped if the bridge is busy or away."""
        self.emit("level", level=round(max(0.0, min(1.0, float(level))), 3), droppable=True)

    def close(self) -> None:
        with self._lock:
            ws, self._ws = self._ws, None
            if ws is not None:
                with contextlib.suppress(Exception):
                    ws.close()

    # ── HUD events ───────────────────────────────────────────────────────────

    def emit(self, kind: str, text: str | None = None, state: str | None = None,
             source: str | None = None, level: float | None = None,
             droppable: bool = False) -> None:
        """
        Fire-and-forget. Never raises, never blocks for long.

        droppable=True is for high-rate events such as the mic level: it never
        dials the bridge and never waits for the lock, so it can be skipped
        without delaying anything that matters.
        """
        if not HUD_EVENTS:
            return
        event = {k: v for k, v in {"kind": kind, "text": text, "state": state,
                                   "source": source, "level": level}.items()
                 if v is not None}
        if droppable:
            if not self._lock.acquire(blocking=False):
                return
            try:
                if self._ws is None:
                    return
                self._ws.send(json.dumps({"type": "event", "event": event}))
            except Exception:
                self._drop()
            finally:
                self._lock.release()
            return
        with self._lock:
            try:
                ws = self._ensure()
                ws.send(json.dumps({"type": "event", "event": event}))
            except BridgeUnavailable:
                return
            except Exception:
                self._drop()

    # ── Claude ───────────────────────────────────────────────────────────────

    def ask(self, text: str, on_action: ActionHandler | None = None,
            timeout: float = CLAUDE_TIMEOUT) -> str:
        """
        Ask Claude and return the spoken answer.

        Raises BridgeUnavailable (bridge not there), TimeoutError (took too long),
        or BridgeError (Claude's turn failed).
        """
        with self._lock:
            ws = self._ensure()
            qid = f"p{uuid.uuid4().hex[:10]}"
            try:
                ws.send(json.dumps({"type": "ask", "id": qid, "text": text}))
                return self._await_turn(ws, qid, on_action, timeout)
            except (BridgeError, TimeoutError):
                raise
            except Exception as e:
                self._drop()
                raise BridgeUnavailable(str(e) or type(e).__name__) from e

    def _await_turn(self, ws: ClientConnection, qid: str, on_action: ActionHandler | None,
                    timeout: float) -> str:
        deadline = time.monotonic() + timeout
        parts: list[str] = []

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                ws.send(json.dumps({"type": "interrupt"}))
                raise TimeoutError("Claude took too long to answer")
            try:
                raw = ws.recv(timeout=min(remaining, 1.0))
            except TimeoutError:
                continue

            msg: dict[str, Any] = json.loads(raw)
            kind = msg.get("type")

            if kind == "action":
                # Claude is asking this process to do something on the Mac. That
                # can include waiting for a spoken yes, so the clock restarts.
                reply: dict[str, Any]
                try:
                    reply = on_action(msg.get("decision") or {}) if on_action else {
                        "ok": False, "error": "Mac actions are not available here."}
                except Exception as e:
                    reply = {"ok": False, "error": f"That failed: {e}"}
                ws.send(json.dumps({"type": "reply", "id": msg.get("id"), **reply}))
                deadline = time.monotonic() + timeout
                continue

            # Turn frames carry the id we sent. Anything else is the tail of an
            # earlier turn that timed out; ignore it.
            if kind in ("text", "done", "error", "tool") and msg.get("ask") != qid:
                continue

            if kind == "text":
                parts.append(str(msg.get("delta") or ""))
            elif kind == "done":
                return (str(msg.get("text") or "") or "".join(parts)).strip()
            elif kind == "error":
                raise BridgeError(str(msg.get("message") or "Claude could not answer."))


# ── module-level singleton ──────────────────────────────────────────────────

_client: BridgeClient | None = None
_client_lock = threading.Lock()


def get_client() -> BridgeClient:
    global _client
    with _client_lock:
        if _client is None:
            # Local mode never asks Claude, so it only needs the events channel.
            _client = BridgeClient(url=BRIDGE_EVENTS_URL if BRAIN_MODE == "local" else BRIDGE_URL)
        return _client


def emit_event(kind: str, text: str | None = None, state: str | None = None,
               source: str | None = None) -> None:
    get_client().emit(kind, text=text, state=state, source=source)
