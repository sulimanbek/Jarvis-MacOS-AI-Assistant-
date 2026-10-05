import json
import re

import pytest
import requests

from core import router
from core.system_actions import SYSTEM_ACTIONS
from tools import live

# ── fixtures: what each source returns ───────────────────────────────────────

GEO = {"results": [{"name": "Dubai", "country": "United Arab Emirates", "latitude": 25.07, "longitude": 55.3,
                    "timezone": "Asia/Dubai"}]}


def forecast(temp=36.4, feels=41.2, code=0, wind=10.0, hi=38.2, lo=29.1, rain=(10, 55), codes=(0, 63),
             highs=(38.2, 37.0), lows=(29.1, 28.4)):
    return {"current": {"temperature_2m": temp, "apparent_temperature": feels, "weather_code": code,
                        "wind_speed_10m": wind},
            "daily": {"temperature_2m_max": list(highs), "temperature_2m_min": list(lows),
                      "precipitation_probability_max": list(rain), "weather_code": list(codes)}}


RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Markets rally on rate hopes - Reuters</title></item>
<item><title>Markets rally on rate hopes - Bloomberg</title></item>
<item><title>Storm hits the coast - BBC News</title></item>
<item><title>Team wins the final - Sky Sports</title></item>
<item><title>New phone announced - The Verge</title></item>
<item><title>Fifth story - Source</title></item>
</channel></rss>"""

WIKI_SEARCH = {"pages": [{"title": "Elon Musk"}]}
WIKI_SUMMARY = {"type": "standard", "extract": (
    "Elon Reeve Musk (born June 28, 1971) is a businessman and investor. He is the founder of several companies. "
    "He was born in South Africa and later moved to the United States, where he built many things.")}


class Resp:
    def __init__(self, payload=None, status=200, raw=None):
        self.status_code = status
        self.content = raw if raw is not None else json.dumps(payload).encode()

    def json(self):
        return json.loads(self.content)


class Net:
    """Replaces requests.get: routes by URL, records calls, can be told to fail."""

    def __init__(self):
        self.calls, self.routes, self.error = [], {}, None

    def __call__(self, url, params=None, **kw):
        self.calls.append((url, params or {}))
        if self.error:
            raise self.error
        for needle, value in self.routes.items():
            if needle in url:
                return value(params) if callable(value) else value
        raise AssertionError(f"unexpected request to {url}")


@pytest.fixture
def net(monkeypatch):
    n = Net()
    n.routes = {
        "geocoding-api": Resp(GEO),
        "api.open-meteo.com": Resp(forecast()),
        "news.google.com": Resp(raw=RSS.encode()),
        "rest.php/v1/search/title": Resp(WIKI_SEARCH),
        "api/rest_v1/page/summary": Resp(WIKI_SUMMARY),
        "coingecko": Resp({"bitcoin": {"usd": 67432.1, "usd_24h_change": -1.84}}),
        "er-api.com": Resp({"result": "success", "rates": {"AED": 3.6725, "EUR": 0.88889, "USD": 1.0}}),
    }
    monkeypatch.setattr(live.requests, "get", n)
    monkeypatch.setattr(live, "_places", {})
    monkeypatch.setattr(live, "HOME_CITY", "Dubai")
    monkeypatch.setattr(live, "TEMP_UNIT", "celsius")
    return n


# ── places ───────────────────────────────────────────────────────────────────

def test_default_city_prefers_the_setting(monkeypatch):
    monkeypatch.setattr(live, "HOME_CITY", "Paris")
    assert live.default_city() == "Paris"


@pytest.mark.parametrize("zone,city", [("Asia/Dubai", "Dubai"), ("America/New_York", "New York"),
                                       ("America/Argentina/Buenos_Aires", "Buenos Aires"), ("UTC", None)])
def test_default_city_comes_from_the_mac_time_zone(monkeypatch, zone, city):
    monkeypatch.setattr(live, "HOME_CITY", "")

    class FakePath:
        def __init__(self, p): pass
        def resolve(self): return f"/var/db/timezone/zoneinfo/{zone}"

    monkeypatch.setattr(live, "Path", FakePath)
    assert live.default_city() == city


def test_places_are_cached_for_the_session(net):
    live.geocode("Dubai")
    live.geocode("dubai")
    live.geocode("Dubai, UAE")
    assert sum("geocoding" in u for u, _ in net.calls) == 1


def test_unknown_place_is_a_clear_error(net):
    net.routes["geocoding-api"] = Resp({})
    ok, msg = live.weather_now("Atlantis")
    assert ok is False and "Atlantis" in msg


# ── weather ──────────────────────────────────────────────────────────────────

def test_weather_now_message(net):
    ok, msg = live.weather_now()
    assert ok
    assert msg == "In Dubai it's 36 degrees and clear, feeling like 41. Today's high is 38 and the low is 29."
    # No rain clause below 30 percent, no wind clause for a light breeze.
    assert "rain" not in msg and "windy" not in msg


def test_weather_now_uses_the_city_asked_for(net):
    live.weather_now("London")
    assert net.calls[0][1]["name"] == "london"


def test_rain_chance_and_strong_wind_are_mentioned(net):
    net.routes["api.open-meteo.com"] = Resp(forecast(feels=36.4, rain=(60, 10), wind=42.0, code=63))
    ok, msg = live.weather_now()
    assert "raining" in msg and "60 percent chance of rain" in msg
    assert "feeling like" not in msg                       # feels-like within 3 degrees: left out
    assert "windy, around 42 kilometres an hour" in msg


def test_fahrenheit_asks_for_fahrenheit_and_speaks_miles(net, monkeypatch):
    monkeypatch.setattr(live, "TEMP_UNIT", "fahrenheit")
    net.routes["api.open-meteo.com"] = Resp(forecast(temp=95.0, feels=97.0, wind=25.0))
    ok, msg = live.weather_now()
    params = next(p for u, p in net.calls if "api.open-meteo.com/v1/forecast" in u)
    assert params["temperature_unit"] == "fahrenheit" and params["wind_speed_unit"] == "mph"
    assert "95 degrees" in msg and "miles per hour" in msg


def test_weather_tomorrow_reads_the_second_day(net):
    ok, msg = live.weather_tomorrow("Dubai")
    assert msg == "Tomorrow in Dubai: rain, a high of 37 and a low of 28, with a 55 percent chance of rain."


def test_no_city_and_no_default_asks_for_one(net, monkeypatch):
    monkeypatch.setattr(live, "HOME_CITY", "")
    monkeypatch.setattr(live, "default_city", lambda: None)
    ok, msg = live.weather_now()
    assert ok is False and "which city" in msg.lower()


@pytest.mark.parametrize("fn", [live.weather_now, live.weather_tomorrow, live.news, live.wiki, live.price])
def test_every_source_says_so_when_offline(net, fn):
    net.error = requests.ConnectionError("no wifi")
    arg = "bitcoin" if fn is live.price else "Elon Musk"
    ok, msg = fn(arg)
    assert ok is False and msg == live.OFFLINE


def test_a_timeout_is_not_reported_as_being_offline(net):
    net.error = requests.Timeout()
    assert live.weather_now() == (False, live.SLOW)
    assert live.SLOW != live.OFFLINE


def test_a_server_error_or_garbage_is_reported_not_raised(net):
    net.routes["api.open-meteo.com"] = Resp(status=500, payload={})
    assert live.weather_now() == (False, live.UNAVAILABLE)
    net.routes["api.open-meteo.com"] = Resp(raw=b"<html>not json</html>")
    assert live.weather_now() == (False, live.UNAVAILABLE)
    net.routes["api.open-meteo.com"] = Resp({"unexpected": True})
    assert live.weather_now() == (False, live.UNAVAILABLE)
    net.routes["api.open-meteo.com"] = Resp(raw=b"x" * (live.MAX_BYTES + 1))
    assert live.weather_now() == (False, live.UNAVAILABLE)


# ── time and date ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("n,expected", [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"), (12, "12th"),
                                        (13, "13th"), (21, "21st"), (22, "22nd"), (23, "23rd"), (30, "30th")])
def test_ordinals(n, expected):
    assert live._ordinal(n) == expected


def test_clock_wording():
    from datetime import datetime
    assert live._clock(datetime(2026, 1, 1, 0, 5)) == "12:05 AM"
    assert live._clock(datetime(2026, 1, 1, 12, 0)) == "12 PM"
    assert live._clock(datetime(2026, 1, 1, 15, 30)) == "3:30 PM"


def test_local_time_needs_no_internet(net):
    net.error = requests.ConnectionError("offline")
    ok, msg = live.time_now(None)
    assert ok and re.fullmatch(r"It's \d{1,2}(:\d\d)? (AM|PM)\.", msg)
    assert net.calls == []


def test_time_in_another_place(net):
    ok, msg = live.time_now("Tokyo")
    assert ok and re.fullmatch(r"It's \d{1,2}(:\d\d)? (AM|PM) in Dubai\.", msg)   # the fake geocoder always says Dubai


def test_date_today():
    ok, msg = live.date_today()
    assert ok and re.fullmatch(r"Today is \w+day, \w+ \d{1,2}(st|nd|rd|th)\.", msg)


# ── news ─────────────────────────────────────────────────────────────────────

def test_news_top_stories_dedupes_and_limits(net):
    ok, msg = live.news()
    assert ok and msg.startswith("Here are the top stories. Markets rally on rate hopes — Reuters.")
    assert msg.count("Markets rally") == 1                  # the repeat from another outlet is dropped
    assert "Fifth story" not in msg                          # four is enough to listen to
    assert net.calls[0][0] == "https://news.google.com/rss" and "q" not in net.calls[0][1]


def test_news_on_a_topic_sends_the_topic(net):
    ok, msg = live.news("spacex launch")
    assert msg.startswith("Here's the latest on spacex launch.")
    assert net.calls[0][0].endswith("/rss/search") and net.calls[0][1]["q"] == "spacex launch"


def test_news_with_no_results(net):
    net.routes["news.google.com"] = Resp(raw=b'<?xml version="1.0"?><rss><channel></channel></rss>')
    assert live.news("zzz") == (False, "I couldn't find news about zzz.")


BOMB = b"""<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">]>
<rss><channel><item><title>&lol2;</title></item></channel></rss>"""
XXE = b"""<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<rss><channel><item><title>&x;</title></item></channel></rss>"""


@pytest.mark.parametrize("payload", [BOMB, XXE, b"not xml at all"])
def test_hostile_or_broken_feeds_are_refused_safely(net, payload):
    net.routes["news.google.com"] = Resp(raw=payload)
    assert live.news() == (False, live.UNAVAILABLE)


# ── wikipedia and search ────────────────────────────────────────────────────

def test_wiki_summary_is_short_and_speakable(net):
    ok, msg = live.wiki("Elon Musk")
    assert ok and "(born" not in msg and "1971" not in msg
    assert msg.startswith("Elon Reeve Musk is a businessman and investor.")
    assert len(msg) <= 300


def test_wiki_disambiguation_asks_which(net):
    net.routes["api/rest_v1/page/summary"] = Resp({"type": "disambiguation", "extract": "Mercury may refer to"})
    ok, msg = live.wiki("mercury")
    assert ok and "could mean several things" in msg


def test_wiki_with_no_page(net):
    net.routes["rest.php/v1/search/title"] = Resp({"pages": []})
    assert live.wiki("qwertyuiop") == (False, "I couldn't find anything about qwertyuiop.")
    assert live.wiki("") == (False, "Tell me what you'd like to know about.")


def test_web_search_prefers_a_matching_wikipedia_page(net):
    ok, msg = live.web_search("elon musk")
    assert ok and msg.startswith("According to Wikipedia: Elon Reeve Musk")


def _feed(*titles):
    items = "".join(f"<item><title>{t}</title></item>" for t in titles)
    return Resp(raw=f'<?xml version="1.0"?><rss><channel>{items}</channel></rss>'.encode())


def test_web_search_falls_back_to_news_when_the_page_is_unrelated(net):
    net.routes["rest.php/v1/search/title"] = Resp({"pages": [{"title": "Banana"}]})
    net.routes["news.google.com"] = _feed("Central bank rate decision due tomorrow - Reuters")
    ok, msg = live.web_search("rate decision tomorrow")
    assert ok and msg.startswith("Here's what's in the news about rate decision tomorrow.")
    assert "Central bank" in msg


def test_web_search_does_not_pass_off_loosely_related_headlines(net):
    # Only the word "dubai" matches: that is not an answer to "tide times in dubai".
    net.routes["rest.php/v1/search/title"] = Resp({"pages": []})
    net.routes["news.google.com"] = _feed("Dubai home prices fall - Gulf Business", "Dubai tourism rebounds - Reuters")
    ok, msg = live.web_search("tide times in dubai")
    assert ok is False and "Wikipedia and the news" in msg


def test_relevance_rules():
    items = [("Dubai home prices fall", "x"), ("Tide times for Dubai beaches published", "y")]
    assert [h for h, _ in live._relevant(items, "tide times in dubai")] == ["Tide times for Dubai beaches published"]
    assert len(live._relevant(items, "dubai")) == 2                       # a one-word query needs one word
    assert live._relevant(items, "") == items


def test_web_search_admits_when_it_found_nothing(net):
    net.routes["rest.php/v1/search/title"] = Resp({"pages": []})
    net.routes["news.google.com"] = Resp(raw=b'<?xml version="1.0"?><rss><channel></channel></rss>')
    ok, msg = live.web_search("asdf")
    assert ok is False and "Wikipedia and the news" in msg


# ── prices and currency ──────────────────────────────────────────────────────

def test_crypto_price(net):
    assert live.price("bitcoin") == (True, "Bitcoin is 67,432 dollars, down 1.8 percent today.")
    assert net.calls[-1][1]["ids"] == "bitcoin"
    assert live.price("BTC")[0] is True                                  # symbols and case work


def test_crypto_up_and_cheap_coins(net):
    net.routes["coingecko"] = Resp({"dogecoin": {"usd": 0.1234, "usd_24h_change": 3.04}})
    assert live.price("doge") == (True, "Dogecoin is 0.1234 dollars, up 3.0 percent today.")


def test_unknown_assets_are_not_guessed(net):
    ok, msg = live.price("milk")
    assert ok is False and net.calls == []


@pytest.mark.parametrize("text,expected", [("100 usd to aed", (100.0, "USD", "AED")), ("usd to eur", (1.0, "USD", "EUR")),
                                           ("1,250.5 gbp in jpy", (1250.5, "GBP", "JPY")), ("nonsense", None), ("", None)])
def test_parse_conversion(text, expected):
    assert live.parse_conversion(text) == expected


def test_conversion_message(net):
    ok, msg = live.convert("100 USD to AED")
    assert (ok, msg) == (True, "100 US dollars is 367 UAE dirhams.")
    assert "latest/USD" in net.calls[-1][0]


@pytest.mark.parametrize("code,amount,expected", [
    ("GBP", 1, "British pound"), ("GBP", 2, "British pounds"), ("EUR", 1.0, "euro"), ("JPY", 1, "Japanese yen"),
    ("AED", 100, "UAE dirhams"), ("ZAR", 1, "South African rand"), ("XYZ", 1, "XYZ")])
def test_currency_names_agree_with_the_amount(code, amount, expected):
    assert live._currency_name(code, amount) == expected


def test_conversion_default_amount_and_unknown_currency(net):
    assert live.convert("USD to EUR")[1] == "1 US dollar is 0.89 euros."
    ok, msg = live.convert("USD to XYZ")
    assert ok is False and "XYZ" in msg
    assert live.convert("what")[0] is False


# ── the registry and the router ──────────────────────────────────────────────

NEW_ACTIONS = ["weather", "weather_tomorrow", "news", "time_now", "date_today", "price", "convert", "wiki", "web_search"]


@pytest.mark.parametrize("action", NEW_ACTIONS)
def test_actions_are_registered_and_return_the_executor_shape(net, action):
    handler = SYSTEM_ACTIONS[action].handler
    ok, message, data = handler({"price": "bitcoin", "convert": "1 USD to EUR"}.get(action, "Dubai"))
    assert isinstance(ok, bool) and isinstance(message, str) and message and data == {}


@pytest.mark.parametrize("phrase,action,value", [
    ("what's the weather", "weather", None), ("what is the weather like today", "weather", None),
    ("what's the weather in london", "weather", "london"), ("weather in new york", "weather", "new york"),
    ("how's the weather in dubai right now", "weather", "dubai"), ("weather", "weather", None),
    ("what's the temperature outside", "weather", None), ("how hot is it", "weather", None),
    ("is it going to rain", "weather", None), ("will it rain tomorrow", "weather_tomorrow", None),
    ("weather tomorrow in paris", "weather_tomorrow", "paris"), ("what's tomorrow's forecast", "weather_tomorrow", None),
    ("hey jarvis what's the weather", "weather", None), ("can you tell me the weather", "weather", None),
    ("what time is it", "time_now", None), ("what's the time", "time_now", None),
    ("what time is it in tokyo", "time_now", "tokyo"), ("what's the date", "date_today", None),
    ("what day is it", "date_today", None), ("what's today's date", "date_today", None),
    ("what's the news", "news", None), ("headlines", "news", None), ("give me the latest news", "news", None),
    ("news about spacex", "news", "spacex"), ("what's the latest news on the election", "news", "the election"),
    ("what's in the news", "news", None),
    ("price of bitcoin", "price", "bitcoin"), ("what's the price of ethereum", "price", "ethereum"),
    ("how much is bitcoin", "price", "bitcoin"), ("bitcoin price", "price", "bitcoin"), ("what's eth at", "price", "eth"),
    ("how much is 100 dollars in dirhams", "convert", "100 USD to AED"), ("convert 50 euros to pounds", "convert", "50 EUR to GBP"),
    ("what's a dollar in dirhams", "convert", "1 USD to AED"), ("100 dollars in euros", "convert", "100 USD to EUR"),
    ("exchange rate dollars to dirhams", "convert", "1 USD to AED"), ("how much is 1,000 yen in dollars", "convert", "1000 JPY to USD"),
    ("who is elon musk", "wiki", "elon musk"), ("who was napoleon", "wiki", "napoleon"),
    ("tell me about the roman empire", "wiki", "roman empire"), ("wikipedia black holes", "wiki", "black holes"),
])
def test_live_phrases_are_answered_locally(phrase, action, value):
    expected = {"tool": "system", "action": action, **({"value": value} if value else {})}
    assert router.route(phrase) == expected


@pytest.mark.parametrize("phrase", [
    "open the weather app", "launch weather", "remind me to check the weather", "set a reminder about the news",
    "play the news", "turn on the weather channel", "who is at the door", "who is the president of france",
    "tell me about my day", "tell me about yourself", "who are you", "i have 3 dollars in my wallet",
    "what do you think about bitcoin", "price of milk", "how much is a coffee", "what time does the movie start",
    "weather app", "the news channel", "news podcast", "what is the capital of france",
])
def test_everything_else_is_left_to_the_other_tiers(phrase):
    decision = router._route_live(phrase, phrase.lower())
    assert decision is None


# ── web search routing ───────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase,query", [
    ("search the web for best pizza dough", "best pizza dough"), ("search online for flights to rome", "flights to rome"),
    ("search for cheap laptops", "cheap laptops"), ("google python tutorials", "python tutorials"),
    ("look up the boiling point of water", "the boiling point of water"), ("web search rust vs go", "rust vs go"),
    ("hey jarvis search the internet for tide times", "tide times"),
])
def test_general_searches_are_recognised(phrase, query):
    assert router._extract_web_search(phrase) == query


@pytest.mark.parametrize("phrase", ["look up ai news on youtube", "search youtube for ai news", "google", "search for youtube",
                                    "open google", "search"])
def test_site_searches_are_not_general_searches(phrase):
    assert router._extract_web_search(phrase) is None


def test_site_searches_still_open_the_site():
    assert router.route("look up ai news on youtube") == {"tool": "browser", "target": "youtube", "query": "ai news"}
    assert router.route("search youtube for ai news") == {"tool": "browser", "target": "youtube", "query": "ai news"}


def test_a_search_goes_to_claude_when_it_is_available(monkeypatch):
    monkeypatch.setattr(router, "BRAIN_MODE", "claude")
    monkeypatch.setattr(router, "think_claude", lambda t: {"tool": None, "response": "from claude", "_source": "claude"})
    assert router.route("search the web for tide times")["response"] == "from claude"


def test_a_search_falls_back_to_wikipedia_and_news_when_claude_is_down(monkeypatch):
    monkeypatch.setattr(router, "BRAIN_MODE", "claude")
    monkeypatch.setattr(router, "think_claude", lambda t: None)
    assert router.route("search the web for tide times") == {"tool": "system", "action": "web_search", "value": "tide times"}


def test_local_mode_searches_with_wikipedia_and_news_and_never_asks_claude(monkeypatch):
    monkeypatch.setattr(router, "BRAIN_MODE", "local")
    monkeypatch.setattr(router, "think_claude", lambda t: (_ for _ in ()).throw(AssertionError("claude used")))
    assert router.route("google python tutorials") == {"tool": "system", "action": "web_search", "value": "python tutorials"}


def test_live_phrases_never_reach_claude(monkeypatch):
    monkeypatch.setattr(router, "BRAIN_MODE", "claude")
    monkeypatch.setattr(router, "think_claude", lambda t: (_ for _ in ()).throw(AssertionError("claude used")))
    assert router.route("what's the weather in london")["action"] == "weather"
    assert router.route("price of bitcoin")["action"] == "price"
