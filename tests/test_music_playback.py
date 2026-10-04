import music.playback as playback
from music.models import ParsedQuery, PlaybackVerification, SearchDecision


class FakeResult:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def _no_delay(monkeypatch):
    monkeypatch.setattr(playback.time, "sleep", lambda *a, **k: None)


def _capture_applescript(monkeypatch, result):
    calls = []

    def fake_run(script, *a, **k):
        calls.append(script)
        return result

    monkeypatch.setattr(playback, "run_applescript", fake_run)
    return calls


# ---------------------------------------------------------------------------
# launch_music
# ---------------------------------------------------------------------------

def test_launch_music_returns_true_when_applescript_reports_ok(monkeypatch):
    _no_delay(monkeypatch)
    monkeypatch.setattr(playback, "run_applescript", lambda script: FakeResult(stdout="OK", returncode=0))

    assert playback.launch_music() is True


def test_launch_music_returns_false_on_launch_error_stdout(monkeypatch):
    _no_delay(monkeypatch)
    monkeypatch.setattr(
        playback, "run_applescript",
        lambda script: FakeResult(stdout="LAUNCH_ERROR: Music has no window.", returncode=0),
    )

    assert playback.launch_music() is False


def test_launch_music_returns_false_on_nonzero_returncode(monkeypatch):
    _no_delay(monkeypatch)
    monkeypatch.setattr(playback, "run_applescript", lambda script: FakeResult(stdout="OK", returncode=1))

    assert playback.launch_music() is False


# ---------------------------------------------------------------------------
# play_from_library
# ---------------------------------------------------------------------------

def test_play_from_library_returns_true_on_soft_match_with_successful_verification(monkeypatch):
    _no_delay(monkeypatch)
    monkeypatch.setattr(playback, "run_applescript", lambda script: FakeResult(stdout="OK_SOFT_ARTIST", returncode=0))
    monkeypatch.setattr(
        playback, "verify_requested_track",
        lambda song, artist, strict_artist_match=False: PlaybackVerification(
            success=True, current_name=song, current_artist=artist, reason="ok",
        ),
    )

    assert playback.play_from_library("Humble", "Kendrick Lamar") is True


def test_play_from_library_returns_false_when_no_direct_match_found(monkeypatch):
    _no_delay(monkeypatch)
    monkeypatch.setattr(playback, "run_applescript", lambda script: FakeResult(stdout="NO_DIRECT_MATCH", returncode=0))
    monkeypatch.setattr(playback, "verify_requested_track", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("verification should not run when there was no direct match")
    ))

    assert playback.play_from_library("Humble", "Kendrick Lamar") is False


def test_play_from_library_returns_false_when_ambiguous_soft_song_match_count_is_not_one(monkeypatch):
    # No artist given: the AppleScript branch only counts a soft song match as
    # usable when exactly one track matches, so an ambiguous ("NO_DIRECT_MATCH")
    # result must short-circuit before verification.
    _no_delay(monkeypatch)
    monkeypatch.setattr(playback, "run_applescript", lambda script: FakeResult(stdout="NO_DIRECT_MATCH", returncode=0))

    called = {"n": 0}
    monkeypatch.setattr(playback, "verify_requested_track", lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    result = playback.play_from_library("Humble", None)

    assert result is False
    assert called["n"] == 0


def test_play_from_library_returns_false_on_nonzero_returncode(monkeypatch):
    _no_delay(monkeypatch)
    monkeypatch.setattr(playback, "run_applescript", lambda script: FakeResult(stdout="OK_EXACT_SONG", returncode=1))

    assert playback.play_from_library("Humble", None) is False


def test_play_from_library_returns_false_when_verification_fails_despite_ok_stdout(monkeypatch):
    _no_delay(monkeypatch)
    monkeypatch.setattr(playback, "run_applescript", lambda script: FakeResult(stdout="OK_EXACT_ARTIST", returncode=0))
    monkeypatch.setattr(
        playback, "verify_requested_track",
        lambda song, artist, strict_artist_match=False: PlaybackVerification(
            success=False, current_name="Other", current_artist="Other Artist", reason="mismatch",
        ),
    )

    assert playback.play_from_library("Humble", "Kendrick Lamar") is False


def test_play_from_library_escapes_song_and_artist_into_applescript(monkeypatch):
    _no_delay(monkeypatch)
    calls = _capture_applescript(monkeypatch, FakeResult(stdout="OK_EXACT_ARTIST", returncode=0))
    monkeypatch.setattr(
        playback, "verify_requested_track",
        lambda song, artist, strict_artist_match=False: PlaybackVerification(
            success=True, current_name=song, current_artist=artist, reason="ok",
        ),
    )

    playback.play_from_library('Song "Title"', 'Artist "Name"')

    assert len(calls) == 1
    assert 'Song \\"Title\\"' in calls[0]
    assert 'Artist \\"Name\\"' in calls[0]


def test_play_from_library_builds_song_only_script_when_no_artist_given(monkeypatch):
    _no_delay(monkeypatch)
    calls = _capture_applescript(monkeypatch, FakeResult(stdout="OK_EXACT_SONG", returncode=0))
    monkeypatch.setattr(
        playback, "verify_requested_track",
        lambda song, artist, strict_artist_match=False: PlaybackVerification(
            success=True, current_name=song, current_artist=None, reason="ok",
        ),
    )

    playback.play_from_library("Humble", None)

    assert len(calls) == 1
    assert "artist is" not in calls[0]
    assert "Humble" in calls[0]


# ---------------------------------------------------------------------------
# search_and_play_in_apple_music
# ---------------------------------------------------------------------------

def test_search_and_play_escapes_query_into_applescript(monkeypatch):
    _no_delay(monkeypatch)
    calls = _capture_applescript(monkeypatch, FakeResult(stdout="OK_UI", returncode=0))
    monkeypatch.setattr(
        playback, "verify_requested_track",
        lambda song, artist, strict_artist_match=False: PlaybackVerification(
            success=True, current_name=song, current_artist=artist, reason="ok",
        ),
    )

    playback.search_and_play_in_apple_music('Song "Title" by Artist', "Song Title", "Artist")

    assert len(calls) == 1
    assert 'Song \\"Title\\" by Artist' in calls[0]


def test_search_and_play_returns_false_when_ui_error_reported(monkeypatch):
    _no_delay(monkeypatch)
    monkeypatch.setattr(playback, "run_applescript", lambda script: FakeResult(stdout="UI_ERROR: no window", returncode=0))

    assert playback.search_and_play_in_apple_music("Humble", "Humble", None) is False


def test_search_and_play_returns_false_on_nonzero_returncode(monkeypatch):
    _no_delay(monkeypatch)
    monkeypatch.setattr(playback, "run_applescript", lambda script: FakeResult(stdout="OK_UI", returncode=1))

    assert playback.search_and_play_in_apple_music("Humble", "Humble", None) is False


def test_search_and_play_verifies_by_artist_only_when_flagged(monkeypatch):
    _no_delay(monkeypatch)
    monkeypatch.setattr(playback, "run_applescript", lambda script: FakeResult(stdout="OK_UI", returncode=0))

    calls = {"artist_only": 0, "track": 0}
    monkeypatch.setattr(
        playback, "verify_requested_artist",
        lambda artist: (calls.__setitem__("artist_only", calls["artist_only"] + 1) or
                        PlaybackVerification(success=True, current_name="x", current_artist=artist, reason="ok")),
    )
    monkeypatch.setattr(
        playback, "verify_requested_track",
        lambda *a, **k: (calls.__setitem__("track", calls["track"] + 1) or
                         PlaybackVerification(success=True, current_name="x", current_artist="y", reason="ok")),
    )

    result = playback.search_and_play_in_apple_music(
        "Kendrick Lamar", "Kendrick Lamar", "Kendrick Lamar", verify_by_artist_only=True,
    )

    assert result is True
    assert calls["artist_only"] == 1
    assert calls["track"] == 0


def test_search_and_play_verifies_by_track_when_artist_only_flag_not_set(monkeypatch):
    _no_delay(monkeypatch)
    monkeypatch.setattr(playback, "run_applescript", lambda script: FakeResult(stdout="OK_UI", returncode=0))

    calls = {"artist_only": 0, "track": 0}
    monkeypatch.setattr(
        playback, "verify_requested_artist",
        lambda artist: (calls.__setitem__("artist_only", calls["artist_only"] + 1) or
                        PlaybackVerification(success=True, current_name="x", current_artist=artist, reason="ok")),
    )
    monkeypatch.setattr(
        playback, "verify_requested_track",
        lambda *a, **k: (calls.__setitem__("track", calls["track"] + 1) or
                         PlaybackVerification(success=True, current_name="x", current_artist="y", reason="ok")),
    )

    result = playback.search_and_play_in_apple_music(
        "Humble by Kendrick Lamar", "Humble", "Kendrick Lamar", verify_by_artist_only=False,
    )

    assert result is True
    assert calls["artist_only"] == 0
    assert calls["track"] == 1


# ---------------------------------------------------------------------------
# play_music_premium (pure orchestration -- safe to test with everything mocked)
# ---------------------------------------------------------------------------

def test_play_music_premium_returns_false_when_parsed_song_is_empty(monkeypatch):
    monkeypatch.setattr(playback, "parse_song_and_artist", lambda query: ParsedQuery(raw_query=query, song=""))
    monkeypatch.setattr(playback, "build_search_decision", lambda parsed: SearchDecision(
        should_try_library=True, should_try_catalog_ui=True, reason="x",
    ))

    assert playback.play_music_premium("   ") is False


def test_play_music_premium_returns_false_when_launch_music_fails(monkeypatch):
    monkeypatch.setattr(playback, "parse_song_and_artist", lambda query: ParsedQuery(raw_query=query, song="Humble"))
    monkeypatch.setattr(playback, "build_search_decision", lambda parsed: SearchDecision(
        should_try_library=True, should_try_catalog_ui=True, reason="x",
    ))
    monkeypatch.setattr(playback, "launch_music", lambda: False)

    assert playback.play_music_premium("play humble") is False


def test_play_music_premium_succeeds_via_library_match_without_trying_catalog_ui(monkeypatch):
    monkeypatch.setattr(playback, "parse_song_and_artist", lambda query: ParsedQuery(raw_query=query, song="Humble"))
    monkeypatch.setattr(playback, "build_search_decision", lambda parsed: SearchDecision(
        should_try_library=True, should_try_catalog_ui=True, reason="x",
    ))
    monkeypatch.setattr(playback, "launch_music", lambda: True)
    monkeypatch.setattr(playback, "play_from_library", lambda song, artist, strict_artist_match=False: True)

    def fail_if_called(*a, **k):
        raise AssertionError("catalog UI search should not run when the library match already succeeded")

    monkeypatch.setattr(playback, "search_and_play_in_apple_music", fail_if_called)

    assert playback.play_music_premium("play humble") is True


def test_play_music_premium_falls_back_to_catalog_ui_when_library_match_fails(monkeypatch):
    monkeypatch.setattr(playback, "parse_song_and_artist", lambda query: ParsedQuery(raw_query=query, song="Humble"))
    monkeypatch.setattr(playback, "build_search_decision", lambda parsed: SearchDecision(
        should_try_library=True, should_try_catalog_ui=True, reason="x",
    ))
    monkeypatch.setattr(playback, "launch_music", lambda: True)
    monkeypatch.setattr(playback, "play_from_library", lambda song, artist, strict_artist_match=False: False)
    monkeypatch.setattr(
        playback, "search_and_play_in_apple_music",
        lambda query, song, artist, strict_artist_match=False, verify_by_artist_only=False: True,
    )

    assert playback.play_music_premium("play humble") is True


def test_play_music_premium_retries_ui_search_after_relaunch_when_first_attempt_fails(monkeypatch):
    monkeypatch.setattr(playback, "parse_song_and_artist", lambda query: ParsedQuery(raw_query=query, song="Humble"))
    monkeypatch.setattr(playback, "build_search_decision", lambda parsed: SearchDecision(
        should_try_library=False, should_try_catalog_ui=True, reason="x",
    ))

    launch_calls = {"n": 0}
    monkeypatch.setattr(playback, "launch_music", lambda: launch_calls.__setitem__("n", launch_calls["n"] + 1) or True)

    ui_calls = {"n": 0}

    def fake_ui(query, song, artist, strict_artist_match=False, verify_by_artist_only=False):
        ui_calls["n"] += 1
        return ui_calls["n"] > 1  # fail first time, succeed on retry

    monkeypatch.setattr(playback, "search_and_play_in_apple_music", fake_ui)

    result = playback.play_music_premium("play humble")

    assert result is True
    assert launch_calls["n"] == 2
    assert ui_calls["n"] == 2


def test_play_music_premium_returns_false_when_all_attempts_fail(monkeypatch):
    monkeypatch.setattr(playback, "parse_song_and_artist", lambda query: ParsedQuery(raw_query=query, song="Humble"))
    monkeypatch.setattr(playback, "build_search_decision", lambda parsed: SearchDecision(
        should_try_library=True, should_try_catalog_ui=True, reason="x",
    ))
    monkeypatch.setattr(playback, "launch_music", lambda: True)
    monkeypatch.setattr(playback, "play_from_library", lambda song, artist, strict_artist_match=False: False)
    monkeypatch.setattr(
        playback, "search_and_play_in_apple_music",
        lambda query, song, artist, strict_artist_match=False, verify_by_artist_only=False: False,
    )

    assert playback.play_music_premium("play humble") is False
