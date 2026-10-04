import requests

import services.ollama_service as ollama_service


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", json_error=None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def _silence_sleep(monkeypatch):
    monkeypatch.setattr(ollama_service.time, "sleep", lambda *a, **k: None)


def test_is_ollama_running_true_on_200(monkeypatch):
    monkeypatch.setattr(ollama_service.requests, "get", lambda url, timeout=2: FakeResponse(status_code=200))

    assert ollama_service.is_ollama_running() is True


def test_is_ollama_running_true_on_404(monkeypatch):
    monkeypatch.setattr(ollama_service.requests, "get", lambda url, timeout=2: FakeResponse(status_code=404))

    assert ollama_service.is_ollama_running() is True


def test_is_ollama_running_false_on_connection_error(monkeypatch):
    def raise_error(url, timeout=2):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(ollama_service.requests, "get", raise_error)

    assert ollama_service.is_ollama_running() is False


def test_is_ollama_running_false_on_other_status(monkeypatch):
    monkeypatch.setattr(ollama_service.requests, "get", lambda url, timeout=2: FakeResponse(status_code=500))

    assert ollama_service.is_ollama_running() is False


def test_ask_ollama_success_via_chat_endpoint(monkeypatch):
    _silence_sleep(monkeypatch)

    def fake_post(url, json=None, timeout=None):
        assert url.endswith("/api/chat")
        return FakeResponse(status_code=200, json_data={"message": {"content": "hello there"}})

    monkeypatch.setattr(ollama_service.requests, "post", fake_post)

    result = ollama_service.ask_ollama([{"role": "user", "content": "hi"}])

    assert result == "hello there"


def test_ask_ollama_falls_back_to_generate_on_chat_404(monkeypatch):
    _silence_sleep(monkeypatch)
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append(url)
        if url.endswith("/api/chat"):
            return FakeResponse(status_code=404)
        return FakeResponse(status_code=200, json_data={"response": "fallback answer"})

    monkeypatch.setattr(ollama_service.requests, "post", fake_post)

    result = ollama_service.ask_ollama([{"role": "user", "content": "hi"}])

    assert result == "fallback answer"
    chat_calls = [c for c in calls if c.endswith("/api/chat")]
    assert len(chat_calls) == 1


def test_ask_ollama_handles_non_json_chat_response_gracefully(monkeypatch):
    _silence_sleep(monkeypatch)

    def fake_post(url, json=None, timeout=None):
        if url.endswith("/api/chat"):
            return FakeResponse(status_code=200, json_error=ValueError("not json"))
        return FakeResponse(status_code=200, json_data={"response": "generate saved the day"})

    monkeypatch.setattr(ollama_service.requests, "post", fake_post)

    result = ollama_service.ask_ollama([{"role": "user", "content": "hi"}])

    assert result == "generate saved the day"


def test_ask_ollama_returns_empty_string_when_both_endpoints_fail(monkeypatch):
    _silence_sleep(monkeypatch)

    def fake_post(url, json=None, timeout=None):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(ollama_service.requests, "post", fake_post)

    result = ollama_service.ask_ollama([{"role": "user", "content": "hi"}])

    assert result == ""


def test_ask_ollama_does_not_raise_when_generate_returns_non_json(monkeypatch):
    _silence_sleep(monkeypatch)

    def fake_post(url, json=None, timeout=None):
        if url.endswith("/api/chat"):
            return FakeResponse(status_code=404)
        return FakeResponse(status_code=200, json_error=ValueError("not json"))

    monkeypatch.setattr(ollama_service.requests, "post", fake_post)

    result = ollama_service.ask_ollama([{"role": "user", "content": "hi"}])

    assert result == ""
