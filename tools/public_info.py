"""
tools/public_info.py

More public information, from free sources that need no account or key:

  sunrise and sunset, air quality   Open-Meteo
  earthquakes                       USGS
  word definitions                  Wiktionary (backup: dictionaryapi.dev)
  stocks, indices, gold, oil        Yahoo Finance's public chart service
  sports scores                     ESPN's public scoreboards
  the space station                 wheretheiss.at
  capitals, populations, GDP        World Bank

Same rules as tools/live.py: each function returns (ok, message) ready to be spoken, never
raises, and says plainly when a source is unreachable instead of guessing. Only the thing you
asked about (a place, a word, a company) is sent to the source.

Some of these (Yahoo's chart service, ESPN's scoreboards) are public but unofficial, so they can
change without notice. If one stops working, Jarvis says it couldn't get that, and Claude's web
search still covers it.
"""

import html
import re
import time
import unicodedata
from datetime import datetime, timedelta
from difflib import get_close_matches
from zoneinfo import ZoneInfo

import requests

from tools.live import (
    OFFLINE,
    SLOW,
    UNAVAILABLE,
    NotFoundError,
    SourceError,
    _clock,
    _get,
    _json,
    _resolve,
)

# ── sunrise, sunset, air quality ─────────────────────────────────────────────


def sun(value: str | None) -> tuple[bool, str]:
    """value is 'kind|day|city': kind sunrise/sunset/both, day today/tomorrow. Any part may be blank."""
    kind, day, city = ((value or "").split("|") + ["", "", ""])[:3]
    kind, day = (kind or "both").strip(), (day or "today").strip()
    try:
        place = _resolve(city)
        data = _json("https://api.open-meteo.com/v1/forecast", {
            "latitude": place.lat, "longitude": place.lon, "timezone": "auto", "forecast_days": 2,
            "daily": "sunrise,sunset"})
        tz = ZoneInfo(data.get("timezone") or place.tz)
        i = 1 if day == "tomorrow" else 0
        rise = datetime.fromisoformat(data["daily"]["sunrise"][i]).replace(tzinfo=tz)
        sets = datetime.fromisoformat(data["daily"]["sunset"][i]).replace(tzinfo=tz)
    except SourceError as e:
        return False, str(e)
    except (KeyError, IndexError, TypeError, ValueError):
        return False, UNAVAILABLE

    now = datetime.now(tz)
    past = day != "tomorrow"

    def phrase(name: str, when: datetime) -> str:
        verb = "was" if past and when < now else "is"
        return f"{name} {verb} at {_clock(when)}"

    where = f"in {place.name}" + (" tomorrow" if day == "tomorrow" else "")
    if kind == "sunrise":
        return True, f"{phrase('Sunrise', rise)} {where}."
    if kind == "sunset":
        return True, f"{phrase('Sunset', sets)} {where}."
    return True, f"{phrase('Sunrise', rise)} and {phrase('sunset', sets).replace('Sunset', 'sunset')} {where}."


_AQI_BANDS = [(50, "good"), (100, "moderate"), (150, "unhealthy for sensitive groups"), (200, "unhealthy"),
              (300, "very unhealthy"), (10_000, "hazardous")]


def air_quality(city: str | None) -> tuple[bool, str]:
    try:
        place = _resolve(city)
        cur = _json("https://air-quality-api.open-meteo.com/v1/air-quality", {
            "latitude": place.lat, "longitude": place.lon, "current": "us_aqi,pm2_5"})["current"]
        aqi = round(cur["us_aqi"])
    except SourceError as e:
        return False, str(e)
    except (KeyError, TypeError, ValueError):
        return False, UNAVAILABLE
    band = next(label for limit, label in _AQI_BANDS if aqi <= limit)
    msg = f"Air quality in {place.name} is {band}, an index of {aqi}."
    if aqi > 100:
        msg += " People who are sensitive to pollution should limit time outside."
    return True, msg


# ── earthquakes ──────────────────────────────────────────────────────────────

_COMPASS = {"N": "north", "NNE": "north north east", "NE": "north east", "ENE": "east north east", "E": "east",
            "ESE": "east south east", "SE": "south east", "SSE": "south south east", "S": "south",
            "SSW": "south south west", "SW": "south west", "WSW": "west south west", "W": "west",
            "WNW": "west north west", "NW": "north west", "NNW": "north north west"}


def _speakable_place(place: str) -> str:
    text = re.sub(r"\b(\d+)\s*km\b", r"\1 kilometres", place)
    return re.sub(r"\b(N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW) of\b", lambda m: _COMPASS[m.group(1)] + " of", text)


def _ago(ms: float) -> str:
    hours = (time.time() * 1000 - ms) / 3_600_000
    if hours < 1:
        return "less than an hour ago"
    n = round(hours)
    return f"{n} hour{'s' if n != 1 else ''} ago"


def quakes(_value: str | None = None) -> tuple[bool, str]:
    try:
        features = _json("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson")["features"]
    except SourceError as e:
        return False, str(e)
    except (KeyError, TypeError):
        return False, UNAVAILABLE
    if not features:
        return True, "There were no earthquakes of magnitude 2.5 or more in the last day."
    try:
        top = max(features, key=lambda f: f["properties"].get("mag") or 0)["properties"]
        mag, place, when = float(top["mag"]), top.get("place") or "somewhere", top["time"]
    except (KeyError, TypeError, ValueError):
        return False, UNAVAILABLE
    noun = "earthquake" if len(features) == 1 else "earthquakes"
    return True, (f"There {'was' if len(features) == 1 else 'were'} {len(features)} {noun} of magnitude 2.5 or more "
                  f"in the last day. The strongest was a magnitude {mag:.1f}, {_speakable_place(place)}, {_ago(when)}.")


# ── dictionary ───────────────────────────────────────────────────────────────

# Wiktionary is fast and answers a clean 404 for unknown words. The free dictionary service is the
# backup: it is often slow, so it is only tried if Wiktionary itself is failing.
_SKIP_POS = {"symbol", "letter", "number", "numeral", "initialism", "abbreviation", "acronym", "contraction", "prefix", "suffix"}
_SKIP_SENSE = re.compile(r"(?i)^(?:alternative|obsolete|archaic|dated|misspelling|nonstandard|eye dialect|pronunciation spelling)\b")


def _plain(html_text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", html_text))).strip()


def _wiktionary(word: str) -> tuple[str, str] | None:
    data = _json("https://en.wiktionary.org/api/rest_v1/page/definition/" + requests.utils.quote(word))
    for entry in data.get("en") or []:
        pos = (entry.get("partOfSpeech") or "").lower()
        if pos in _SKIP_POS:
            continue
        for sense in entry.get("definitions") or []:
            text = _plain(sense.get("definition") or "")
            if text and not _SKIP_SENSE.match(text):
                return pos, text
    return None


def _dictionaryapi(word: str) -> tuple[str, str] | None:
    entries = _get("https://api.dictionaryapi.dev/api/v2/entries/en/" + requests.utils.quote(word)).json()
    meaning = entries[0]["meanings"][0]
    return meaning.get("partOfSpeech", ""), meaning["definitions"][0]["definition"].strip()


def define(word: str | None) -> tuple[bool, str]:
    w = re.sub(r"[^a-z' -]", "", (word or "").lower()).strip()
    if not w:
        return False, "Which word?"
    not_found = f"I couldn't find a definition for {w}."
    problems: list[str] = []
    for source in (_wiktionary, _dictionaryapi):
        try:
            found = source(w)
        except NotFoundError:
            return False, not_found                       # a real "no such word": don't wait on another source
        except SourceError as e:
            problems.append(str(e))
            continue
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            found = None
        if found:
            pos, text = found
            break
    else:
        # Both sources failed. Say why (offline, slow) rather than pretend the word doesn't exist.
        reasons = set(problems)
        return False, (problems[0] if len(problems) == 2 and len(reasons) == 1 and problems[0] in (OFFLINE, SLOW) else not_found)
    text = text[:260].rsplit(" ", 1)[0] + "…" if len(text) > 260 else text.rstrip(".") + "."
    return True, f"{w.capitalize()}, {pos}: {text}" if pos else f"{w.capitalize()}: {text}"


# ── stocks, indices, commodities ─────────────────────────────────────────────
# spoken name -> (Yahoo symbol, name to say, unit, kind). "company" names need a stock/share word in
# the question ("apple stock") so the fruit and the phone aren't mistaken for a quote.

def _co(symbol: str, spoken: str) -> tuple[str, str, str, str]:
    return symbol, spoken, "dollars", "company"


ASSETS: dict[str, tuple[str, str, str, str]] = {
    "apple": _co("AAPL", "Apple"), "microsoft": _co("MSFT", "Microsoft"), "google": _co("GOOGL", "Google"),
    "alphabet": _co("GOOGL", "Google"), "amazon": _co("AMZN", "Amazon"), "tesla": _co("TSLA", "Tesla"),
    "nvidia": _co("NVDA", "Nvidia"), "meta": _co("META", "Meta"), "facebook": _co("META", "Meta"),
    "netflix": _co("NFLX", "Netflix"), "amd": _co("AMD", "AMD"), "intel": _co("INTC", "Intel"),
    "disney": _co("DIS", "Disney"), "nike": _co("NKE", "Nike"), "coca cola": _co("KO", "Coca-Cola"),
    "coke": _co("KO", "Coca-Cola"), "pepsi": _co("PEP", "Pepsi"), "mcdonalds": _co("MCD", "McDonald's"), "mcdonald's": _co("MCD", "McDonald's"),
    "starbucks": _co("SBUX", "Starbucks"), "walmart": _co("WMT", "Walmart"), "boeing": _co("BA", "Boeing"),
    "ford": _co("F", "Ford"), "general motors": _co("GM", "General Motors"), "jpmorgan": _co("JPM", "JPMorgan"),
    "visa": _co("V", "Visa"), "mastercard": _co("MA", "Mastercard"), "paypal": _co("PYPL", "PayPal"),
    "uber": _co("UBER", "Uber"), "airbnb": _co("ABNB", "Airbnb"), "spotify": _co("SPOT", "Spotify"),
    "oracle": _co("ORCL", "Oracle"), "salesforce": _co("CRM", "Salesforce"), "adobe": _co("ADBE", "Adobe"),
    "ibm": _co("IBM", "IBM"), "cisco": _co("CSCO", "Cisco"), "qualcomm": _co("QCOM", "Qualcomm"),
    "shopify": _co("SHOP", "Shopify"), "palantir": _co("PLTR", "Palantir"), "coinbase": _co("COIN", "Coinbase"),
    "exxon": _co("XOM", "Exxon"), "chevron": _co("CVX", "Chevron"), "pfizer": _co("PFE", "Pfizer"),
    "toyota": _co("TM", "Toyota"), "sony": _co("SONY", "Sony"), "tsmc": _co("TSM", "TSMC"),
    "alibaba": _co("BABA", "Alibaba"), "berkshire hathaway": _co("BRK-B", "Berkshire Hathaway"),
    "s and p": ("^GSPC", "The S&P 500", "points", "market"), "s&p": ("^GSPC", "The S&P 500", "points", "market"),
    "s&p 500": ("^GSPC", "The S&P 500", "points", "market"), "s and p 500": ("^GSPC", "The S&P 500", "points", "market"),
    "stock market": ("^GSPC", "The S&P 500", "points", "market"), "market": ("^GSPC", "The S&P 500", "points", "market"),
    "markets": ("^GSPC", "The S&P 500", "points", "market"),
    "dow": ("^DJI", "The Dow", "points", "market"), "dow jones": ("^DJI", "The Dow", "points", "market"),
    "nasdaq": ("^IXIC", "The Nasdaq", "points", "market"), "ftse": ("^FTSE", "The FTSE 100", "points", "market"),
    "ftse 100": ("^FTSE", "The FTSE 100", "points", "market"), "nikkei": ("^N225", "The Nikkei", "points", "market"),
    "dax": ("^GDAXI", "The DAX", "points", "market"),
    "gold": ("GC=F", "Gold", "dollars an ounce", "market"), "silver": ("SI=F", "Silver", "dollars an ounce", "market"),
    "oil": ("BZ=F", "Brent oil", "dollars a barrel", "market"), "brent": ("BZ=F", "Brent oil", "dollars a barrel", "market"),
    "crude oil": ("CL=F", "Crude oil", "dollars a barrel", "market"), "crude": ("CL=F", "Crude oil", "dollars a barrel", "market"),
    "wti": ("CL=F", "Crude oil", "dollars a barrel", "market"),
    "copper": ("HG=F", "Copper", "dollars a pound", "market"),
}


def _money(x: float) -> str:
    return f"{x:,.2f}" if x < 1000 else f"{x:,.0f}" if x >= 10_000 else f"{x:,.1f}".rstrip("0").rstrip(".")


def market(name: str | None) -> tuple[bool, str]:
    entry = ASSETS.get(re.sub(r"^the ", "", re.sub(r"\s+", " ", (name or "").strip().lower())))
    if entry is None:
        return False, "I don't have a price for that."
    symbol, spoken, unit, _kind = entry
    try:
        data = _json("https://query1.finance.yahoo.com/v8/finance/chart/" + requests.utils.quote(symbol, safe=""),
                     {"interval": "1d", "range": "1d"})
        meta = data["chart"]["result"][0]["meta"]
        price = float(meta["regularMarketPrice"])
        previous = float(meta.get("chartPreviousClose") or meta["previousClose"])
        period = meta["currentTradingPeriod"]["regular"]
        is_open = period["start"] <= time.time() <= period["end"]
    except SourceError as e:
        return False, str(e)
    except (KeyError, IndexError, TypeError, ValueError):
        return False, UNAVAILABLE
    change = (price - previous) / previous * 100 if previous else 0.0
    when = "today" if is_open else "at the last close"
    verb = "up" if change >= 0 else "down"
    return True, f"{spoken} is {_money(price)} {unit}, {verb} {abs(change):.1f} percent {when}."


# ── sports ───────────────────────────────────────────────────────────────────
# spoken name -> (ESPN sport, ESPN league, name to say)

LEAGUES: dict[str, tuple[str, str, str]] = {
    "premier league": ("soccer", "eng.1", "Premier League"), "epl": ("soccer", "eng.1", "Premier League"),
    "la liga": ("soccer", "esp.1", "La Liga"), "bundesliga": ("soccer", "ger.1", "Bundesliga"),
    "serie a": ("soccer", "ita.1", "Serie A"), "ligue 1": ("soccer", "fra.1", "Ligue 1"),
    "champions league": ("soccer", "uefa.champions", "Champions League"), "mls": ("soccer", "usa.1", "MLS"),
    "nba": ("basketball", "nba", "NBA"), "wnba": ("basketball", "wnba", "WNBA"),
    "nfl": ("football", "nfl", "NFL"), "mlb": ("baseball", "mlb", "MLB"), "nhl": ("hockey", "nhl", "NHL"),
}


def _teams(league: str, *names: str) -> dict[str, str]:
    return {n: league for n in names}


# Famous teams, so "arsenal score" is understood without guessing at every noun in the language.
TEAMS: dict[str, str] = {
    **_teams("premier league", "arsenal", "chelsea", "liverpool", "manchester united", "man united", "man utd",
             "manchester city", "man city", "tottenham", "newcastle", "aston villa", "west ham", "brighton",
             "everton", "leeds", "fulham", "crystal palace", "wolves", "nottingham forest", "brentford", "bournemouth"),
    **_teams("la liga", "real madrid", "barcelona", "atletico madrid", "sevilla", "valencia", "real sociedad"),
    **_teams("bundesliga", "bayern munich", "bayern", "dortmund", "borussia dortmund", "leverkusen", "rb leipzig"),
    **_teams("serie a", "juventus", "ac milan", "inter milan", "napoli", "roma", "lazio"),
    **_teams("ligue 1", "psg", "paris saint germain", "marseille", "lyon", "monaco"),
    **_teams("nba", "lakers", "celtics", "warriors", "bulls", "heat", "knicks", "nets", "bucks", "suns", "mavericks",
             "nuggets", "clippers", "sixers", "76ers", "raptors", "thunder", "rockets", "grizzlies", "cavaliers",
             "cavs", "pacers", "hawks", "hornets", "magic", "pistons", "wizards", "timberwolves", "jazz", "kings",
             "pelicans", "blazers", "trail blazers"),
    **_teams("nfl", "chiefs", "eagles", "cowboys", "49ers", "patriots", "packers", "bills", "ravens", "bengals",
             "dolphins", "steelers", "jets", "bears", "lions", "rams", "chargers", "raiders", "broncos", "seahawks",
             "saints", "buccaneers", "bucs", "texans", "colts", "jaguars", "titans", "browns", "falcons", "vikings",
             "commanders"),
    **_teams("mlb", "yankees", "red sox", "dodgers", "cubs", "mets", "astros", "braves", "phillies"),
    **_teams("nhl", "bruins", "maple leafs", "canadiens", "oilers", "penguins", "blackhawks", "lightning"),
}


def _scoreboard(league: str, yesterday: bool = False) -> tuple[str, list[dict]]:
    sport, code, label = LEAGUES[league]
    # ESPN's "today" is the US Eastern date, so "yesterday" is measured there too, not on your local clock.
    params = {"dates": (datetime.now(ZoneInfo("America/New_York")) - timedelta(days=1)).strftime("%Y%m%d")} if yesterday else None
    data = _json(f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{code}/scoreboard", params)
    return label, data.get("events") or []


def _describe_game(event: dict) -> str:
    comp = event["competitions"][0]
    teams = {c["homeAway"]: c for c in comp["competitors"]}
    home, away = teams["home"], teams["away"]
    hn, an = home["team"]["displayName"], away["team"]["displayName"]
    status = event["status"]["type"]
    if status["state"] == "pre":
        when = datetime.fromisoformat(event["date"].replace("Z", "+00:00")).astimezone()
        day = "" if when.date() == datetime.now().astimezone().date() else f" {when:%A}"
        return f"{hn} versus {an}{day} at {_clock(when)}"
    detail = (status.get("description") if status["state"] == "post" else status.get("shortDetail")) or ""
    return f"{hn} {home.get('score', '0')}, {an} {away.get('score', '0')}" + (f", {detail.lower()}" if detail else "")


def sports(value: str | None) -> tuple[bool, str]:
    """value is a league or team name, optionally followed by '|yesterday'."""
    name, _, day = (value or "").partition("|")
    key = re.sub(r"\s+", " ", name.strip().lower())
    yesterday = day.strip() == "yesterday"
    league = key if key in LEAGUES else TEAMS.get(key)
    if league is None:
        return False, "Which league or team? For example, Premier League scores."
    when = "yesterday" if yesterday else "today"
    try:
        label, events = _scoreboard(league, yesterday)
        if key in TEAMS:                                     # a team: only its game(s)
            words = key.split()
            events = [e for e in events if any(all(w in c["team"]["displayName"].lower() for w in words)
                                               or key in c["team"].get("name", "").lower()
                                               or key in c["team"].get("shortDisplayName", "").lower()
                                               for c in e["competitions"][0]["competitors"])]
            if not events:
                return True, f"I don't see a {key.title()} game on the scoreboard {when}."
        elif not events:
            return True, f"There {'were' if yesterday else 'are'} no {label} games {when}."
        lines = [_describe_game(e) for e in events[:5]]
    except SourceError as e:
        return False, str(e)
    except (KeyError, IndexError, TypeError, ValueError):
        return False, UNAVAILABLE
    extra = f" And {len(events) - 5} more." if len(events) > 5 else ""
    lead = "" if key in TEAMS else f"{label}: "
    return True, lead + ". ".join(lines) + "." + extra


# ── the space station ────────────────────────────────────────────────────────

def _region(lat: float, lon: float, tz_id: str, country: str) -> str:
    if country and country != "??":
        area = tz_id.split("/")[0]
        return {"America": "the Americas", "Europe": "Europe", "Africa": "Africa", "Asia": "Asia",
                "Australia": "Australia", "Antarctica": "Antarctica"}.get(area, "land")
    if abs(lat) > 66:
        return "the polar regions"
    if -70 < lon < 20:
        return "the Atlantic Ocean"
    if 20 <= lon < 100:
        return "the Indian Ocean"
    return "the Pacific Ocean"


def iss(_value: str | None = None) -> tuple[bool, str]:
    try:
        pos = _json("https://api.wheretheiss.at/v1/satellites/25544")
        lat, lon = float(pos["latitude"]), float(pos["longitude"])
        alt, speed = round(float(pos["altitude"])), round(float(pos["velocity"]))
    except SourceError as e:
        return False, str(e)
    except (KeyError, TypeError, ValueError):
        return False, UNAVAILABLE
    try:
        geo = _json(f"https://api.wheretheiss.at/v1/coordinates/{lat},{lon}")
        where = _region(lat, lon, str(geo.get("timezone_id", "")), str(geo.get("country_code", "??")))
    except SourceError:
        where = "the Pacific Ocean" if abs(lon) > 100 else "the Atlantic or Indian Ocean"   # rough, better than silence
    return True, f"The International Space Station is over {where}, {alt} kilometres up and moving at {speed:,} kilometres an hour."


# ── countries (World Bank) ───────────────────────────────────────────────────

COUNTRY_NAMES = (
    "afghanistan albania algeria andorra angola argentina armenia australia austria azerbaijan bahamas bahrain "
    "bangladesh barbados belarus belgium belize benin bhutan bolivia bosnia botswana brazil brunei bulgaria "
    "burkina faso burundi cambodia cameroon canada chad chile china colombia comoros congo costa rica croatia "
    "cuba cyprus czechia denmark djibouti dominica ecuador egypt el salvador eritrea estonia eswatini ethiopia "
    "fiji finland france gabon gambia georgia germany ghana greece grenada guatemala guinea guyana haiti "
    "honduras hungary iceland india indonesia iran iraq ireland israel italy jamaica japan jordan kazakhstan "
    "kenya kiribati kosovo kuwait kyrgyzstan laos latvia lebanon lesotho liberia libya liechtenstein lithuania "
    "luxembourg madagascar malawi malaysia maldives mali malta mauritania mauritius mexico moldova monaco "
    "mongolia montenegro morocco mozambique myanmar namibia nepal netherlands new zealand nicaragua niger "
    "nigeria north korea north macedonia norway oman pakistan palestine panama papua new guinea paraguay peru "
    "philippines poland portugal qatar romania russia rwanda samoa san marino saudi arabia senegal serbia "
    "seychelles sierra leone singapore slovakia slovenia somalia south africa south korea south sudan spain "
    "sri lanka sudan suriname sweden switzerland syria taiwan tajikistan tanzania thailand togo tonga "
    "trinidad and tobago tunisia turkey turkmenistan uganda ukraine united arab emirates united kingdom "
    "united states uruguay uzbekistan vanuatu vatican venezuela vietnam yemen zambia zimbabwe "
    "uae uk usa america britain england scotland wales emirates holland"
)
COUNTRY_LIST = sorted(set(COUNTRY_NAMES.split()) | {
    "burkina faso", "costa rica", "el salvador", "new zealand", "north korea", "north macedonia",
    "papua new guinea", "san marino", "saudi arabia", "sierra leone", "south africa", "south korea",
    "south sudan", "sri lanka", "trinidad and tobago", "united arab emirates", "united kingdom", "united states",
}, key=len, reverse=True)

# What people say -> how the World Bank spells it (normalised: lower case, no punctuation or accents).
_COUNTRY_ALIASES = {
    "usa": "united states", "us": "united states", "america": "united states", "uk": "united kingdom",
    "britain": "united kingdom", "england": "united kingdom", "scotland": "united kingdom", "wales": "united kingdom",
    "uae": "united arab emirates", "emirates": "united arab emirates", "holland": "netherlands",
    "south korea": "korea rep", "north korea": "korea dem peoples rep", "russia": "russian federation",
    "iran": "iran islamic rep", "egypt": "egypt arab rep", "turkey": "turkiye", "vietnam": "viet nam",
    "syria": "syrian arab republic", "laos": "lao pdr", "venezuela": "venezuela rb", "yemen": "yemen rep",
    "czech republic": "czechia", "slovakia": "slovak republic", "kyrgyzstan": "kyrgyz republic",
    "gambia": "gambia the", "bahamas": "bahamas the", "ivory coast": "cote d'ivoire".replace("'", ""),
    "congo": "congo dem rep", "brunei": "brunei darussalam", "bosnia": "bosnia and herzegovina",
    "hong kong": "hong kong sar china", "palestine": "west bank and gaza", "burma": "myanmar",
}
_countries: dict[str, dict] = {}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text)).strip()


def _load_countries() -> dict[str, dict]:
    if not _countries:
        raw = _json_list("https://api.worldbank.org/v2/country", {"format": "json", "per_page": 400})
        for c in raw[1]:
            if c.get("capitalCity"):                        # skips regions like "World" and "Euro area"
                _countries[_norm(c["name"])] = c
    return _countries


def _json_list(url: str, params: dict | None = None) -> list:
    try:
        data = _get(url, params).json()
    except ValueError as e:
        raise SourceError(UNAVAILABLE) from e
    if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
        raise SourceError(UNAVAILABLE)
    return data


def _find_country(name: str) -> dict | None:
    countries = _load_countries()
    key = _norm(re.sub(r"^the ", "", name.strip().lower()))
    key = _COUNTRY_ALIASES.get(key, key)
    if key in countries:
        return countries[key]
    close = get_close_matches(key, list(countries), n=1, cutoff=0.85)
    return countries[close[0]] if close else None


def _big(x: float) -> str:
    for scale, word in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million")):
        if x >= scale:
            return f"{x / scale:.1f}".rstrip("0").rstrip(".") + f" {word}"
    return f"{x:,.0f}"


_THE = {"united states", "united kingdom", "united arab emirates", "netherlands", "philippines", "bahamas", "gambia"}
_SAID_AS = {"usa": "united states", "us": "united states", "america": "united states", "uk": "united kingdom",
            "britain": "united kingdom", "england": "united kingdom", "uae": "united arab emirates",
            "emirates": "united arab emirates", "holland": "netherlands"}


def _country_label(said: str, row: dict) -> str:
    """How to say the country: as it was asked (South Korea), or in full for abbreviations (UAE)."""
    said_norm = re.sub(r"^the ", "", _norm(said))
    text = _SAID_AS.get(said_norm) or said_norm or _norm(row["name"])
    label = " ".join(w if w in ("and", "of", "the") else w.capitalize() for w in text.split())
    return ("the " + label) if text in _THE else label


def country(value: str | None) -> tuple[bool, str]:
    """value is 'capital|Japan', 'population|Japan' or 'gdp|Japan'."""
    what, _, name = (value or "").partition("|")
    what, name = what.strip().lower(), name.strip()
    if what not in ("capital", "population", "gdp") or not name:
        return False, "Ask me for a country's capital, population or GDP."
    try:
        c = _find_country(name)
        if c is None:
            return False, f"I couldn't find a country called {name}."
        label = _country_label(name, c)
        if what == "capital":
            return True, f"The capital of {label} is {c['capitalCity'].rstrip('.')}."
        indicator = "SP.POP.TOTL" if what == "population" else "NY.GDP.MKTP.CD"
        row = _json_list(f"https://api.worldbank.org/v2/country/{c['iso2Code']}/indicator/{indicator}",
                         {"format": "json", "mrnev": 1})[1][0]
        amount, year = float(row["value"]), row["date"]
    except SourceError as e:
        return False, str(e)
    except (KeyError, IndexError, TypeError, ValueError):
        return False, UNAVAILABLE
    if what == "population":
        return True, f"{label[0].upper() + label[1:]} has a population of about {_big(amount)}, as of {year}."
    return True, f"The GDP of {label} is about {_big(amount)} dollars, as of {year}."
