import atexit
import os
import shutil

from dotenv import load_dotenv

load_dotenv()

from audio.ptt import record_push_to_talk, set_level_callback
from audio.tts import speak
from config import BRAIN_MODE, WHISPER_BIN, WHISPER_MODEL
from core.bridge_client import emit_event, get_client
from core.executor import execute
from core.level_stream import LevelStreamer
from core.mac_actions import set_confirmer
from core.router import route
from core.stt.whisper_cpp import transcribe
from memory.context import add_message
from security.policy import requires_confirmation as _policy_requires_confirmation
from services.ollama_service import ensure_ollama_running, is_ollama_running
from utils.logger import save_action

EXIT_COMMANDS = {"exit", "quit", "stop", "goodbye", "bye"}
CONFIRM_YES = {"yes", "yeah", "yep", "confirm", "do it", "go ahead", "proceed"}
CONFIRM_NO = {"no", "nope", "cancel", "stop", "dont", "don't"}


def _run_startup_health_checks() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    whisper_bin = os.path.expanduser(WHISPER_BIN)
    whisper_model = os.path.expanduser(WHISPER_MODEL)

    if not os.path.isfile(whisper_bin):
        errors.append(f"Whisper binary missing: {whisper_bin}")
    if not os.path.isfile(whisper_model):
        errors.append(f"Whisper model missing: {whisper_model}")

    if shutil.which("say") is None:
        errors.append("macOS 'say' command is unavailable.")
    if shutil.which("osascript") is None:
        errors.append("macOS 'osascript' command is unavailable.")
    if shutil.which("shortcuts") is None:
        warnings.append("macOS Shortcuts CLI not found. Shortcut commands may fail.")

    if not is_ollama_running():
        warnings.append("Ollama is not currently reachable.")

    return errors, warnings


def _listen_once_for_confirmation() -> str:
    audio, sr = record_push_to_talk()
    if getattr(audio, "size", 0) == 0:
        return ""
    try:
        return (transcribe(audio, sr) or "").strip().lower()
    except Exception:
        return ""


def _requires_confirmation(decision: dict) -> bool:
    return _policy_requires_confirmation(decision.get("tool"))


def _confirm_action(decision: dict) -> bool:
    tool = (decision.get("tool") or "action").strip()
    speak(f"Permission check. Should I proceed with {tool}? Say yes or no.")
    print(f"🔐 Awaiting confirmation for tool={tool}")

    heard = _listen_once_for_confirmation()
    if not heard:
        speak("No confirmation received. Cancelling.")
        return False

    if any(word in heard for word in CONFIRM_YES):
        return True

    if any(word in heard for word in CONFIRM_NO):
        speak("Action cancelled.")
        return False

    speak("I could not verify permission. Action cancelled.")
    return False


def main():
    print("🎙️ Hold RIGHT OPTION to talk...")
    errors, warnings = _run_startup_health_checks()
    for warning in warnings:
        print(f"⚠️ Health warning: {warning}")
    for error in errors:
        print(f"❌ Health error: {error}")

    if errors:
        speak("Startup checks failed. Please fix the environment before running commands.")
        return

    # Start Ollama automatically when Jarvis starts
    if ensure_ollama_running():
        speak("Jarvis ready.")
        print("✅ Ollama is running.")
    else:
        speak("Jarvis ready, but my local model could not be started.")
        print("❌ Ollama could not be started. Jarvis will still run for non-LLM commands.")

    # Lets Claude's mac_action requests ask you for a spoken yes before they run.
    set_confirmer(_confirm_action)

    # Your voice level for the HUD (a single number, never audio).
    levels = LevelStreamer()
    levels.start()
    atexit.register(levels.stop)
    set_level_callback(levels.push)
    if BRAIN_MODE == "claude":
        if get_client().warm():
            print("✅ Claude bridge connected.")
        else:
            print("⚠️ Claude bridge not reachable — using the local model.")
    emit_event("online", text="Jarvis online")

    while True:
        try:
            emit_event("state", state="idle")
            audio, sr = record_push_to_talk()

            if getattr(audio, "size", 0) == 0:
                continue

            try:
                user_text = transcribe(audio, sr)
            except Exception as e:
                print("❌ Transcription error:", e)
                save_action(
                    action_type="transcription",
                    user_input="",
                    result="failure",
                    details=str(e),
                )
                speak("I had trouble understanding you.")
                continue

            user_text = (user_text or "").strip()
            if not user_text:
                continue

            print("🧠 You said:", user_text)
            emit_event("heard", text=user_text)
            emit_event("state", state="thinking")
            add_message("user", user_text)

            lowered = user_text.lower().strip()
            if lowered in EXIT_COMMANDS:
                save_action(
                    action_type="system",
                    user_input=user_text,
                    result="success",
                    details="Exit command received",
                )
                speak("Goodbye.")
                break

            try:
                decision = route(user_text)
                print("⚙️ Decision:", decision)
            except Exception as e:
                print("❌ Routing error:", e)
                save_action(
                    action_type="routing",
                    user_input=user_text,
                    result="failure",
                    details=str(e),
                )
                speak("I had trouble deciding what to do.")
                continue

            if _requires_confirmation(decision) and not _confirm_action(decision):
                save_action(
                    action_type="security",
                    user_input=user_text,
                    result="failure",
                    details=f"Permission denied or missing for decision: {decision}",
                )
                continue

            try:
                result = execute(decision, user_text)
                response = (result.get("message") or "").strip()

                if not result.get("ok") and result.get("retryable"):
                    print(f"🔁 Retrying action once due to code={result.get('code')}")
                    retry_result = execute(decision, user_text)
                    if retry_result.get("ok"):
                        result = retry_result
                        response = (retry_result.get("message") or "").strip()

                if response:
                    print("🤖 Jarvis:", response)
                    add_message("assistant", response)
                    source = decision.get("_source") or ("local" if decision.get("tool") is None else "fast")
                    emit_event("reply", text=response, source=source)
                    emit_event("state", state="speaking")
                    speak(response)
                else:
                    speak("Done.")

            except Exception as e:
                print("❌ Execution error:", e)
                save_action(
                    action_type="execution",
                    user_input=user_text,
                    result="failure",
                    details=str(e),
                )
                speak("Something went wrong while executing that command.")

        except KeyboardInterrupt:
            speak("Goodbye.")
            break
        except Exception as e:
            print("❌ Fatal loop error:", e)
            save_action(
                action_type="system",
                user_input="",
                result="failure",
                details=str(e),
            )
            speak("Something unexpected went wrong.")


if __name__ == "__main__":
    main()

    