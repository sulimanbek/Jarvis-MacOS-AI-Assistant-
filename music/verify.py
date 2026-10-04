import re

from music.models import PlaybackVerification
from services.applescript import run_applescript


def normalize_text(text: str) -> str:
    text = (text or "").strip().lower()

    # remove bracketed extras like (live), [remastered]
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"\[.*?\]", "", text)

    # normalize featuring variants
    text = re.sub(r"\bfeat\b\.?", "featuring", text)

    # remove punctuation
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def get_current_track_info():
    script = """
    tell application "Music"
        try
            if player state is playing or player state is paused then
                set trackName to name of current track
                set trackArtist to artist of current track
                return trackName & "||" & trackArtist
            else
                return "NO_TRACK"
            end if
        on error errMsg
            return "TRACK_ERROR: " & errMsg
        end try
    end tell
    """

    result = run_applescript(script)
    stdout = (result.stdout or "").strip()

    if result.returncode != 0:
        return None, None

    if not stdout or stdout == "NO_TRACK" or stdout.startswith("TRACK_ERROR:"):
        return None, None

    if "||" in stdout:
        name, artist = stdout.split("||", 1)
        return name.strip(), artist.strip()

    return stdout.strip(), None


def _text_matches(requested: str, actual: str) -> bool:
    requested_n = normalize_text(requested)
    actual_n = normalize_text(actual)

    if not requested_n or not actual_n:
        return False

    if requested_n == actual_n:
        return True

    if len(requested_n) >= 4 and requested_n in actual_n:
        return True

    return len(actual_n) >= 4 and actual_n in requested_n


def _strict_artist_matches(requested: str, actual: str) -> bool:
    requested_n = normalize_text(requested)
    actual_n = normalize_text(actual)

    if not requested_n or not actual_n:
        return False

    # strict mode prefers exact or very close containment only
    if requested_n == actual_n:
        return True

    return len(requested_n) >= 5 and requested_n in actual_n


def verify_requested_track(
    song: str,
    artist: str | None,
    strict_artist_match: bool = False,
) -> PlaybackVerification:
    current_name, current_artist = get_current_track_info()

    if not current_name:
        return PlaybackVerification(
            success=False,
            current_name=None,
            current_artist=None,
            reason="No current track detected."
        )

    song_ok = _text_matches(song, current_name)
    if not song_ok:
        return PlaybackVerification(
            success=False,
            current_name=current_name,
            current_artist=current_artist,
            reason="Current track title does not match requested song."
        )

    if artist:
        if strict_artist_match:
            artist_ok = _strict_artist_matches(artist, current_artist or "")
        else:
            artist_ok = _text_matches(artist, current_artist or "")

        if not artist_ok:
            return PlaybackVerification(
                success=False,
                current_name=current_name,
                current_artist=current_artist,
                reason="Current track artist does not match requested artist."
            )

    return PlaybackVerification(
        success=True,
        current_name=current_name,
        current_artist=current_artist,
        reason="Playback verified successfully."
    )


def verify_requested_artist(artist: str) -> PlaybackVerification:
    current_name, current_artist = get_current_track_info()

    if not current_name:
        return PlaybackVerification(
            success=False,
            current_name=None,
            current_artist=None,
            reason="No current track detected.",
        )

    artist_ok = _strict_artist_matches(artist, current_artist or "")
    if not artist_ok:
        return PlaybackVerification(
            success=False,
            current_name=current_name,
            current_artist=current_artist,
            reason="Current track artist does not match requested artist.",
        )

    return PlaybackVerification(
        success=True,
        current_name=current_name,
        current_artist=current_artist,
        reason="Artist playback verified successfully.",
    )