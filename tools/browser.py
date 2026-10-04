import re
import webbrowser
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse

from security.policy import get_policy

WEB_TARGETS = {
    "youtube": "https://youtube.com",
    "you tube": "https://youtube.com",
    "youtube.com": "https://youtube.com",

    "github": "https://github.com",
    "github.com": "https://github.com",

    "netflix": "https://netflix.com",
    "netflix.com": "https://netflix.com",

    "google": "https://google.com",
    "google.com": "https://google.com",

    "chatgpt": "https://chatgpt.com",
    "chat g p t": "https://chatgpt.com",
    "chatgpt.com": "https://chatgpt.com",

    "tradingview": "https://tradingview.com",
    "trading view": "https://tradingview.com",
    "tradingview.com": "https://tradingview.com",

    "gmail": "https://mail.google.com",
    "google mail": "https://mail.google.com",
    "mail": "https://mail.google.com",

    "linkedin": "https://linkedin.com",
    "linked in": "https://linkedin.com",
    "linkedin.com": "https://linkedin.com",

    "etoro": "https://www.etoro.com",
    "e toro": "https://www.etoro.com",
    "e-toro": "https://www.etoro.com",
    "etoro.com": "https://www.etoro.com",
}

SITE_SEARCH_URLS = {
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "you tube": "https://www.youtube.com/results?search_query={query}",
    "youtube.com": "https://www.youtube.com/results?search_query={query}",
    "github": "https://github.com/search?q={query}",
    "github.com": "https://github.com/search?q={query}",
    "linkedin": "https://www.linkedin.com/search/results/all/?keywords={query}",
    "linkedin.com": "https://www.linkedin.com/search/results/all/?keywords={query}",
    "google": "https://www.google.com/search?q={query}",
    "google.com": "https://www.google.com/search?q={query}",
}

def clean_target(text: str) -> str:
    text = (text or "").strip().lower()
    text = text.rstrip(".,!?;:")
    text = text.replace("www.", "")
    text = re.sub(r"^the\s+", "", text)
    text = re.sub(r"\s+website$", "", text)
    text = re.sub(r"\s+site$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_blocked_direct_target(target: str) -> bool:
    policy = get_policy()
    blocked_patterns = policy.get("blocked_url_patterns", [])
    target = (target or "").strip().lower()
    if not target:
        return True
    return any(re.match(pattern, target) for pattern in blocked_patterns)


def _sanitize_url(url: str) -> str:
    policy = get_policy()
    blocked = {p.lower() for p in policy.get("strip_tracking_params", [])}

    parsed = urlparse(url)
    kept = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() not in blocked:
            kept.append((key, value))

    sanitized_query = urlencode(kept, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, sanitized_query, ""))


def _is_trusted_target(target: str) -> bool:
    policy = get_policy()
    trusted = {clean_target(t) for t in policy.get("trusted_web_targets", [])}
    return clean_target(target) in trusted


def open_url(target: str) -> bool:
    target = clean_target(target)
    url = WEB_TARGETS.get(target)

    if not url:
        print(f"❌ No URL mapping found for target: {target}")
        return False

    try:
        ok = webbrowser.open(_sanitize_url(url))
        print(f"🔗 Opened URL for target '{target}': {url}")
        return bool(ok)
    except Exception as e:
        print(f"❌ URL open error: {e}")
        return False


def open_search(query: str) -> bool:
    query = (query or "").strip()
    if not query:
        return False

    try:
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        ok = webbrowser.open(_sanitize_url(url))
        print(f"🔎 Searching for: {query}")
        return bool(ok)
    except Exception as e:
        print(f"❌ Search error: {e}")
        return False


def open_site_search(target: str, query: str) -> bool:
    target = clean_target(target)
    query = (query or "").strip()
    if not target or not query:
        return False

    encoded = quote_plus(query)
    if target in SITE_SEARCH_URLS:
        url = SITE_SEARCH_URLS[target].format(query=encoded)
    elif target in WEB_TARGETS:
        domain = WEB_TARGETS[target]
        url = f"https://www.google.com/search?q={quote_plus(query + ' site:' + domain)}"
    else:
        return False

    try:
        ok = webbrowser.open(_sanitize_url(url))
        print(f"🔎 Opened '{target}' search for: {query}")
        return bool(ok)
    except Exception as e:
        print(f"❌ Site search error: {e}")
        return False


def open_target(target: str, query: str | None = None) -> bool:
    raw_target = (target or "").strip()
    target = clean_target(raw_target)
    query = (query or "").strip()

    if not target:
        print("❌ No target provided.")
        return False

    # Security guardrail: never open direct private/local/file URLs.
    if _is_blocked_direct_target(raw_target):
        print("⛔ Blocked unsafe or private URL target.")
        return False

    if query:
        if not _is_trusted_target(target):
            print("⛔ Target is not in trusted website list.")
            return False
        if open_site_search(target, query):
            return True
        if target in WEB_TARGETS:
            return open_url(target) and open_search(query)

        policy = get_policy()
        if policy.get("disable_unknown_site_search", True):
            # In strict mode, do not run unknown site-specific targets with a query.
            print(f"⛔ Blocked untrusted site target for query: {target}")
            return False

    if target in WEB_TARGETS:
        return open_url(target)

    return open_search(target)