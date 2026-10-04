import memory.profile as profile


def _redirect(monkeypatch, tmp_path):
    path = tmp_path / "profile.json"
    monkeypatch.setattr(profile, "PROFILE_FILE", str(path))
    return path


def test_set_and_get_profile_value_round_trip(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    profile.set_profile_value("name", "Amena")

    assert profile.get_profile_value("name") == "Amena"


def test_get_profile_value_returns_default_when_missing(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    assert profile.get_profile_value("missing_key") is None
    assert profile.get_profile_value("missing_key", "fallback") == "fallback"


def test_get_all_profile_returns_full_dict(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    profile.set_profile_value("name", "Amena")
    profile.set_profile_value("city", "NYC")

    assert profile.get_all_profile() == {"name": "Amena", "city": "NYC"}


def test_get_all_profile_returns_empty_dict_when_no_file(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    assert profile.get_all_profile() == {}


def test_safe_read_does_not_raise_on_corrupt_file(monkeypatch, tmp_path):
    path = _redirect(monkeypatch, tmp_path)
    path.write_text("{not valid json", encoding="utf-8")

    data = profile._safe_read()

    assert data == {}
