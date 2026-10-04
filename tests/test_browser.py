import tools.browser as browser

DEFAULT_POLICY = {
    "trusted_web_targets": ["youtube", "github", "netflix", "google", "chatgpt", "linkedin"],
    "blocked_url_patterns": [
        r"^https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0)(?::\d+)?",
        r"^https?://(?:10\.\d+\.\d+\.\d+)",
        r"^https?://(?:192\.168\.\d+\.\d+)",
        r"^https?://(?:172\.(?:1[6-9]|2\d|3[0-1])\.\d+\.\d+)",
        r"^file://",
    ],
    "strip_tracking_params": ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"],
    "disable_unknown_site_search": True,
}


def _patch_policy(monkeypatch, overrides=None):
    policy = dict(DEFAULT_POLICY)
    if overrides:
        policy.update(overrides)
    monkeypatch.setattr(browser, "get_policy", lambda: policy)
    return policy


def test_is_blocked_direct_target_blocks_localhost(monkeypatch):
    _patch_policy(monkeypatch)
    assert browser._is_blocked_direct_target("http://localhost:8080/x") is True


def test_is_blocked_direct_target_blocks_rfc1918(monkeypatch):
    _patch_policy(monkeypatch)
    assert browser._is_blocked_direct_target("http://192.168.1.5/") is True
    assert browser._is_blocked_direct_target("http://10.0.0.5/") is True
    assert browser._is_blocked_direct_target("http://172.16.0.1/") is True


def test_is_blocked_direct_target_blocks_file_scheme(monkeypatch):
    _patch_policy(monkeypatch)
    assert browser._is_blocked_direct_target("file:///etc/passwd") is True


def test_is_blocked_direct_target_blocks_empty(monkeypatch):
    _patch_policy(monkeypatch)
    assert browser._is_blocked_direct_target("") is True
    assert browser._is_blocked_direct_target(None) is True


def test_is_blocked_direct_target_allows_normal_site(monkeypatch):
    _patch_policy(monkeypatch)
    assert browser._is_blocked_direct_target("youtube") is False


def test_sanitize_url_strips_tracking_params(monkeypatch):
    _patch_policy(monkeypatch)
    url = "https://example.com/page?utm_source=x&gclid=y&keep=1"
    result = browser._sanitize_url(url)
    assert "utm_source" not in result
    assert "gclid" not in result
    assert "keep=1" in result


def test_open_target_routes_direct_open_for_known_target(monkeypatch):
    _patch_policy(monkeypatch)
    captured = {}
    monkeypatch.setattr(browser.webbrowser, "open", lambda url: captured.setdefault("url", url) or True)

    result = browser.open_target("youtube")

    assert result is True
    assert captured["url"] == "https://youtube.com"


def test_open_target_routes_to_google_fallback_for_unknown_target(monkeypatch):
    _patch_policy(monkeypatch)
    captured = {}
    monkeypatch.setattr(browser.webbrowser, "open", lambda url: captured.setdefault("url", url) or True)

    result = browser.open_target("some random search term")

    assert result is True
    assert "google.com/search" in captured["url"]


def test_open_target_site_search_for_trusted_target_with_query(monkeypatch):
    _patch_policy(monkeypatch)
    captured = {}
    monkeypatch.setattr(browser.webbrowser, "open", lambda url: captured.setdefault("url", url) or True)

    result = browser.open_target("youtube", "cat videos")

    assert result is True
    assert "youtube.com/results" in captured["url"]


def test_open_target_blocks_untrusted_target_with_query(monkeypatch):
    _patch_policy(monkeypatch)
    called = {"n": 0}
    monkeypatch.setattr(browser.webbrowser, "open", lambda url: called.__setitem__("n", called["n"] + 1) or True)

    result = browser.open_target("some obscure site", "search term")

    assert result is False
    assert called["n"] == 0


def test_open_target_blocks_unsafe_direct_target(monkeypatch):
    _patch_policy(monkeypatch)
    called = {"n": 0}
    monkeypatch.setattr(browser.webbrowser, "open", lambda url: called.__setitem__("n", called["n"] + 1) or True)

    result = browser.open_target("http://localhost:9000/admin")

    assert result is False
    assert called["n"] == 0


def test_open_target_empty_target_returns_false(monkeypatch):
    _patch_policy(monkeypatch)
    assert browser.open_target("") is False
    assert browser.open_target(None) is False


def test_open_url_calls_webbrowser_open_and_ignores_falsy_return(monkeypatch):
    _patch_policy(monkeypatch)
    monkeypatch.setattr(browser.webbrowser, "open", lambda url: False)

    result = browser.open_url("youtube")

    assert result is False


def test_open_url_returns_false_for_unmapped_target(monkeypatch):
    _patch_policy(monkeypatch)
    monkeypatch.setattr(browser.webbrowser, "open", lambda url: True)

    assert browser.open_url("not a real site") is False


def test_open_search_calls_webbrowser_open_with_query(monkeypatch):
    _patch_policy(monkeypatch)
    captured = {}
    monkeypatch.setattr(browser.webbrowser, "open", lambda url: captured.setdefault("url", url) or True)

    result = browser.open_search("hello world")

    assert result is True
    assert "hello+world" in captured["url"]


def test_open_search_returns_false_for_empty_query(monkeypatch):
    _patch_policy(monkeypatch)
    assert browser.open_search("") is False
    assert browser.open_search(None) is False


def test_open_search_handles_webbrowser_exception(monkeypatch):
    _patch_policy(monkeypatch)

    def raise_open(url):
        raise RuntimeError("boom")

    monkeypatch.setattr(browser.webbrowser, "open", raise_open)

    assert browser.open_search("hello") is False
