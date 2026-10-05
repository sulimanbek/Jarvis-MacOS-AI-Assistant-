import difflib
import re
import subprocess

from config import SUBPROCESS_TIMEOUT


def run_shortcut(shortcut_name: str, input_text: str = "", timeout: int = SUBPROCESS_TIMEOUT) -> bool:
    if not shortcut_name or not shortcut_name.strip():
        print("❌ No shortcut name provided.")
        return False

    cmd = ["shortcuts", "run", shortcut_name]

    if input_text:
        cmd.extend(["-i", input_text])

    print(f"🔧 Running shortcut: {shortcut_name}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        print("🔧 Return code:", result.returncode)
        if stdout:
            print("🔧 Output:", stdout)
        if stderr:
            print("⚠️ Error:", stderr)

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print("❌ Shortcut timed out.")
        return False

    except Exception as e:
        print(f"❌ Shortcut execution error: {e}")
        return False

# Words people say around a shortcut's name ("run the shortcut playlist").
_FILLER = {
    "run", "the", "a", "my", "shortcut", "shortcuts", "start", "execute", "trigger",
    "launch", "please", "called", "named", "for", "me", "open", "use",
}


def list_shortcuts(timeout: int = SUBPROCESS_TIMEOUT) -> list[str]:
    """Names of the shortcuts installed on this Mac (empty if it can't be read)."""
    try:
        result = subprocess.run(["shortcuts", "list"], capture_output=True, text=True, timeout=timeout)
    except Exception:
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


def match_shortcut(spoken: str, names: list[str]) -> str | None:
    """
    Pick the installed shortcut a spoken phrase refers to.

    "run the shortcut playlist" has to find the shortcut called "playlist": the
    Shortcuts app only runs an exact name, so passing the sentence along fails.
    """
    by_norm = {_norm(n): n for n in names if _norm(n)}
    if not by_norm:
        return None
    said = _norm(spoken)
    if said in by_norm:
        return by_norm[said]

    core = " ".join(w for w in said.split() if w not in _FILLER)
    if core in by_norm:
        return by_norm[core]

    # A shortcut's full name appearing inside the sentence; longest name first.
    for key in sorted(by_norm, key=len, reverse=True):
        if len(key) >= 3 and re.search(rf"\b{re.escape(key)}\b", said):
            return by_norm[key]

    close = difflib.get_close_matches(core, list(by_norm), n=1, cutoff=0.7)
    return by_norm[close[0]] if close else None
