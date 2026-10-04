import subprocess

from config import SUBPROCESS_TIMEOUT


def run_applescript(script: str, timeout: int = SUBPROCESS_TIMEOUT):
    """
    Run an AppleScript string through osascript.

    Returns:
        subprocess.CompletedProcess
    """
    try:
        return subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print("❌ AppleScript timed out.")
        raise
    except Exception as e:
        print(f"❌ AppleScript execution error: {e}")
        raise


def escape_applescript_text(text: str) -> str:
    """
    Escape text safely for embedding inside AppleScript string literals.
    """
    return (text or "").replace("\\", "\\\\").replace('"', '\\"')