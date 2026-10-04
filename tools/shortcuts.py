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