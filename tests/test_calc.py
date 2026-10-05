import pytest

from tools import calc

# ── arithmetic ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("said,expected", [
    ("23 times 47", "23 times 47 is 1,081."),
    ("15% of 240", "15% of 240 is 36."),
    ("15 percent of 240", "15 percent of 240 is 36."),
    ("what's 20 percent of 80".replace("what's ", ""), "20 percent of 80 is 16."),
    ("square root of 144", "square root of 144 is 12."),
    ("square root of 2", "square root of 2 is 1.414."),
    ("5 plus 3", "5 plus 3 is 8."),
    ("100 minus 37", "100 minus 37 is 63."),
    ("10 divided by 4", "10 divided by 4 is 2.5."),
    ("10 over 4", "10 over 4 is 2.5."),
    ("2 to the power of 10", "2 to the power of 10 is 1,024."),
    ("2 ^ 8", "2 ^ 8 is 256."),
    ("7 squared", "7 squared is 49."),
    ("3 cubed", "3 cubed is 27."),
    ("1,000 times 3", "1,000 times 3 is 3,000."),
    ("5 x 3", "5 x 3 is 15."),
    ("(2 + 3) * 4", "(2 + 3) * 4 is 20."),
    ("0.1 plus 0.2", "0.1 plus 0.2 is 0.3."),
    ("-5 times 3", "-5 times 3 is negative 15."),
    ("7 mod 3", "7 mod 3 is 1."),
    ("2 + 3 * 4", "2 + 3 * 4 is 14."),                  # precedence is respected
    ("1000000 times 1000000", "1000000 times 1000000 is 1,000,000,000,000."),
])
def test_arithmetic(said, expected):
    assert calc.calculate(said) == (True, expected)


@pytest.mark.parametrize("said,message", [
    ("10 / 0", "You can't divide by zero."),
    ("5 mod 0", "You can't divide by zero."),
    ("2 ** 99999", "That's too big for me to work out."),
    ("9 ** 9 ** 9", "That's too big for me to work out."),
    ("10 ** 400", "That's too big for me to work out."),
    ("0 ** -1", "I can't work that one out."),
    ("(-8) ** 0.5", "That doesn't have a real answer."),
])
def test_arithmetic_refuses_what_it_cannot_do_safely(said, message):
    assert calc.calculate(said) == (False, message)


@pytest.mark.parametrize("hostile", [
    "__import__('os').system('ls')", "open('/etc/passwd')", "().__class__.__bases__", "[x for x in range(10**9)]",
    "lambda: 1", "1; import os", "os.system('x')", "exec('1')", "eval('1+1')", "5 plus apple", "2 plus", "", "   ",
    "abc", "1 if True else 2", "'a' * 5", "1 < 2", "not 1", "{1: 2}", "5 !! 3", "1__2",
])
def test_nothing_that_is_not_plain_arithmetic_is_ever_run(hostile):
    ok, message = calc.calculate(hostile)
    assert ok is False and message in {"I couldn't work that out.", "You can't divide by zero."}


def test_deeply_nested_input_cannot_crash_it():
    ok, _ = calc.calculate("(" * 5000 + "1" + ")" * 5000)
    assert ok is False


def test_no_code_path_can_reach_eval_or_exec():
    import inspect
    body = inspect.getsource(calc).split("def calculate")[1]
    assert "eval(" not in body and "exec(" not in body and "compile(" not in body


@pytest.mark.parametrize("x,expected", [
    (1081, "1,081"), (6.2137, "6.214"), (0.00254, "0.00254"), (-3.5, "negative 3.5"), (2.5, "2.5"), (0.3, "0.3"),
    (12345.678, "12,346"), (1234.5678, "1,234.6"), (1e12, "1,000,000,000,000"), (0, "0"), (100.0, "100"),
])
def test_number_formatting(x, expected):
    assert calc.format_number(x) == expected


def test_infinity_and_nan_are_not_spoken():
    for bad in (float("inf"), float("nan")):
        with pytest.raises(calc.CalcError):
            calc.format_number(bad)


# ── units ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("said,expected", [
    ("10 km to miles", "10 kilometers is 6.214 miles."),
    ("1 mile to km", "1 mile is 1.609 kilometers."),
    ("5 feet in cm", "5 feet is 152.4 centimeters."),
    ("1 inch to cm", "1 inch is 2.54 centimeters."),
    ("1 kg to pounds", "1 kilogram is 2.205 pounds."),
    ("1 pound to kilos", "1 pound is 0.4536 kilograms."),
    ("2 gallons to liters", "2 gallons is 7.571 liters."),
    ("100 mph to km/h", "100 miles per hour is 160.9 kilometers per hour."),
    ("10 minutes to seconds", "10 minutes is 600 seconds."),
    ("2 hours in minutes", "2 hours is 120 minutes."),
    ("500 gb to mb", "500 gigabytes is 500,000 megabytes."),
    ("1 acre to square feet", "1 acre is 43,560 square feet."),
    ("km to miles", "1 kilometer is 0.6214 miles."),                       # the amount defaults to 1
    ("1,000 meters to km", "1,000 meters is 1 kilometer."),
    ("1 tablespoon to teaspoons", "1 tablespoon is 3 teaspoons."),
])
def test_unit_conversions(said, expected):
    assert calc.convert_units(said) == (True, expected)


@pytest.mark.parametrize("said,expected", [
    ("0 celsius in kelvin", "0 degrees Celsius is 273.15 kelvin."),
    ("72 fahrenheit to celsius", "72 degrees Fahrenheit is 22.22 degrees Celsius."),
    ("100 celsius to fahrenheit", "100 degrees Celsius is 212 degrees Fahrenheit."),
    ("98.6 fahrenheit to celsius", "98.6 degrees Fahrenheit is 37 degrees Celsius."),
    ("-40 celsius to fahrenheit", "negative 40 degrees Celsius is negative 40 degrees Fahrenheit."),
    ("72 degrees fahrenheit to celsius", "72 degrees Fahrenheit is 22.22 degrees Celsius."),
])
def test_temperatures(said, expected):
    assert calc.convert_units(said) == (True, expected)


@pytest.mark.parametrize("said,message", [
    ("5 km to kg", "I can't convert kilometers to kilograms."),
    ("3 parsecs to km", "I don't know one of those units."),
    ("5 celsius to km", "Those units don't go together."),
    ("-300 celsius to fahrenheit", "That's below absolute zero."),
    ("nonsense", "Tell me like this: 10 kilometers in miles."),
    ("", "Tell me like this: 10 kilometers in miles."),
])
def test_unit_conversion_failures(said, message):
    assert calc.convert_units(said) == (False, message)


def test_every_unit_has_a_consistent_definition():
    for key, (category, factor, singular, plural) in calc._UNITS.items():
        assert factor > 0 and singular and plural
        assert calc._find_unit(key) == key
        assert calc._find_unit(singular) == key and calc._find_unit(plural) == key
        assert category in {"length", "mass", "volume", "speed", "area", "time", "data"}


def test_round_trips_are_consistent():
    for a, b in [("km", "mi"), ("kg", "lb"), ("l", "gal"), ("h", "min"), ("acre", "m2"), ("mph", "km/h")]:
        _, forward = calc.convert_units(f"7 {a} to {b}")
        value = float(forward.split(" is ")[1].split(" ")[0].replace(",", ""))
        _, back = calc.convert_units(f"{value} {b} to {a}")
        assert float(back.split(" is ")[1].split(" ")[0].replace(",", "")) == pytest.approx(7, rel=2e-3)
