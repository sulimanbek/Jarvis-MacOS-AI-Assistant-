import tools.music as music


def test_play_music_any_delegates_to_play_music_premium_success(monkeypatch):
    captured = {}

    def fake_play(query):
        captured["query"] = query
        return True

    monkeypatch.setattr(music, "play_music_premium", fake_play)

    result = music.play_music_any("Starboy")

    assert result is True
    assert captured["query"] == "Starboy"


def test_play_music_any_returns_false_when_premium_playback_fails(monkeypatch):
    monkeypatch.setattr(music, "play_music_premium", lambda query: False)

    result = music.play_music_any("some obscure song")

    assert result is False


def test_play_music_any_swallows_exceptions_gracefully(monkeypatch):
    def raise_error(query):
        raise RuntimeError("boom")

    monkeypatch.setattr(music, "play_music_premium", raise_error)

    result = music.play_music_any("Starboy")

    assert result is False


def test_play_music_any_returns_false_for_empty_query():
    assert music.play_music_any("") is False
    assert music.play_music_any(None) is False


def test_play_music_any_strips_query_before_delegating(monkeypatch):
    captured = {}

    def fake_play(query):
        captured["query"] = query
        return True

    monkeypatch.setattr(music, "play_music_premium", fake_play)

    music.play_music_any("  Starboy  ")

    assert captured["query"] == "Starboy"
