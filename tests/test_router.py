import core.router as router


def _clear_memory(monkeypatch):
    monkeypatch.setattr(router, "get_last_song", lambda: None)
    monkeypatch.setattr(router, "get_last_app", lambda: None)
    monkeypatch.setattr(router, "get_last_browser_target", lambda: None)
    monkeypatch.setattr(router, "get_last_shortcut", lambda: None)
    monkeypatch.setattr(router, "get_last_action", lambda: {})


# --- Fast-path regex matches --------------------------------------------

def test_route_play_query_returns_music_tool(monkeypatch):
    _clear_memory(monkeypatch)
    result = router.route("play Starboy")
    assert result == {"tool": "music", "query": "Starboy"}


def test_route_open_known_app_returns_app_tool(monkeypatch):
    _clear_memory(monkeypatch)
    result = router.route("open safari")
    assert result == {"tool": "app", "name": "Safari"}


def test_route_volume_up_returns_system_tool(monkeypatch):
    _clear_memory(monkeypatch)
    result = router.route("turn the volume up")
    assert result == {"tool": "system", "action": "volume_up"}


def test_route_memory_query_what_was_that_song(monkeypatch):
    _clear_memory(monkeypatch)
    monkeypatch.setattr(router, "get_last_song", lambda: "Starboy")
    result = router.route("what was that song")
    assert result == {"tool": None, "response": "The last song was Starboy."}


# --- Multi-step detection -------------------------------------------------

def test_route_multi_step_command_routes_to_agent(monkeypatch):
    _clear_memory(monkeypatch)
    result = router.route("open Safari and then play some music")
    assert result == {"tool": "__agent__", "text": "open Safari and then play some music"}


def test_is_multi_step_true_for_sequence_phrase():
    assert router._is_multi_step("open safari and then play music") is True


def test_is_multi_step_true_for_two_verbs_with_and():
    assert router._is_multi_step("open safari and play some music") is True


def test_is_multi_step_false_for_single_action():
    assert router._is_multi_step("play some music") is False


# --- Fuzzy matching ---------------------------------------------------

def test_fuzzy_match_tolerates_mishearing_within_threshold():
    assert router._fuzzy_match("saffari", ["safari", "spotify"]) == "safari"


def test_fuzzy_match_returns_none_for_short_target():
    assert router._fuzzy_match("ab", ["safari"]) is None


def test_fuzzy_match_returns_none_when_below_cutoff():
    assert router._fuzzy_match("xyzzyplugh", ["safari", "spotify"]) is None


def test_route_open_target_uses_fuzzy_match_for_app(monkeypatch):
    _clear_memory(monkeypatch)
    result = router.route("open saffari")
    assert result == {"tool": "app", "name": "Safari"}


# --- _route_memory: valid and malformed/missing state ----------------------

def test_route_memory_repeat_music_with_known_last_song(monkeypatch):
    _clear_memory(monkeypatch)
    monkeypatch.setattr(router, "get_last_song", lambda: "Starboy")
    result = router._route_memory("play that again")
    assert result == {"tool": "music", "query": "Starboy"}


def test_route_memory_repeat_music_without_last_song_is_unhandled(monkeypatch):
    _clear_memory(monkeypatch)
    result = router._route_memory("play that again")
    assert result == {
        "tool": None,
        "response": "I don't know which song you mean yet.",
        "_unhandled_reason": "music_memory_missing",
    }


def test_route_memory_do_that_again_with_malformed_action_state(monkeypatch):
    _clear_memory(monkeypatch)
    # Malformed: action type present but no value
    monkeypatch.setattr(router, "get_last_action", lambda: {"type": "app"})
    result = router._route_memory("do that again")
    assert result == {
        "tool": None,
        "response": "I don't remember the last action yet.",
        "_unhandled_reason": "action_memory_missing",
    }


def test_route_memory_do_that_again_with_valid_state(monkeypatch):
    _clear_memory(monkeypatch)
    monkeypatch.setattr(router, "get_last_action", lambda: {"type": "browser", "value": "youtube"})
    result = router._route_memory("do that again")
    assert result == {"tool": "browser", "target": "youtube"}


def test_route_memory_open_last_app_missing_returns_unhandled(monkeypatch):
    _clear_memory(monkeypatch)
    result = router._route_memory("open the last app")
    assert result == {
        "tool": None,
        "response": "I don't remember the last app yet.",
        "_unhandled_reason": "app_memory_missing",
    }


def test_route_memory_returns_none_when_no_memory_phrase_matches(monkeypatch):
    _clear_memory(monkeypatch)
    assert router._route_memory("what time is it") is None


# --- LLM fallback path ------------------------------------------------

def test_route_falls_back_to_llm_when_no_fast_path_matches(monkeypatch):
    _clear_memory(monkeypatch)
    monkeypatch.setattr(router, "think_local", lambda text: {"tool": "app", "name": "Notes"})
    result = router.route("please pull up my notes application for me")
    assert result == {"tool": "app", "name": "Notes"}


def test_route_llm_fallback_handles_conversational_response(monkeypatch):
    _clear_memory(monkeypatch)
    monkeypatch.setattr(router, "think_local", lambda text: {"tool": None, "response": "I'm doing well, thanks."})
    result = router.route("how are you feeling today")
    assert result == {"tool": None, "response": "I'm doing well, thanks."}


def test_route_llm_fallback_rejects_disallowed_tool(monkeypatch):
    _clear_memory(monkeypatch)
    monkeypatch.setattr(router, "think_local", lambda text: {"tool": "shell", "command": "rm -rf /"})
    result = router.route("do something dangerous")
    assert result == {
        "tool": None,
        "response": "I had trouble deciding what to do.",
        "_unhandled_reason": "disallowed_tool",
    }
