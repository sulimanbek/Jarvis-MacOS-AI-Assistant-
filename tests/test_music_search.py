import music.search as search


def test_normalize_text_lowercases_strips_punctuation_and_collapses_whitespace():
    assert search.normalize_text('  Blinding LIGHTS, (feat. Someone)!!  ') == 'blinding lights feat someone'


def test_normalize_text_handles_none_and_empty_input():
    assert search.normalize_text(None) == ''
    assert search.normalize_text('') == ''


def test_closest_artist_matches_known_artist_exactly():
    assert search._closest_artist('Kendrick Lamar') == 'Kendrick Lamar'


def test_closest_artist_matches_misheard_variant_within_threshold():
    assert search._closest_artist('Kendric Lamr') == 'Kendrick Lamar'


def test_closest_artist_returns_none_when_too_far_off():
    assert search._closest_artist('a completely unrelated phrase') is None


def test_looks_like_artist_query_true_for_short_plain_name():
    assert search._looks_like_artist_query('Kendrick Lamar') is True


def test_looks_like_artist_query_false_for_query_over_four_words():
    assert search._looks_like_artist_query('kendrick lamar humble music video') is False


def test_looks_like_artist_query_false_when_contains_variant_keyword():
    assert search._looks_like_artist_query('kendrick lamar acoustic version') is False


def test_looks_like_artist_query_false_for_empty_text():
    assert search._looks_like_artist_query('') is False


def test_clean_query_strips_play_prefix():
    assert search._clean_query('play Humble') == 'Humble'


def test_clean_query_strips_the_song_prefix():
    assert search._clean_query('the song Humble') == 'Humble'


def test_clean_query_strips_song_prefix():
    assert search._clean_query('song Humble') == 'Humble'


def test_clean_query_strips_some_music_prefix():
    assert search._clean_query('some music Humble') == 'Humble'


def test_clean_query_strips_music_prefix():
    assert search._clean_query('music Humble') == 'Humble'


def test_clean_query_leaves_query_untouched_without_known_prefix():
    assert search._clean_query('Humble') == 'Humble'


def test_clean_query_strips_surrounding_quotes():
    assert search._clean_query('"Humble"') == 'Humble'


def test_apply_common_stt_corrections_replaces_alias_preserves_case_and_punctuation():
    result = search._apply_common_stt_corrections('Play some Kendric Lamar, please!')

    assert result == 'Play some Kendrick Lamar, please!'


def test_apply_common_stt_corrections_leaves_text_without_alias_untouched():
    text = 'Play some Bohemian Rhapsody, please!'

    assert search._apply_common_stt_corrections(text) == text


def test_parse_song_and_artist_song_by_artist_pattern():
    parsed = search.parse_song_and_artist('Humble by Kendrick Lamar')

    assert parsed.song == 'Humble'
    assert parsed.artist == 'Kendrick Lamar'
    assert parsed.intent == 'song'
    assert parsed.artist_normalized == 'kendrick lamar'


def test_parse_song_and_artist_by_artist_only_pattern():
    parsed = search.parse_song_and_artist('by Kendrick Lamar')

    assert parsed.artist == 'Kendrick Lamar'
    assert parsed.song == 'Kendrick Lamar'
    assert parsed.intent == 'artist'


def test_parse_song_and_artist_artist_only_short_query():
    parsed = search.parse_song_and_artist('Kendrick Lamar')

    assert parsed.intent == 'artist'
    assert parsed.artist == 'Kendrick Lamar'
    assert parsed.song == 'Kendrick Lamar'


def test_parse_song_and_artist_generic_song_only_query():
    parsed = search.parse_song_and_artist('bohemian rhapsody')

    assert parsed.intent == 'song'
    assert parsed.artist is None
    assert parsed.song == 'bohemian rhapsody'
    assert parsed.song_normalized == 'bohemian rhapsody'


def test_parse_song_and_artist_resolves_misheard_artist_alias_via_by_pattern():
    parsed = search.parse_song_and_artist('humble by kendric lamar')

    assert parsed.artist == 'Kendrick Lamar'
    assert parsed.song == 'humble'
    assert parsed.intent == 'song'


def test_parse_song_and_artist_resolves_misheard_artist_alias_as_artist_only():
    parsed = search.parse_song_and_artist('play kendric lamar')

    assert parsed.intent == 'artist'
    assert parsed.artist == 'Kendrick Lamar'
