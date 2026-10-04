from services.applescript import escape_applescript_text, run_applescript


def add_note(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False

    safe_text = escape_applescript_text(text)
    script = f'''
    tell application "Notes"
        make new note with properties {{body:"{safe_text}"}}
    end tell
    '''

    result = run_applescript(script)
    if result.returncode != 0:
        print("❌ Notes error:", (result.stderr or "").strip())
        return False
    return True
