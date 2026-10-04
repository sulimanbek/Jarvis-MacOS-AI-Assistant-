import time

from music.search import build_search_decision, parse_song_and_artist
from music.verify import verify_requested_artist, verify_requested_track
from services.applescript import escape_applescript_text, run_applescript


def launch_music() -> bool:
    script = """
    tell application "Music"
        activate
    end tell

    delay 1.5

    tell application "System Events"
        if not (exists process "Music") then
            return "LAUNCH_ERROR: Music process not found."
        end if

        tell process "Music"
            set frontmost to true
            delay 1

            if (count of windows) is 0 then
                keystroke "1" using command down
                delay 1.5
            end if

            if (count of windows) is 0 then
                keystroke "0" using command down
                delay 1.5
            end if

            if (count of windows) is 0 then
                return "LAUNCH_ERROR: Music has no window."
            end if

            return "OK"
        end tell
    end tell
    """

    result = run_applescript(script)
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    print("🎵 Launch stdout:", stdout)
    print("🎵 Launch stderr:", stderr)
    print("🎵 Launch code:", result.returncode)

    if result.returncode != 0 or "LAUNCH_ERROR" in stdout:
        return False

    time.sleep(1.5)
    return True


def play_from_library(song: str, artist: str | None, strict_artist_match: bool = False) -> bool:
    safe_song = escape_applescript_text(song)
    safe_artist = escape_applescript_text(artist) if artist else None

    if safe_artist:
        script = f'''
        tell application "Music"
            try
                set exactMatches to (every track whose name is "{safe_song}" and artist is "{safe_artist}")
                if (count of exactMatches) > 0 then
                    play item 1 of exactMatches
                    return "OK_EXACT_ARTIST"
                end if

                set exactSongMatches to (every track whose name is "{safe_song}")
                if (count of exactSongMatches) > 0 then
                    play item 1 of exactSongMatches
                    return "OK_EXACT_SONG"
                end if

                set softMatches to (every track whose name contains "{safe_song}" and artist contains "{safe_artist}")
                if (count of softMatches) > 0 then
                    play item 1 of softMatches
                    return "OK_SOFT_ARTIST"
                end if

                return "NO_DIRECT_MATCH"
            on error errMsg
                return "DIRECT_ERROR: " & errMsg
            end try
        end tell
        '''
    else:
        script = f'''
        tell application "Music"
            try
                set exactSongMatches to (every track whose name is "{safe_song}")
                if (count of exactSongMatches) > 0 then
                    play item 1 of exactSongMatches
                    return "OK_EXACT_SONG"
                end if

                set softMatches to (every track whose name contains "{safe_song}")
                if (count of softMatches) is 1 then
                    play item 1 of softMatches
                    return "OK_SOFT_SONG"
                end if

                return "NO_DIRECT_MATCH"
            on error errMsg
                return "DIRECT_ERROR: " & errMsg
            end try
        end tell
        '''

    result = run_applescript(script)
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    print("🎵 Direct stdout:", stdout)
    print("🎵 Direct stderr:", stderr)
    print("🎵 Direct code:", result.returncode)

    if result.returncode != 0 or not stdout.startswith("OK_"):
        return False

    time.sleep(1.0)

    verification = verify_requested_track(
        song,
        artist,
        strict_artist_match=strict_artist_match,
    )

    print("🎵 Verification after library:", verification)

    return bool(getattr(verification, "success", False))


def search_and_play_in_apple_music(
    query: str,
    song: str,
    artist: str | None,
    strict_artist_match: bool = False,
    verify_by_artist_only: bool = False,
) -> bool:
    safe_query = escape_applescript_text(query)

    script = f'''
    tell application "Music"
        activate
    end tell

    delay 1.2

    tell application "System Events"
        if not (exists process "Music") then
            return "UI_ERROR: Music process not found."
        end if

        tell process "Music"
            set frontmost to true
            delay 1

            if (count of windows) is 0 then
                keystroke "1" using command down
                delay 1.5
            end if

            if (count of windows) is 0 then
                keystroke "0" using command down
                delay 1.5
            end if

            if (count of windows) is 0 then
                return "UI_ERROR: Music has no window."
            end if

            -- focus search
            keystroke "f" using command down
            delay 0.8

            -- clear previous query
            keystroke "a" using command down
            delay 0.2
            key code 51
            delay 0.3

            -- type query
            keystroke "{safe_query}"
            delay 2.8

            -- go directly into first visible result
            key code 125
            delay 0.6

            -- select result
            key code 36
            delay 1.0

            -- try play
            key code 49
            delay 1.2

            return "OK_UI"
        end tell
    end tell
    '''

    result = run_applescript(script)
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    print("🎵 UI stdout:", stdout)
    print("🎵 UI stderr:", stderr)
    print("🎵 UI code:", result.returncode)

    if result.returncode != 0 or "OK_UI" not in stdout:
        print("❌ Apple Music UI fallback failed:", stdout or stderr or "Unknown error")
        return False

    time.sleep(2.0)

    if verify_by_artist_only and artist:
        verification = verify_requested_artist(artist)
    else:
        verification = verify_requested_track(
            song,
            artist,
            strict_artist_match=strict_artist_match,
        )

    print("🎵 Verification after Apple Music UI:", verification)

    return bool(getattr(verification, "success", False))


def play_music_premium(query: str) -> bool:
    parsed = parse_song_and_artist(query)
    decision = build_search_decision(parsed)

    print(f"🎵 Requested query: {parsed.raw_query}")
    print(f"🎵 Parsed song: {parsed.song}")
    print(f"🎵 Parsed artist: {parsed.artist}")
    print(f"🎵 Parsed intent: {parsed.intent}")
    print(f"🎵 Search decision: {decision}")

    if not parsed.song:
        return False

    if not launch_music():
        print("❌ Failed to launch Music.")
        return False

    if getattr(decision, "should_try_library", False) and play_from_library(
        parsed.song,
        parsed.artist,
        strict_artist_match=getattr(decision, "strict_artist_match", False),
    ):
        print("✅ Playing from library.")
        return True

    if getattr(decision, "should_try_catalog_ui", False):
        print("🔎 No reliable library match. Searching Apple Music...")

        if search_and_play_in_apple_music(
            parsed.raw_query,
            parsed.song,
            parsed.artist,
            strict_artist_match=getattr(decision, "strict_artist_match", False),
            verify_by_artist_only=getattr(decision, "verify_by_artist_only", False),
        ):
            print("✅ Apple Music search/play verified.")
            return True

        print("⚠️ First UI attempt failed. Re-launching Music and retrying...")
        if launch_music() and search_and_play_in_apple_music(
            parsed.raw_query,
            parsed.song,
            parsed.artist,
            strict_artist_match=getattr(decision, "strict_artist_match", False),
            verify_by_artist_only=getattr(decision, "verify_by_artist_only", False),
        ):
            print("✅ Apple Music search/play verified on retry.")
            return True

    print("❌ Could not play from library or verified Apple Music search.")
    return False