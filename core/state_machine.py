"""
core/state_machine.py

Thread-safe state tracker for the Jarvis daemon.
Prevents concurrent activations — if Jarvis is already executing,
a new trigger is ignored until it returns to IDLE.
"""

import threading
from enum import Enum, auto


class State(Enum):
    IDLE      = auto()   # waiting for trigger
    TRIGGERED = auto()   # trigger received, about to listen
    LISTENING = auto()   # recording audio
    PLANNING  = auto()   # routing / building plan
    EXECUTING = auto()   # running tool(s)
    SPEAKING  = auto()   # TTS playing response


class JarvisState:
    def __init__(self):
        self._state = State.IDLE
        self._lock  = threading.Lock()

    @property
    def current(self) -> State:
        with self._lock:
            return self._state

    def transition(self, new_state: State):
        with self._lock:
            old = self._state
            self._state = new_state
        print(f"[State] {old.name} → {new_state.name}")

    def is_idle(self) -> bool:
        return self.current == State.IDLE

    def is_busy(self) -> bool:
        return self.current != State.IDLE
