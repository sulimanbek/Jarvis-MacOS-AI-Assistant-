import music.verify as verify


class FakeResult:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def test_normalize_text_strips_brackets_feat_and_punctuation():
    text = "Blinding Lights (Remastered) [Live] feat. Someone!"

    assert verify.normalize_text(text) == "blinding lights featuring someone"


def test_normalize_text_handles_none_input():
    assert verify.normalize_text(None) == ""


def test_text_matches_exact_match_is_true():
    assert verify._text_matches("Humble", "Humble") is True


def test_text_matches_substring_containment_true_when_actual_has_extra_suffix():
    assert verify._text_matches("Blinding Lights", "Blinding Lights - Remastered") is True


def test_text_matches_false_when_too_short_to_count_as_containment():
    # both sides shorter than the 4-char containment floor -> no match
    assert verify._text_matches("Hi", "Hi There") is False


def test_text_matches_false_positive_risk_with_short_generic_title():
    # Characterizes current (unintentional) behavior: a short, generic
    # requested title can match an unrelated track that merely contains it.
    assert verify._text_matches("Home", "Home Alone Theme") is True


def test_text_matches_false_when_neither_side_is_empty_after_normalization():
    assert verify._text_matches("", "Humble") is False
    assert verify._text_matches("Humble", "") is False


def test_get_current_track_info_returns_name_and_artist_on_success(monkeypatch):
    monkeypatch.setattr(
        verify, "run_applescript",
        lambda script: FakeResult(stdout="Humble||Kendrick Lamar", returncode=0),
    )

    name, artist = verify.get_current_track_info()

    assert (name, artist) == ("Humble", "Kendrick Lamar")


def test_get_current_track_info_returns_none_none_when_nothing_playing(monkeypatch):
    monkeypatch.setattr(
        verify, "run_applescript",
        lambda script: FakeResult(stdout="NO_TRACK", returncode=0),
    )

    assert verify.get_current_track_info() == (None, None)


def test_get_current_track_info_returns_none_none_on_nonzero_returncode(monkeypatch):
    monkeypatch.setattr(
        verify, "run_applescript",
        lambda script: FakeResult(stdout="Humble||Kendrick Lamar", returncode=1),
    )

    assert verify.get_current_track_info() == (None, None)


def test_get_current_track_info_returns_none_none_on_track_error(monkeypatch):
    monkeypatch.setattr(
        verify, "run_applescript",
        lambda script: FakeResult(stdout="TRACK_ERROR: boom", returncode=0),
    )

    assert verify.get_current_track_info() == (None, None)


def test_get_current_track_info_handles_missing_artist_separator(monkeypatch):
    monkeypatch.setattr(
        verify, "run_applescript",
        lambda script: FakeResult(stdout="Humble", returncode=0),
    )

    assert verify.get_current_track_info() == ("Humble", None)


def test_verify_requested_track_success_when_song_and_artist_match(monkeypatch):
    monkeypatch.setattr(verify, "get_current_track_info", lambda: ("Humble", "Kendrick Lamar"))

    result = verify.verify_requested_track("Humble", "Kendrick Lamar")

    assert result.success is True
    assert result.current_name == "Humble"
    assert result.current_artist == "Kendrick Lamar"


def test_verify_requested_track_fails_when_no_current_track(monkeypatch):
    monkeypatch.setattr(verify, "get_current_track_info", lambda: (None, None))

    result = verify.verify_requested_track("Humble", "Kendrick Lamar")

    assert result.success is False
    assert result.reason == "No current track detected."


def test_verify_requested_track_fails_when_song_title_does_not_match(monkeypatch):
    monkeypatch.setattr(verify, "get_current_track_info", lambda: ("Different Song", "Kendrick Lamar"))

    result = verify.verify_requested_track("Humble", "Kendrick Lamar")

    assert result.success is False
    assert result.reason == "Current track title does not match requested song."


def test_verify_requested_track_fails_when_artist_does_not_match(monkeypatch):
    monkeypatch.setattr(verify, "get_current_track_info", lambda: ("Humble", "Someone Else"))

    result = verify.verify_requested_track("Humble", "Kendrick Lamar")

    assert result.success is False
    assert result.reason == "Current track artist does not match requested artist."


def test_verify_requested_track_ignores_artist_when_none_requested(monkeypatch):
    monkeypatch.setattr(verify, "get_current_track_info", lambda: ("Humble", "Someone Else"))

    result = verify.verify_requested_track("Humble", None)

    assert result.success is True


def test_verify_requested_track_strict_mode_rejects_a_loose_partial_artist_match(monkeypatch):
    # "Lama" is a short partial match that non-strict containment (floor of 4
    # chars, either direction) accepts but strict mode (floor of 5 chars,
    # requested-in-actual only) rejects.
    monkeypatch.setattr(verify, "get_current_track_info", lambda: ("Humble", "Kendrick Lamar"))

    loose_result = verify.verify_requested_track("Humble", "Lama", strict_artist_match=False)
    strict_result = verify.verify_requested_track("Humble", "Lama", strict_artist_match=True)

    assert loose_result.success is True
    assert strict_result.success is False


def test_verify_requested_artist_success_on_match(monkeypatch):
    monkeypatch.setattr(verify, "get_current_track_info", lambda: ("Humble", "Kendrick Lamar"))

    result = verify.verify_requested_artist("Kendrick Lamar")

    assert result.success is True
    assert result.reason == "Artist playback verified successfully."


def test_verify_requested_artist_fails_when_no_current_track(monkeypatch):
    monkeypatch.setattr(verify, "get_current_track_info", lambda: (None, None))

    result = verify.verify_requested_artist("Kendrick Lamar")

    assert result.success is False
    assert result.reason == "No current track detected."


def test_verify_requested_artist_fails_on_mismatch(monkeypatch):
    monkeypatch.setattr(verify, "get_current_track_info", lambda: ("Humble", "Someone Else"))

    result = verify.verify_requested_artist("Kendrick Lamar")

    assert result.success is False
    assert result.reason == "Current track artist does not match requested artist."
