import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import requests

from tests.test_live import GEO, Net, Resp
from tools import live
from tools import public_info as pi

NOW_MS = lambda: time.time() * 1000  # noqa: E731


def chart(price=332.89, prev=333.69, open_now=True):
    now = time.time()
    start, end = (now - 3600, now + 3600) if open_now else (now - 7200, now - 3600)
    return {"chart": {"result": [{"meta": {"regularMarketPrice": price, "chartPreviousClose": prev,
                                           "currentTradingPeriod": {"regular": {"start": start, "end": end}}}}]}}


def event(home, away, hs=None, as_=None, state="pre", desc="Scheduled", detail="", date="2026-10-10T15:00Z"):
    def comp(name, ha, score):
        return {"homeAway": ha, "score": score, "team": {"displayName": name, "name": name.split()[-1],
                                                         "shortDisplayName": name.split()[-1]}}
    return {"date": date, "status": {"type": {"state": state, "description": desc, "shortDetail": detail}},
            "competitions": [{"competitors": [comp(home, "home", hs), comp(away, "away", as_)]}]}


@pytest.fixture
def net(monkeypatch):
    n = Net()
    n.routes = {
        "geocoding-api": Resp(GEO),
        "api.open-meteo.com/v1/forecast": Resp({"timezone": "Asia/Dubai", "daily": {
            "sunrise": ["2026-10-06T06:12", "2026-10-07T06:13"], "sunset": ["2026-10-06T18:00", "2026-10-07T17:59"]}}),
        "air-quality-api": Resp({"current": {"us_aqi": 129.0, "pm2_5": 56.0}}),
        "earthquake.usgs.gov": Resp({"features": [
            {"properties": {"mag": 3.1, "place": "10 km N of Somewhere, CA", "time": NOW_MS() - 5 * 3600_000}},
            {"properties": {"mag": 5.3, "place": "32 km SW of Dana Point, CA", "time": NOW_MS() - 3 * 3600_000}},
            {"properties": {"mag": 2.6, "place": "Alaska", "time": NOW_MS() - 60_000}}]}),
        "wiktionary.org": wikt(("Noun", ["A combination of events which have come together by chance."])),
        "dictionaryapi.dev": Resp([{"meanings": [{"partOfSpeech": "noun", "definitions": [
            {"definition": "A combination of events which have come together by chance."}]}]}]),
        "query1.finance.yahoo.com": Resp(chart()),
        "espn.com": Resp({"events": [event("Arsenal", "Leeds United"), event("Aston Villa", "Brentford", "2", "1", "post", "Full Time")]}),
        "wheretheiss.at/v1/satellites": Resp({"latitude": 13.1, "longitude": 148.4, "altitude": 424.4, "velocity": 27564.7}),
        "wheretheiss.at/v1/coordinates": Resp({"timezone_id": "Pacific/Guam", "country_code": "??"}),
        "api.worldbank.org/v2/country?": None,
    }
    country_rows = [{"name": "Japan", "iso2Code": "JP", "capitalCity": "Tokyo"},
                    {"name": "Korea, Rep.", "iso2Code": "KR", "capitalCity": "Seoul"},
                    {"name": "United States", "iso2Code": "US", "capitalCity": "Washington D.C."},
                    {"name": "United Arab Emirates", "iso2Code": "AE", "capitalCity": "Abu Dhabi"},
                    {"name": "World", "iso2Code": "1W", "capitalCity": ""}]
    n.routes["api.worldbank.org/v2/country"] = lambda params: (
        Resp([{"page": 1}, country_rows]) if "per_page" in (params or {})
        else Resp([{"page": 1}, [{"value": 125_700_000, "date": "2025"}]]))
    del n.routes["api.worldbank.org/v2/country?"]
    monkeypatch.setattr(live.requests, "get", n)
    monkeypatch.setattr(live, "_places", {})
    monkeypatch.setattr(live, "HOME_CITY", "Dubai")
    monkeypatch.setattr(pi, "_countries", {})
    return n


# ── sunrise and sunset ───────────────────────────────────────────────────────

class FixedClock(datetime):
    fixed = datetime(2026, 10, 6, 12, 0, tzinfo=ZoneInfo("Asia/Dubai"))

    @classmethod
    def now(cls, tz=None):
        return cls.fixed.astimezone(tz) if tz else cls.fixed


def test_sun_times_use_the_right_tense(net, monkeypatch):
    monkeypatch.setattr(pi, "datetime", FixedClock)
    assert pi.sun("both|today|") == (True, "Sunrise was at 6:12 AM and sunset is at 6 PM in Dubai.")
    assert pi.sun("sunset|today|") == (True, "Sunset is at 6 PM in Dubai.")
    assert pi.sun("sunrise|tomorrow|") == (True, "Sunrise is at 6:13 AM in Dubai tomorrow.")


def test_sun_for_another_city_sends_that_city(net):
    pi.sun("sunset|today|London")
    assert net.calls[0][1]["name"] == "london"


def test_sun_survives_garbage(net):
    net.routes["api.open-meteo.com/v1/forecast"] = Resp({"daily": {}})
    assert pi.sun("both|today|") == (False, live.UNAVAILABLE)


# ── air quality ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("aqi,band", [(20, "good"), (50, "good"), (51, "moderate"), (129, "unhealthy for sensitive groups"),
                                      (180, "unhealthy"), (250, "very unhealthy"), (400, "hazardous")])
def test_air_quality_bands(net, aqi, band):
    net.routes["air-quality-api"] = Resp({"current": {"us_aqi": aqi}})
    ok, msg = pi.air_quality(None)
    assert ok and f"is {band}, an index of {aqi}" in msg
    assert ("limit time outside" in msg) == (aqi > 100)


# ── earthquakes ──────────────────────────────────────────────────────────────

def test_earthquakes_report_the_strongest_in_words(net):
    ok, msg = pi.quakes()
    assert ok and msg.startswith("There were 3 earthquakes of magnitude 2.5 or more in the last day.")
    assert "magnitude 5.3, 32 kilometres south west of Dana Point, CA, 3 hours ago." in msg


def test_earthquake_edge_cases(net):
    net.routes["earthquake.usgs.gov"] = Resp({"features": []})
    assert pi.quakes() == (True, "There were no earthquakes of magnitude 2.5 or more in the last day.")
    net.routes["earthquake.usgs.gov"] = Resp({"features": [{"properties": {"mag": 2.7, "place": "Alaska", "time": NOW_MS() - 10_000}}]})
    assert pi.quakes()[1].startswith("There was 1 earthquake of")
    assert "less than an hour ago" in pi.quakes()[1]
    net.routes["earthquake.usgs.gov"] = Resp({"features": [{"properties": {}}]})
    assert pi.quakes() == (False, live.UNAVAILABLE)


# ── dictionary ───────────────────────────────────────────────────────────────

def wikt(*entries):
    return Resp({"en": [{"partOfSpeech": pos, "definitions": [{"definition": d} for d in defs]} for pos, defs in entries]})


def test_definition_is_cleaned_of_markup(net):
    net.routes["wiktionary.org"] = wikt(("Noun", ['<a rel="mw:WikiLink" href="/wiki/combination">A combination</a> of events &amp; luck.']))
    assert pi.define("Serendipity") == (True, "Serendipity, noun: A combination of events & luck.")
    assert "dictionaryapi" not in str(net.calls)                      # the backup was not needed


def test_odd_entries_are_skipped(net):
    net.routes["wiktionary.org"] = wikt(("Symbol", ["ISO language code for Kirundi."]),
                                        ("Verb", ["Alternative form of runne.", "To move swiftly."]))
    assert pi.define("run") == (True, "Run, verb: To move swiftly.")


def test_a_word_wiktionary_does_not_know_stops_there(net):
    net.routes["wiktionary.org"] = Resp({"title": "Not found."}, status=404)
    assert pi.define("qzxvbnm") == (False, "I couldn't find a definition for qzxvbnm.")
    assert "dictionaryapi" not in str(net.calls)                      # no waiting on the slow backup


def test_the_backup_is_used_only_when_wiktionary_is_failing(net):
    net.routes["wiktionary.org"] = Resp(status=500, payload={})
    assert pi.define("serendipity") == (True, "Serendipity, noun: A combination of events which have come together by chance.")


def test_an_empty_wiktionary_answer_falls_back_too(net):
    net.routes["wiktionary.org"] = Resp({"en": []})
    assert pi.define("serendipity")[0] is True


def test_definition_failures_are_reported_honestly(net):
    assert pi.define("") == (False, "Which word?") and pi.define("12345") == (False, "Which word?")
    net.error = requests.ConnectionError()
    assert pi.define("word") == (False, live.OFFLINE)
    net.error = requests.Timeout()
    assert pi.define("word") == (False, live.SLOW)
    net.error = None
    net.routes["wiktionary.org"] = Resp(status=500, payload={})
    net.routes["dictionaryapi.dev"] = Resp({"title": "No Definitions Found"}, status=404)
    assert pi.define("word") == (False, "I couldn't find a definition for word.")


def test_a_long_definition_is_trimmed_at_a_word(net):
    net.routes["wiktionary.org"] = wikt(("Verb", ["word " * 100]))
    msg = pi.define("long")[1]
    assert len(msg) < 300 and msg.endswith("…") and not msg.endswith("….")


# ── markets ──────────────────────────────────────────────────────────────────

def test_stock_price_open_and_closed(net):
    assert pi.market("apple") == (True, "Apple is 332.89 dollars, down 0.2 percent today.")
    net.routes["query1.finance.yahoo.com"] = Resp(chart(open_now=False))
    assert pi.market("apple")[1] == "Apple is 332.89 dollars, down 0.2 percent at the last close."


def test_units_and_names_for_other_assets(net):
    net.routes["query1.finance.yahoo.com"] = Resp(chart(price=4167.6, prev=4162.3))
    assert pi.market("gold") == (True, "Gold is 4,167.6 dollars an ounce, up 0.1 percent today.")
    net.routes["query1.finance.yahoo.com"] = Resp(chart(price=7773.95, prev=7722.72))
    assert pi.market("the stock market")[1].startswith("The S&P 500 is 7,773.9 points, up 0.7 percent")
    assert "ZNVDA" not in str(net.calls) and "%5EGSPC" in net.calls[-1][0]            # the ^ is encoded


def test_unknown_asset_is_not_guessed(net):
    assert pi.market("milk") == (False, "I don't have a price for that.") and net.calls == []


def test_markets_degrade_safely(net):
    net.routes["query1.finance.yahoo.com"] = Resp({"chart": {"result": None, "error": {"code": "Not Found"}}})
    assert pi.market("apple") == (False, live.UNAVAILABLE)
    net.routes["query1.finance.yahoo.com"] = Resp(status=429, payload={})
    assert pi.market("apple") == (False, live.UNAVAILABLE)


def test_every_asset_is_well_formed():
    for name, (symbol, spoken, unit, kind) in pi.ASSETS.items():
        assert symbol and spoken and unit and kind in ("company", "market"), name
        assert name == name.lower()


# ── sports ───────────────────────────────────────────────────────────────────

def test_league_scores_mix_finished_and_upcoming(net):
    ok, msg = pi.sports("premier league")
    assert ok and msg.startswith("Premier League: Arsenal versus Leeds United")
    assert "Aston Villa 2, Brentford 1, full time." in msg
    assert net.calls[0][0].endswith("/soccer/eng.1/scoreboard")


def test_a_team_only_gets_its_own_game(net):
    ok, msg = pi.sports("arsenal")
    assert ok and msg.startswith("Arsenal versus Leeds United") and "Villa" not in msg and not msg.startswith("Premier")
    assert pi.sports("aston villa")[1] == "Aston Villa 2, Brentford 1, full time."


def test_a_team_with_no_game_says_so(net):
    assert pi.sports("chelsea") == (True, "I don't see a Chelsea game on the scoreboard today.")


def test_yesterday_is_measured_on_espns_clock(net):
    pi.sports("premier league|yesterday")
    expected = (datetime.now(ZoneInfo("America/New_York")) - timedelta(days=1)).strftime("%Y%m%d")
    assert net.calls[0][1] == {"dates": expected}
    net.routes["espn.com"] = Resp({"events": []})
    assert pi.sports("nba|yesterday") == (True, "There were no NBA games yesterday.")
    assert pi.sports("nba") == (True, "There are no NBA games today.")


def test_live_games_show_the_clock(net):
    net.routes["espn.com"] = Resp({"events": [event("Chelsea", "Brentford", "1", "1", "in", "In Progress", "67'")]})
    assert pi.sports("premier league")[1] == "Premier League: Chelsea 1, Brentford 1, 67'."


def test_long_scoreboards_are_cut_off(net):
    net.routes["espn.com"] = Resp({"events": [event(f"Home{i}", f"Away{i}", "1", "0", "post", "Final") for i in range(8)]})
    assert pi.sports("nba")[1].endswith("And 3 more.")


def test_sports_needs_a_league_or_team(net):
    assert pi.sports(None)[0] is False and pi.sports("curling")[0] is False and net.calls == []


def test_every_team_maps_to_a_real_league():
    assert set(pi.TEAMS.values()) <= set(pi.LEAGUES)


# ── the space station ────────────────────────────────────────────────────────

def test_iss(net):
    assert pi.iss() == (True, "The International Space Station is over the Pacific Ocean, 424 kilometres up and moving at 27,565 kilometres an hour.")


@pytest.mark.parametrize("lat,lon,tz,cc,expected", [
    (0, -30, "Etc/GMT+2", "??", "the Atlantic Ocean"), (0, 60, "Etc/GMT-4", "??", "the Indian Ocean"),
    (0, 170, "Etc/GMT-11", "??", "the Pacific Ocean"), (75, 10, "Etc/GMT", "??", "the polar regions"),
    (40, -100, "America/Chicago", "US", "the Americas"), (50, 10, "Europe/Berlin", "DE", "Europe"),
])
def test_iss_regions(lat, lon, tz, cc, expected):
    assert pi._region(lat, lon, tz, cc) == expected


def test_iss_still_answers_if_the_location_lookup_fails(net):
    net.routes["wheretheiss.at/v1/coordinates"] = Resp(status=500, payload={})
    ok, msg = pi.iss()
    assert ok and "International Space Station is over" in msg


# ── countries ────────────────────────────────────────────────────────────────

def test_capital_names_follow_how_you_asked(net):
    assert pi.country("capital|japan") == (True, "The capital of Japan is Tokyo.")
    assert pi.country("capital|south korea")[1] == "The capital of South Korea is Seoul."
    assert pi.country("capital|the usa")[1] == "The capital of the United States is Washington D.C."   # one full stop, not two
    assert pi.country("capital|uae")[1] == "The capital of the United Arab Emirates is Abu Dhabi."


def test_population_and_gdp(net):
    assert pi.country("population|japan") == (True, "Japan has a population of about 125.7 million, as of 2025.")
    assert pi.country("population|uae")[1].startswith("The United Arab Emirates has a population of about")
    net.routes["api.worldbank.org/v2/country"] = lambda params: (
        Resp([{}, [{"name": "United States", "iso2Code": "US", "capitalCity": "Washington D.C."}]]) if "per_page" in (params or {})
        else Resp([{}, [{"value": 30_800_000_000_000, "date": "2025"}]]))
    pi._countries.clear()
    assert pi.country("gdp|usa") == (True, "The GDP of the United States is about 30.8 trillion dollars, as of 2025.")


def test_unknown_country_and_bad_requests(net):
    assert pi.country("capital|narnia") == (False, "I couldn't find a country called narnia.")
    assert pi.country("capital|") [0] is False and pi.country("flag|japan")[0] is False and pi.country(None)[0] is False


def test_the_country_list_is_fetched_once_and_regions_are_dropped(net):
    pi.country("capital|japan")
    pi.country("capital|korea")
    assert sum("per_page" in p for _, p in net.calls) == 1
    assert "world" not in pi._countries


def test_big_number_wording():
    assert [pi._big(x) for x in (1_500_000, 11_500_000, 2.5e9, 30.8e12, 950_000)] == \
           ["1.5 million", "11.5 million", "2.5 billion", "30.8 trillion", "950,000"]


# ── every source says what is wrong ──────────────────────────────────────────

@pytest.mark.parametrize("call", [
    lambda: pi.sun("both|today|"), lambda: pi.air_quality(None), pi.quakes, lambda: pi.market("gold"),
    lambda: pi.sports("nba"), pi.iss, lambda: pi.country("capital|japan"), lambda: pi.define("word")])
def test_offline_and_slow_are_reported_differently(net, call):
    net.error = requests.ConnectionError()
    assert call() == (False, live.OFFLINE)
    net.error = requests.Timeout()
    assert call() == (False, live.SLOW)
