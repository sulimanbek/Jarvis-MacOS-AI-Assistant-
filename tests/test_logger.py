import utils.logger as logger


def _redirect(monkeypatch, tmp_path):
    path = tmp_path / "actions.json"
    monkeypatch.setattr(logger, "ACTIONS_LOG_FILE", str(path))
    return path


def test_save_action_writes_entry_with_expected_fields(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    logger.save_action("app", "open safari", "success", details="opened Safari")

    entry = logger.get_last_action()

    assert entry["type"] == "app"
    assert entry["input"] == "open safari"
    assert entry["result"] == "success"
    assert entry["details"] == "opened Safari"
    assert "timestamp" in entry


def test_get_last_action_returns_none_when_log_empty(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    assert logger.get_last_action() is None


def test_get_last_successful_action_skips_failures(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    logger.save_action("app", "open broken", "failure")
    logger.save_action("app", "open safari", "success")
    logger.save_action("music", "play song", "failure")

    entry = logger.get_last_successful_action()

    assert entry["input"] == "open safari"
    assert entry["result"] == "success"


def test_get_last_successful_action_returns_none_when_all_failed(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    logger.save_action("app", "open broken", "failure")

    assert logger.get_last_successful_action() is None


def test_get_last_action_of_type_returns_matching_successful_entry(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    logger.save_action("app", "open safari", "success")
    logger.save_action("music", "play song", "success")
    logger.save_action("app", "open chrome", "success")
    logger.save_action("app", "open broken", "failure")

    entry = logger.get_last_action_of_type("app")

    assert entry["input"] == "open chrome"


def test_get_last_action_of_type_ignores_failed_entries_of_that_type(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    logger.save_action("app", "open safari", "success")
    logger.save_action("app", "open broken", "failure")

    entry = logger.get_last_action_of_type("app")

    assert entry["input"] == "open safari"


def test_get_last_action_of_type_returns_none_when_no_match(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    logger.save_action("music", "play song", "success")

    assert logger.get_last_action_of_type("app") is None


def test_get_unhandled_requests_filters_to_unhandled_type(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    logger.save_action("app", "open safari", "success")
    logger.save_action("unhandled", "do the impossible", "failure")
    logger.save_action("unhandled", "another weird request", "failure")

    unhandled = logger.get_unhandled_requests()

    assert len(unhandled) == 2
    assert all(item["type"] == "unhandled" for item in unhandled)


def test_get_unhandled_requests_respects_limit_and_returns_most_recent(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)

    for i in range(5):
        logger.save_action("unhandled", f"request {i}", "failure")

    unhandled = logger.get_unhandled_requests(limit=2)

    assert len(unhandled) == 2
    assert unhandled[0]["input"] == "request 3"
    assert unhandled[1]["input"] == "request 4"


def test_safe_read_does_not_raise_on_corrupt_file(monkeypatch, tmp_path):
    path = _redirect(monkeypatch, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")

    data = logger._safe_read()

    assert data == []
