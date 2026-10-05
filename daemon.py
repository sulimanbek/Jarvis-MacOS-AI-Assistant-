"""
daemon.py — always-on background Jarvis.

Trigger modes (both active simultaneously):
  1. Wake word  — say the configured wake word (default: "alexa")
  2. Double clap — two sharp claps within 700ms

Run:   python daemon.py
Stop:  say wake word → "goodbye", or Ctrl+C
"""

import os
import shutil

from dotenv import load_dotenv

load_dotenv()

from audio.listener import ContinuousListener
from audio.tts import speak, speak_ack
from config import BRAIN_MODE, WHISPER_BIN, WHISPER_MODEL
from core.agent import run_agent
from core.bridge_client import emit_event, get_client
from core.executor import execute
from core.level_stream import LevelStreamer
from core.mac_actions import set_confirmer
from core.router import route
from core.state_machine import JarvisState, State
from core.stt.whisper_cpp import transcribe
from memory.context import add_message
from security.policy import requires_confirmation as _policy_requires_confirmation
from services.ollama_service import ensure_ollama_running, is_ollama_running
from utils.logger import save_action

EXIT_COMMANDS = {"exit", "quit", "stop", "goodbye", "bye", "shut down", "shutdown"}
CONFIRM_YES   = {"yes", "yeah", "yep", "confirm", "do it", "go ahead", "proceed"}
CONFIRM_NO    = {"no",  "nope", "cancel", "stop",  "dont", "don't"}


# ── Startup ──────────────────────────────────────────────────────────────────

def _startup_checks() -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    if not os.path.isfile(os.path.expanduser(WHISPER_BIN)):
        errors.append(f"Whisper binary missing: {WHISPER_BIN}")
    if not os.path.isfile(os.path.expanduser(WHISPER_MODEL)):
        errors.append(f"Whisper model missing: {WHISPER_MODEL}")
    if shutil.which("say") is None:
        errors.append("macOS 'say' command unavailable.")
    if shutil.which("osascript") is None:
        errors.append("macOS 'osascript' unavailable.")
    if not is_ollama_running():
        warnings.append("Ollama not running — will attempt to start.")
    return errors, warnings


# ── Confirmation ─────────────────────────────────────────────────────────────

def _requires_confirmation(decision: dict) -> bool:
    return _policy_requires_confirmation(decision.get("tool"))


def _confirm_action(listener: ContinuousListener, decision: dict) -> bool:
    tool = (decision.get("tool") or "action").strip()
    speak(f"Should I proceed with {tool}? Say yes or no after the wake word.")
    print(f"🔐 Awaiting confirmation for tool={tool}")

    audio, sr = listener.listen_for_command()
    if audio.size == 0:
        speak("No confirmation received. Cancelling.")
        return False

    try:
        heard = (transcribe(audio, sr) or "").strip().lower()
    except Exception:
        speak("I couldn't hear your confirmation. Cancelling.")
        return False

    if any(w in heard for w in CONFIRM_YES):
        return True
    if any(w in heard for w in CONFIRM_NO):
        speak("Cancelled.")
        return False

    speak("Couldn't verify. Cancelling.")
    return False


# ── Main loop ─────────────────────────────────────────────────────────────────

def _process_command(user_text: str, listener: ContinuousListener):
    """Route, validate, and execute one command."""
    add_message("user", user_text)

    if user_text.lower().strip() in EXIT_COMMANDS:
        save_action("system", user_text, "success", "Exit command")
        speak("Goodbye.")
        return "exit"

    try:
        decision = route(user_text)
        print(f"⚙️  Decision: {decision}")
    except Exception as e:
        save_action("routing", user_text, "failure", str(e))
        speak("I had trouble deciding what to do.")
        return

    # Multi-step agent path — each planned step is confirmed individually
    # (via confirm_step) so high-risk tools (e.g. shortcuts) inside a plan
    # can't bypass the same policy gate single-tool execution uses below.
    if decision.get("tool") == "__agent__":
        def confirm_step(step_decision: dict) -> bool:
            if not _requires_confirmation(step_decision):
                return True
            if _confirm_action(listener, step_decision):
                return True
            save_action("security", user_text, "failure", f"Denied: {step_decision}")
            return False

        result = run_agent(user_text, confirm_step=confirm_step)
        add_message("assistant", result.get("message", ""))
        emit_event("reply", text=result.get("message", ""), source="agent")
        return

    # Confirmation gate (only for high-risk tools configured in policy.json)
    if _requires_confirmation(decision) and not _confirm_action(listener, decision):
        save_action("security", user_text, "failure", f"Denied: {decision}")
        return

    # Single-step execution
    speak_ack()

    try:
        result = execute(decision, user_text)
        if not result.get("ok") and result.get("retryable"):
            print("🔁 Retrying once...")
            result = execute(decision, user_text)

        response = (result.get("message") or "Done.").strip()
        print(f"🤖 Jarvis: {response}")
        add_message("assistant", response)
        source = decision.get("_source") or ("local" if decision.get("tool") is None else "fast")
        emit_event("reply", text=response, source=source)
        emit_event("state", state="speaking")
        speak(response)

    except Exception as e:
        save_action("execution", user_text, "failure", str(e))
        speak("Something went wrong.")


def main():
    errors, warnings = _startup_checks()
    for w in warnings:
        print(f"⚠️  {w}")
    for e in errors:
        print(f"❌ {e}")
    if errors:
        print("Fix the errors above then restart.")
        return

    if ensure_ollama_running():
        print("✅ Ollama running.")
    else:
        print("⚠️  Ollama could not start. Non-LLM commands will still work.")

    state    = JarvisState()
    levels   = LevelStreamer()
    levels.start()
    listener = ContinuousListener(
        on_triggered=lambda: emit_event("state", state="listening"),
        on_level=levels.push,
    )

    # Lets Claude's mac_action requests ask you for a spoken yes before they run.
    set_confirmer(lambda decision: _confirm_action(listener, decision))

    if BRAIN_MODE == "claude":
        if get_client().warm():
            print("✅ Claude bridge connected.")
        else:
            print("⚠️  Claude bridge not reachable — using the local model. "
                  "Start it with scripts/start_all.sh")
    emit_event("online", text="Jarvis online")

    speak("Jarvis online.")
    print("🟢 Jarvis running. Say the wake word or double-clap to activate.")

    try:
        while True:
            try:
                state.transition(State.IDLE)
                emit_event("state", state="idle")

                audio, sr = listener.listen_for_command()

                if audio.size == 0:
                    continue

                # ── Transcribe ────────────────────────────────────────────
                state.transition(State.PLANNING)
                emit_event("state", state="thinking")
                try:
                    user_text = transcribe(audio, sr)
                except Exception as e:
                    save_action("transcription", "", "failure", str(e))
                    speak("I had trouble understanding that.")
                    continue

                user_text = (user_text or "").strip()
                if not user_text:
                    continue

                print(f"🧠 You said: {user_text}")
                emit_event("heard", text=user_text)

                # ── Execute ───────────────────────────────────────────────
                state.transition(State.EXECUTING)
                outcome = _process_command(user_text, listener)

                state.transition(State.SPEAKING)

                if outcome == "exit":
                    break

            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"❌ Fatal loop error: {e}")
                save_action("system", "", "failure", str(e))
                speak("Something unexpected went wrong.")

    except KeyboardInterrupt:
        speak("Goodbye.")
    finally:
        levels.stop()
        listener.stop()


if __name__ == "__main__":
    main()
