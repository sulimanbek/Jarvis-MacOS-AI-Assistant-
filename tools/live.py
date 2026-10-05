"""
tools/live.py

Live information from free public sources that need no account or key:

  weather and forecast   Open-Meteo
  news headlines         Google News (RSS)
  facts about a person or thing   Wikipedia
  crypto prices          CoinGecko
  currency conversion    open.er-api.com
  time and date          your Mac's clock (and the time zone Open-Meteo gives a place)

Each function returns (ok, message): one or two short sentences ready to be spoken.
They never raise, and they say plainly when the internet or a source is unavailable
rather than guessing. This is the answer straight from the source, not a language
model's memory, so it is current and can't be made up.

What leaves your Mac: the place, topic or coin you asked about, sent to that source.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from config import HOME_CITY, LIVE_TIMEOUT, NEWS_COUNTRY, TEMP_UNIT

HEADERS = {"User-Agent": "JarvisMacAssistant/1.0 (personal assistant)"}
MAX_BYTES = 3_000_000

OFFLINE = "I can't reach the internet right now."
UNAVAILABLE = "I couldn't get that right now."
SLOW = "That source is taking too long, so I gave up."


class SourceError(Exception):
    """A source couldn't be reached or answered badly. The message is speakable."""


class NotFoundError(SourceError):
    """The source answered, and says there is no such thing (HTTP 404)."""


def _get(url: str, params: dict | None = None) -> requests.Response:
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=LIVE_TIMEOUT)
    except requests.Timeout as e:
        raise SourceError(SLOW) from e
    except requests.ConnectionError as e:
        raise SourceError(OFFLINE) from e
    except requests.RequestException as e:
        raise SourceError(UNAVAILABLE) from e
    if response.status_code == 404:
        raise NotFoundError(UNAVAILABLE)
    if response.status_code != 200 or len(response.content) > MAX_BYTES:
        raise SourceError(UNAVAILABLE)
    return response


def _json(url: str, params: dict | None = None) -> dict:
    try:
        data = _get(url, params).json()
    except ValueError as e:
        raise SourceError(UNAVAILABLE) from e
    if not isinstance(data, dict):
        raise SourceError(UNAVAILABLE)
    return data


# ── places ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Place:
    name: str
    country: str
    lat: float
    lon: float
    tz: str


_places: dict[str, Place] = {}


def default_city() -> str | None:
    """The city to use when none is said: JARVIS_CITY, else taken from the Mac's time zone."""
    if HOME_CITY:
        return HOME_CITY
    try:
        zone = str(Path("/etc/localtime").resolve()).split("/zoneinfo/")[-1]
    except OSError:
        return None
    if "/" not in zone:
        return None
    return zone.rsplit("/", 1)[-1].replace("_", " ")


def geocode(name: str) -> Place:
    key = re.sub(r"\s+", " ", name.strip().lower().split(",")[0])
    if key in _places:
        return _places[key]
    data = _json("https://geocoding-api.open-meteo.com/v1/search",
                 {"name": key, "count": 1, "format": "json"})
    results = data.get("results") or []
    if not results:
        raise SourceError(f"I couldn't find a place called {name.strip()}.")
    r = results[0]
    place = Place(r.get("name", name), r.get("country", ""), r["latitude"], r["longitude"],
                  r.get("timezone") or "UTC")
    _places[key] = place
    return place


def _resolve(city: str | None) -> Place:
    chosen = (city or "").strip() or default_city()
    if not chosen:
        raise SourceError("Tell me which city, for example: weather in London.")
    return geocode(chosen)


def warm() -> None:
    """Look up the home city ahead of time so the first question isn't slow. Never raises."""
    try:
        city = default_city()
        if city:
            geocode(city)
    except Exception:
        pass


# ── speaking helpers ─────────────────────────────────────────────────────────

def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _clock(dt: datetime) -> str:
    hour = dt.hour % 12 or 12
    suffix = "AM" if dt.hour < 12 else "PM"
    return f"{hour} {suffix}" if dt.minute == 0 else f"{hour}:{dt.minute:02d} {suffix}"


# ── time and date (no internet needed for the local clock) ───────────────────

def time_now(place: str | None = None) -> tuple[bool, str]:
    if not (place or "").strip():
        return True, f"It's {_clock(datetime.now().astimezone())}."
    try:
        p = geocode(str(place))
        return True, f"It's {_clock(datetime.now(ZoneInfo(p.tz)))} in {p.name}."
    except SourceError as e:
        return False, str(e)


def date_today(_value: str | None = None) -> tuple[bool, str]:
    now = datetime.now().astimezone()
    return True, f"Today is {now:%A}, {now:%B} {_ordinal(now.day)}."


# ── weather ──────────────────────────────────────────────────────────────────

_WEATHER_CODES = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy",
    51: "drizzling", 53: "drizzling", 55: "drizzling", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "lightly raining", 63: "raining", 65: "raining heavily", 66: "freezing rain", 67: "freezing rain",
    71: "lightly snowing", 73: "snowing", 75: "snowing heavily", 77: "snowing", 80: "showery",
    81: "showery", 82: "very showery", 85: "snow showers", 86: "snow showers", 95: "stormy",
    96: "stormy with hail", 99: "stormy with hail",
}
_FORECAST_WORDS = {
    **_WEATHER_CODES, 0: "clear skies", 2: "partly cloudy", 3: "overcast", 61: "light rain", 63: "rain",
    65: "heavy rain", 71: "light snow", 73: "snow", 75: "heavy snow", 80: "showers", 81: "showers",
    82: "heavy showers", 95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail",
}


def _forecast(place: Place) -> dict:
    imperial = TEMP_UNIT == "fahrenheit"
    return _json("https://api.open-meteo.com/v1/forecast", {
        "latitude": place.lat, "longitude": place.lon, "timezone": "auto", "forecast_days": 2,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "temperature_unit": "fahrenheit" if imperial else "celsius",
        "wind_speed_unit": "mph" if imperial else "kmh",
    })


def _rain_phrase(chance) -> str:
    return f", with a {round(chance)} percent chance of rain" if chance is not None and chance >= 30 else ""


def weather_now(city: str | None = None) -> tuple[bool, str]:
    try:
        place = _resolve(city)
        data = _forecast(place)
        cur, day = data["current"], data["daily"]
        temp, feels = round(cur["temperature_2m"]), round(cur["apparent_temperature"])
        text = _WEATHER_CODES.get(cur.get("weather_code"), "")
        parts = [f"In {place.name} it's {temp} degrees" + (f" and {text}" if text else "")]
        if abs(feels - temp) >= 3:
            parts[0] += f", feeling like {feels}"
        high, low = round(day["temperature_2m_max"][0]), round(day["temperature_2m_min"][0])
        msg = f"{parts[0]}. Today's high is {high} and the low is {low}{_rain_phrase(day['precipitation_probability_max'][0])}."
        wind = cur.get("wind_speed_10m") or 0
        if wind >= (30 if TEMP_UNIT != "fahrenheit" else 20):
            msg += f" It's windy, around {round(wind)} {'miles per hour' if TEMP_UNIT == 'fahrenheit' else 'kilometres an hour'}."
        return True, msg
    except SourceError as e:
        return False, str(e)
    except (KeyError, IndexError, TypeError):
        return False, UNAVAILABLE


def weather_tomorrow(city: str | None = None) -> tuple[bool, str]:
    try:
        place = _resolve(city)
        day = _forecast(place)["daily"]
        words = _FORECAST_WORDS.get(day["weather_code"][1], "mixed weather")
        high, low = round(day["temperature_2m_max"][1]), round(day["temperature_2m_min"][1])
        return True, (f"Tomorrow in {place.name}: {words}, a high of {high} and a low of {low}"
                      f"{_rain_phrase(day['precipitation_probability_max'][1])}.")
    except SourceError as e:
        return False, str(e)
    except (KeyError, IndexError, TypeError):
        return False, UNAVAILABLE


# ── news ─────────────────────────────────────────────────────────────────────

def _headlines(topic: str | None, limit: int) -> list[tuple[str, str]]:
    base = "https://news.google.com/rss/search" if topic else "https://news.google.com/rss"
    params = {"hl": "en", "gl": NEWS_COUNTRY, "ceid": f"{NEWS_COUNTRY}:en"}
    if topic:
        params["q"] = topic
    try:
        root = ET.fromstring(_get(base, params).content)
    except (ET.ParseError, DefusedXmlException) as e:  # malformed, or an entity/DTD trick
        raise SourceError(UNAVAILABLE) from e

    seen, out = set(), []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        headline, _, source = title.rpartition(" - ")
        headline, source = (headline, source) if headline else (title, "")
        key = re.sub(r"\W+", "", headline.lower())[:40]
        if key in seen:
            continue
        seen.add(key)
        out.append((headline.strip()[:150], source.strip()))
        if len(out) >= limit:
            break
    return out


def _say_headlines(items: list[tuple[str, str]]) -> str:
    return " ".join(f"{h}{' — ' + s if s else ''}." for h, s in items)


def news(topic: str | None = None) -> tuple[bool, str]:
    topic = (topic or "").strip() or None
    try:
        items = _headlines(topic, 4)
    except SourceError as e:
        return False, str(e)
    if not items:
        return False, f"I couldn't find news about {topic}." if topic else UNAVAILABLE
    lead = f"Here's the latest on {topic}." if topic else "Here are the top stories."
    return True, f"{lead} {_say_headlines(items)}"


# ── Wikipedia ────────────────────────────────────────────────────────────────

_STOP = {"the", "a", "an", "of", "in", "on", "for", "and", "to", "is", "was", "who", "what"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP}


def _first_sentences(text: str, limit: int = 300) -> str:
    text = re.sub(r"\s*\([^)]*\)", "", text).strip()
    out = ""
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text):
        if out and len(out) + len(sentence) + 1 > limit:
            break
        out = f"{out} {sentence}".strip()
        if len(out) >= 160:
            break
    return out[:limit].rstrip()


def _wiki(topic: str, must_overlap: bool = False) -> str | None:
    """A short summary for `topic`, or None if there is no good page."""
    found = _json("https://en.wikipedia.org/w/rest.php/v1/search/title", {"q": topic, "limit": 1})
    pages = found.get("pages") or []
    if not pages:
        return None
    title = pages[0].get("title", "")
    if must_overlap and not (_words(topic) & _words(title)):
        return None
    summary = _json("https://en.wikipedia.org/api/rest_v1/page/summary/" + requests.utils.quote(title.replace(" ", "_"), safe=""))
    if summary.get("type") == "disambiguation":
        return f"{title} could mean several things. Which one do you want?"
    extract = _first_sentences(summary.get("extract") or "")
    return extract or None


def wiki(topic: str | None) -> tuple[bool, str]:
    topic = (topic or "").strip()
    if not topic:
        return False, "Tell me what you'd like to know about."
    try:
        text = _wiki(topic)
    except SourceError as e:
        return False, str(e)
    return (True, text) if text else (False, f"I couldn't find anything about {topic}.")


def _relevant(items: list[tuple[str, str]], query: str) -> list[tuple[str, str]]:
    """Keep headlines that actually mention most of what was asked, not just one word of it."""
    wanted = _words(query)
    if not wanted:
        return items
    need = 1 if len(wanted) == 1 else max(2, -(-len(wanted) * 3 // 5))   # at least 60 percent, never fewer than 2
    return [it for it in items if len(wanted & _words(it[0])) >= need]


def web_search(query: str | None) -> tuple[bool, str]:
    """
    A basic search for when Claude isn't available: a Wikipedia summary if the topic has a page,
    otherwise the latest headlines. Not a full web search, and it says so when it comes up empty.
    """
    query = (query or "").strip()
    if not query:
        return False, "What should I search for?"
    try:
        text = _wiki(query, must_overlap=True)
        if text:
            return True, f"According to Wikipedia: {text}"
        items = _relevant(_headlines(query, 12), query)[:3]
    except SourceError as e:
        return False, str(e)
    if items:
        return True, f"Here's what's in the news about {query}. {_say_headlines(items)}"
    return False, f"I couldn't find anything on {query}. Without Claude I can only check Wikipedia and the news."


# ── prices ───────────────────────────────────────────────────────────────────

# Named on purpose: a free-text search for "price of milk" would find some random token.
COINS = {
    "bitcoin": ("bitcoin", "Bitcoin"), "btc": ("bitcoin", "Bitcoin"),
    "ethereum": ("ethereum", "Ethereum"), "ether": ("ethereum", "Ethereum"), "eth": ("ethereum", "Ethereum"),
    "solana": ("solana", "Solana"), "sol": ("solana", "Solana"),
    "dogecoin": ("dogecoin", "Dogecoin"), "doge": ("dogecoin", "Dogecoin"),
    "xrp": ("ripple", "XRP"), "ripple": ("ripple", "XRP"),
    "litecoin": ("litecoin", "Litecoin"), "ltc": ("litecoin", "Litecoin"),
    "cardano": ("cardano", "Cardano"), "ada": ("cardano", "Cardano"),
    "bnb": ("binancecoin", "BNB"), "binance coin": ("binancecoin", "BNB"),
    "tether": ("tether", "Tether"), "usdt": ("tether", "Tether"),
    "polkadot": ("polkadot", "Polkadot"), "dot": ("polkadot", "Polkadot"),
    "avalanche": ("avalanche-2", "Avalanche"), "avax": ("avalanche-2", "Avalanche"),
    "chainlink": ("chainlink", "Chainlink"), "link": ("chainlink", "Chainlink"),
    "shiba inu": ("shiba-inu", "Shiba Inu"), "shib": ("shiba-inu", "Shiba Inu"),
    "toncoin": ("the-open-network", "Toncoin"), "ton": ("the-open-network", "Toncoin"),
    "tron": ("tron", "Tron"), "trx": ("tron", "Tron"),
    "polygon": ("matic-network", "Polygon"), "matic": ("matic-network", "Polygon"),
}


def _money(value: float) -> str:
    if value >= 100:
        return f"{value:,.0f}"
    if value >= 1:
        return f"{value:,.2f}"
    return f"{value:.4f}".rstrip("0").rstrip(".") or "0"


def price(asset: str | None) -> tuple[bool, str]:
    coin = COINS.get(re.sub(r"\s+", " ", (asset or "").strip().lower()))
    if coin is None:
        return False, "I only know the prices of the main cryptocurrencies."
    coin_id, name = coin
    try:
        data = _json("https://api.coingecko.com/api/v3/simple/price",
                     {"ids": coin_id, "vs_currencies": "usd", "include_24hr_change": "true"})
        info = data[coin_id]
        usd, change = float(info["usd"]), info.get("usd_24h_change")
    except SourceError as e:
        return False, str(e)
    except (KeyError, TypeError, ValueError):
        return False, UNAVAILABLE
    msg = f"{name} is {_money(usd)} dollars"
    if change is not None:
        msg += f", {'up' if change >= 0 else 'down'} {abs(change):.1f} percent today"
    return True, msg + "."


# ── currency ─────────────────────────────────────────────────────────────────

CURRENCY_NAMES = {
    "USD": "US dollars", "EUR": "euros", "GBP": "British pounds", "AED": "UAE dirhams", "SAR": "Saudi riyals",
    "JPY": "Japanese yen", "INR": "Indian rupees", "CAD": "Canadian dollars", "AUD": "Australian dollars",
    "CHF": "Swiss francs", "CNY": "Chinese yuan", "TRY": "Turkish lira", "KWD": "Kuwaiti dinars",
    "EGP": "Egyptian pounds", "QAR": "Qatari riyals", "BHD": "Bahraini dinars", "OMR": "Omani rials",
    "PKR": "Pakistani rupees", "RUB": "Russian rubles", "ZAR": "South African rand", "SGD": "Singapore dollars",
    "MXN": "Mexican pesos", "BRL": "Brazilian reais", "KRW": "South Korean won", "NZD": "New Zealand dollars",
}


def parse_conversion(value: str) -> tuple[float, str, str] | None:
    """'100 usd to aed' -> (100.0, 'USD', 'AED'). The amount is optional and defaults to 1."""
    m = re.fullmatch(r"\s*([\d,]*\.?\d+)?\s*([a-zA-Z]{3})\s+(?:to|in|into)\s+([a-zA-Z]{3})\s*", value or "")
    if not m:
        return None
    amount = float(m.group(1).replace(",", "")) if m.group(1) else 1.0
    return amount, m.group(2).upper(), m.group(3).upper()


_SAME_IN_SINGULAR = {"JPY", "CNY", "TRY", "ZAR", "BRL"}


def _currency_name(code: str, amount: float) -> str:
    name = CURRENCY_NAMES.get(code, code)
    if amount == 1 and code not in _SAME_IN_SINGULAR and name.endswith("s"):
        return name[:-1]
    return name


def _spoken_amount(x: float) -> str:
    return f"{x:,.0f}" if x >= 100 or x == int(x) else f"{x:,.2f}"


def convert(value: str | None) -> tuple[bool, str]:
    parsed = parse_conversion(value or "")
    if parsed is None:
        return False, "Tell me like this: a hundred dollars in euros."
    amount, src, dst = parsed
    try:
        rates = _json(f"https://open.er-api.com/v6/latest/{src}").get("rates") or {}
        if dst not in rates:
            return False, f"I don't have a rate for {dst}."
        result = amount * float(rates[dst])
    except SourceError as e:
        return False, str(e) if str(e) != UNAVAILABLE else f"I couldn't get a rate for {src}."
    except (TypeError, ValueError):
        return False, UNAVAILABLE
    return True, (f"{_spoken_amount(amount)} {_currency_name(src, amount)} is "
                  f"{_spoken_amount(result)} {_currency_name(dst, result)}.")
