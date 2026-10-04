from services.applescript import escape_applescript_text, run_applescript


def add_reminder(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False

    safe_text = escape_applescript_text(text)
    script = f'''
    tell application "Reminders"
        tell default list
            make new reminder with properties {{name:"{safe_text}"}}
        end tell
    end tell
    '''

    result = run_applescript(script)
    if result.returncode != 0:
        print("❌ Reminders error:", (result.stderr or "").strip())
        return False
    return True
