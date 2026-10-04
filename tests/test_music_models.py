from music.models import ParsedQuery, PlaybackVerification, SearchDecision


def test_parsed_query_defaults_when_only_required_fields_given():
    parsed = ParsedQuery(raw_query="humble", song="humble")

    assert parsed.artist is None
    assert parsed.intent == "song"
    assert parsed.song_normalized is None
    assert parsed.artist_normalized is None


def test_parsed_query_stores_all_fields_when_fully_specified():
    parsed = ParsedQuery(
        raw_query="humble by kendrick lamar",
        song="humble",
        artist="Kendrick Lamar",
        intent="song",
        song_normalized="humble",
        artist_normalized="kendrick lamar",
    )

    assert parsed == ParsedQuery(
        raw_query="humble by kendrick lamar",
        song="humble",
        artist="Kendrick Lamar",
        intent="song",
        song_normalized="humble",
        artist_normalized="kendrick lamar",
    )


def test_search_decision_defaults_are_false():
    decision = SearchDecision(
        should_try_library=True,
        should_try_catalog_ui=True,
        reason="song-only query",
    )

    assert decision.strict_artist_match is False
    assert decision.verify_by_artist_only is False


def test_search_decision_stores_all_fields_when_fully_specified():
    decision = SearchDecision(
        should_try_library=False,
        should_try_catalog_ui=True,
        reason="artist intent",
        strict_artist_match=True,
        verify_by_artist_only=True,
    )

    assert decision == SearchDecision(
        should_try_library=False,
        should_try_catalog_ui=True,
        reason="artist intent",
        strict_artist_match=True,
        verify_by_artist_only=True,
    )


def test_playback_verification_holds_success_and_track_details():
    verification = PlaybackVerification(
        success=True,
        current_name="Humble",
        current_artist="Kendrick Lamar",
        reason="Playback verified successfully.",
    )

    assert verification == PlaybackVerification(
        success=True,
        current_name="Humble",
        current_artist="Kendrick Lamar",
        reason="Playback verified successfully.",
    )


def test_playback_verification_allows_none_track_details_on_failure():
    verification = PlaybackVerification(
        success=False,
        current_name=None,
        current_artist=None,
        reason="No current track detected.",
    )

    assert verification.success is False
    assert verification.current_name is None
    assert verification.current_artist is None
