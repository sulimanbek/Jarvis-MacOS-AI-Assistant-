import pytest

from core import router
from core.system_actions import SYSTEM_ACTIONS

NEW_ACTIONS = ["calc", "units", "sun", "air_quality", "quakes", "define", "market", "sports", "iss", "country"]


def route(phrase):
    return router.route(phrase)


@pytest.mark.parametrize("action", NEW_ACTIONS)
def test_actions_are_registered(action):
    assert action in SYSTEM_ACTIONS


@pytest.mark.parametrize("phrase,action,value", [
    # maths
    ("what's 23 times 47", "calc", "23 times 47"), ("15% of 240", "calc", "15% of 240"),
    ("what's 15 percent of 240", "calc", "15 percent of 240"), ("square root of 144", "calc", "square root of 144"),
    ("5 plus 3", "calc", "5 plus 3"), ("what is 100 divided by 8", "calc", "100 divided by 8"),
    ("2 to the power of 10", "calc", "2 to the power of 10"), ("what's 7 squared", "calc", "7 squared"),
    ("calculate 12 minus 5", "calc", "12 minus 5"), ("how much is 9 times 9", "calc", "9 times 9"),
    ("what's 5 x 3", "calc", "5 x 3"),
    # units
    ("how many kilometers in 5 miles", "units", "5 miles to kilometers"), ("convert 10 km to miles", "units", "10 km to miles"),
    ("what's 72 degrees fahrenheit in celsius", "units", "72 degrees fahrenheit to celsius"),
    ("how many ounces in a pound", "units", "1 pound to ounces"), ("5 feet in cm", "units", "5 feet to cm"),
    ("10 pounds to kilos", "units", "10 pounds to kilos"), ("how many minutes in 2 hours", "units", "2 hours to minutes"),
    ("how much is 5 gallons in liters", "units", "5 gallons to liters"),
    # sun and air
    ("when is sunset", "sun", "sunset|today|"), ("what time is sunrise tomorrow", "sun", "sunrise|tomorrow|"),
    ("when does the sun set in london", "sun", "sunset|today|london"), ("sunrise and sunset", "sun", "both|today|"),
    ("what time is sunset today", "sun", "sunset|today|"),
    ("what's the air quality", "air_quality", None), ("air quality in delhi", "air_quality", "delhi"),
    ("how's the air outside", "air_quality", None), ("is the air safe", "air_quality", None), ("what's the aqi", "air_quality", None),
    # earthquakes, words
    ("any earthquakes today", "quakes", None), ("latest earthquake", "quakes", None), ("were there any big earthquakes", "quakes", None),
    ("define serendipity", "define", "serendipity"), ("what does serendipity mean", "define", "serendipity"),
    ("what's the meaning of ephemeral", "define", "ephemeral"), ("definition of the word ubiquitous", "define", "ubiquitous"),
    # markets
    ("apple stock", "market", "apple"), ("price of tesla stock", "market", "tesla"), ("what's nvidia's stock price".replace("'s stock", " stock"), "market", "nvidia"),
    ("how's nvidia stock doing", "market", "nvidia"), ("how's tesla trading", "market", "tesla"), ("microsoft share price", "market", "microsoft"),
    ("price of gold", "market", "gold"), ("gold price", "market", "gold"), ("how much is oil", "market", "oil"),
    ("what's the oil price", "market", "oil"), ("how much is an ounce of gold", "market", "gold"),
    ("how's the stock market", "market", "stock market"), ("how's the nasdaq", "market", "nasdaq"), ("where is the dow", "market", "dow"),
    ("how are the markets doing", "market", "markets"),
    # sports
    ("premier league scores", "sports", "premier league"), ("nba scores yesterday", "sports", "nba|yesterday"),
    ("what are the nfl scores", "sports", "nfl"), ("champions league results", "sports", "champions league"),
    ("arsenal score", "sports", "arsenal"), ("did the lakers win", "sports", "lakers"), ("how did man city do", "sports", "man city"),
    ("did real madrid win last night", "sports", "real madrid|yesterday"), ("what's the score", "sports", None),
    # iss, countries
    ("where is the iss", "iss", None), ("where is the international space station", "iss", None), ("where's the space station", "iss", None),
    ("capital of japan", "country", "capital|japan"), ("what's the capital of france", "country", "capital|france"),
    ("what is the capital city of south korea", "country", "capital|south korea"),
    ("what's the population of india", "country", "population|india"), ("population of the united states", "country", "population|united states"),
    ("what is the gdp of the usa", "country", "gdp|usa"), ("how many people live in egypt", "country", "population|egypt"),
    ("what's the capital of the uae", "country", "capital|uae"),
])
def test_phrases_are_answered_locally(phrase, action, value):
    expected = {"tool": "system", "action": action, **({"value": value} if value else {})}
    assert route(phrase) == expected


@pytest.mark.parametrize("phrase", [
    # numbers that aren't a sum, and sentences that merely contain these words
    "what's 2023", "i have 5 apples and 3 pears", "what time is 5 o'clock", "call me at 5 plus", "5 plus", "plus 5",
    "it's 10 degrees outside", "i need 3 kilos of flour", "what are 5 good movies",
    # not units
    "how many days until friday", "how much is rent", "convert this", "5 km",
    # companies and things that are also words
    "apple", "how's apple doing", "how much is apple", "price of apples", "i like apple pie", "go to the market",
    "what's the market like for houses", "gold medal winners", "is gold a good gift", "oil change prices",
    # sports-ish
    "did the bears come out of hibernation", "who won the world cup", "when do the lakers play", "play lakers music",
    # places and words
    "what's the capital of texas", "capital of narnia", "capital of the moon", "what does that mean", "what does it mean",
    "what's the meaning of life", "define", "what's the definition of love and loss", "where is the station", "where is the bathroom",
    "what to do in an earthquake", "earthquake preparedness", "tell me about my day",
    # sun and air that are really something else
    "the sun is shining", "sunset boulevard", "is the air conditioning on", "turn up the air",
])
def test_everything_else_is_left_to_the_other_tiers(phrase):
    assert router._route_info(phrase, phrase.lower()) is None


@pytest.mark.parametrize("phrase", ["open the weather station", "remind me to check the gold price", "play the nba theme",
                                    "open calculator", "launch the sports app", "set a reminder for sunrise",
                                    "search for the capital of japan", "write a note about 5 plus 3"])
def test_commands_are_never_mistaken_for_questions(phrase):
    assert router._route_info(phrase, phrase.lower()) is None


def test_currency_still_beats_units_and_both_beat_maths():
    assert route("how much is 100 dollars in dirhams")["action"] == "convert"
    assert route("how much is 10 pounds in dollars")["action"] == "convert"          # money, not weight
    assert route("10 pounds to kilos")["action"] == "units"                          # weight, not money
    assert route("what's 5 km in miles")["action"] == "units"
    assert route("what's 5 plus 3")["action"] == "calc"


def test_older_routes_are_unchanged():
    assert route("what's the weather")["action"] == "weather"
    assert route("price of bitcoin")["action"] == "price"
    assert route("what time is it")["action"] == "time_now"
    assert route("volume up")["action"] == "volume_up"
    assert route("open safari") == {"tool": "app", "name": "Safari"}
