"""
tools/calc.py

Arithmetic and unit conversion, worked out on this Mac with no internet and no language model
(small models are unreliable at both). Each function returns (ok, message), ready to be spoken.

Maths is worked out by walking the parsed syntax tree with a whitelist of arithmetic operations;
nothing is ever executed as code. Only plain arithmetic is accepted, so nothing a person says (or a
microphone mishears) can run anything.
"""

import ast
import math
import re

MAX_EXPONENT = 1000
MAX_MAGNITUDE = 1e300


class CalcError(Exception):
    """The expression can't be worked out. The message is speakable."""


# ── number formatting ────────────────────────────────────────────────────────

def format_number(x: float) -> str:
    """1081 -> '1,081'; 6.2137 -> '6.214'; 0.00254 -> '0.00254'; -3.5 -> 'negative 3.5'."""
    if math.isnan(x) or math.isinf(x):
        raise CalcError("That's too big for me to say.")
    if x < 0:
        return "negative " + format_number(-x)
    if x == int(x) and x < 1e15:
        return f"{int(x):,}"
    if x >= 1000:
        return f"{x:,.0f}" if x >= 10000 else f"{x:,.1f}".rstrip("0").rstrip(".")
    text = f"{x:.4g}"
    if "e" in text:
        text = f"{x:.10f}".rstrip("0").rstrip(".")
    return text


# ── arithmetic ───────────────────────────────────────────────────────────────

_WORD_OPERATORS = [
    (r"\bto the power of\b|\bto the power\b|\braised to\b", " ** "),
    (r"\bmultiplied by\b|\btimes\b|\bmultiply\b", " * "),
    (r"\bdivided by\b|\bover\b", " / "),
    (r"\bplus\b|\band\b", " + "),
    (r"\bminus\b|\bless\b|\btake away\b", " - "),
    (r"\bmodulo\b|\bmod\b|\bremainder\b", " % "),
    (r"\bsquared\b", " ** 2 "),
    (r"\bcubed\b", " ** 3 "),
]


def _normalise(text: str) -> str:
    t = text.lower().replace(",", "").replace("×", "*").replace("÷", "/").replace("−", "-").replace("^", "**")
    t = re.sub(r"(?<=\d)\s*x\s*(?=\d)", " * ", t)                    # "5 x 3"
    t = re.sub(r"\bsquare root of ([\d.]+)", r"(\1 ** 0.5)", t)
    t = re.sub(r"\bcube root of ([\d.]+)", r"(\1 ** (1/3))", t)
    # "15% of 240", "15 percent of 240" -> (15 / 100) * 240
    t = re.sub(r"([\d.]+)\s*(?:%|percent|per cent)\s*of\s*([\d.]+)", r"((\1 / 100) * \2)", t)
    t = re.sub(r"([\d.]+)\s*(?:%|percent|per cent)", r"(\1 / 100)", t)
    for pattern, symbol in _WORD_OPERATORS:
        t = re.sub(pattern, symbol, t)
    return re.sub(r"\s+", " ", t).strip()


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _evaluate(node.operand)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        a, b = _evaluate(node.left), _evaluate(node.right)
        op = node.op
        if isinstance(op, ast.Add):
            result = a + b
        elif isinstance(op, ast.Sub):
            result = a - b
        elif isinstance(op, ast.Mult):
            result = a * b
        elif isinstance(op, (ast.Div, ast.Mod)):
            if b == 0:
                raise CalcError("You can't divide by zero.")
            result = a / b if isinstance(op, ast.Div) else a % b
        elif isinstance(op, ast.Pow):
            if abs(b) > MAX_EXPONENT or (abs(a) > 1 and abs(b) * math.log10(abs(a)) > 300):
                raise CalcError("That's too big for me to work out.")
            try:
                result = a ** b
            except (ZeroDivisionError, OverflowError) as e:
                raise CalcError("I can't work that one out.") from e
            if isinstance(result, complex):
                raise CalcError("That doesn't have a real answer.")
        else:
            raise CalcError("I can only do simple arithmetic.")
        if abs(result) > MAX_MAGNITUDE:
            raise CalcError("That's too big for me to say.")
        return result
    raise CalcError("I can only do simple arithmetic.")


def calculate(spoken: str | None) -> tuple[bool, str]:
    text = (spoken or "").strip()
    expression = _normalise(text)
    # Only digits, spaces, dots, brackets and the arithmetic operators survive.
    if not expression or not re.fullmatch(r"[\d\s.()+\-*/%]+", expression) or not re.search(r"\d", expression):
        return False, "I couldn't work that out."
    try:
        tree = ast.parse(expression, mode="eval")
        value = _evaluate(tree)
    except CalcError as e:
        return False, str(e)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return False, "I couldn't work that out."
    spoken = re.sub(r"\s+", " ", text.rstrip("?.!"))
    return True, f"{spoken} is {format_number(value)}."


# ── units ────────────────────────────────────────────────────────────────────
# canonical key -> (category, factor to the category's base unit, spoken singular, spoken plural)

_UNITS: dict[str, tuple[str, float, str, str]] = {}
_ALIASES: dict[str, str] = {}


def _unit(key: str, category: str, factor: float, singular: str, plural: str, *aliases: str) -> None:
    _UNITS[key] = (category, factor, singular, plural)
    for a in (key, singular, plural, *aliases):
        _ALIASES[a.lower()] = key


# length (base: metre)
_unit("mm", "length", 0.001, "millimeter", "millimeters", "millimetre", "millimetres")
_unit("cm", "length", 0.01, "centimeter", "centimeters", "centimetre", "centimetres")
_unit("m", "length", 1.0, "meter", "meters", "metre", "metres")
_unit("km", "length", 1000.0, "kilometer", "kilometers", "kilometre", "kilometres", "k", "kays")
_unit("in", "length", 0.0254, "inch", "inches", '"')
_unit("ft", "length", 0.3048, "foot", "feet", "'")
_unit("yd", "length", 0.9144, "yard", "yards")
_unit("mi", "length", 1609.344, "mile", "miles")
_unit("nmi", "length", 1852.0, "nautical mile", "nautical miles")
# mass (base: gram)
_unit("mg", "mass", 0.001, "milligram", "milligrams")
_unit("g", "mass", 1.0, "gram", "grams")
_unit("kg", "mass", 1000.0, "kilogram", "kilograms", "kilo", "kilos")
_unit("t", "mass", 1_000_000.0, "metric ton", "metric tons", "tonne", "tonnes")
_unit("oz", "mass", 28.349523125, "ounce", "ounces")
_unit("lb", "mass", 453.59237, "pound", "pounds", "lbs")
_unit("st", "mass", 6350.29318, "stone", "stones")
# volume (base: litre)
_unit("ml", "volume", 0.001, "milliliter", "milliliters", "millilitre", "millilitres")
_unit("l", "volume", 1.0, "liter", "liters", "litre", "litres")
_unit("tsp", "volume", 0.00492892159375, "teaspoon", "teaspoons")
_unit("tbsp", "volume", 0.01478676478125, "tablespoon", "tablespoons")
_unit("floz", "volume", 0.0295735295625, "fluid ounce", "fluid ounces")
_unit("cup", "volume", 0.2365882365, "cup", "cups")
_unit("pt", "volume", 0.473176473, "pint", "pints")
_unit("qt", "volume", 0.946352946, "quart", "quarts")
_unit("gal", "volume", 3.785411784, "gallon", "gallons")
# speed (base: metre per second)
_unit("m/s", "speed", 1.0, "meter per second", "meters per second", "metres per second", "metre per second")
_unit("km/h", "speed", 1 / 3.6, "kilometer per hour", "kilometers per hour", "kilometres per hour", "kph", "kmh", "kilometre per hour")
_unit("mph", "speed", 0.44704, "mile per hour", "miles per hour")
_unit("kn", "speed", 0.514444, "knot", "knots")
# area (base: square metre)
_unit("m2", "area", 1.0, "square meter", "square meters", "square metre", "square metres")
_unit("km2", "area", 1e6, "square kilometer", "square kilometers", "square kilometre", "square kilometres")
_unit("ft2", "area", 0.09290304, "square foot", "square feet")
_unit("mi2", "area", 2589988.110336, "square mile", "square miles")
_unit("ha", "area", 10000.0, "hectare", "hectares")
_unit("acre", "area", 4046.8564224, "acre", "acres")
# time (base: second)
_unit("s", "time", 1.0, "second", "seconds", "sec", "secs")
_unit("min", "time", 60.0, "minute", "minutes", "mins")
_unit("h", "time", 3600.0, "hour", "hours", "hr", "hrs")
_unit("d", "time", 86400.0, "day", "days")
_unit("wk", "time", 604800.0, "week", "weeks")
# digital storage (base: byte)
_unit("B", "data", 1.0, "byte", "bytes")
_unit("KB", "data", 1e3, "kilobyte", "kilobytes")
_unit("MB", "data", 1e6, "megabyte", "megabytes")
_unit("GB", "data", 1e9, "gigabyte", "gigabytes", "gigs", "gig")
_unit("TB", "data", 1e12, "terabyte", "terabytes")
# temperature is handled separately (it is not a simple factor)
_TEMPS = {"c": "C", "celsius": "C", "centigrade": "C", "degrees celsius": "C", "degree celsius": "C",
          "f": "F", "fahrenheit": "F", "degrees fahrenheit": "F", "degree fahrenheit": "F",
          "k": "K", "kelvin": "K", "kelvins": "K"}
_TEMP_NAMES = {"C": "degrees Celsius", "F": "degrees Fahrenheit", "K": "kelvin"}


def unit_words() -> list[str]:
    """Every unit word the router may match, longest first."""
    return sorted(set(_ALIASES) | set(_TEMPS), key=len, reverse=True)


def _find_unit(word: str) -> str | None:
    w = re.sub(r"\s+", " ", word.strip().lower())
    if w in _TEMPS:
        return "temp:" + _TEMPS[w]
    return _ALIASES.get(w) if w != "k" else "temp:K"


def parse_unit_request(value: str) -> tuple[float, str, str] | None:
    """'10 km to miles' -> (10.0, 'km', 'miles'). The amount defaults to 1."""
    m = re.fullmatch(r"\s*(-?[\d,]*\.?\d+)?\s*([a-z][a-z0-9 /]*?)\s+(?:to|in|into)\s+([a-z][a-z0-9 /]*?)\s*", (value or "").lower())
    if not m:
        return None
    amount = float(m.group(1).replace(",", "")) if m.group(1) else 1.0
    return amount, m.group(2), m.group(3)


def _to_kelvin(x: float, u: str) -> float:
    return {"C": x + 273.15, "F": (x - 32) * 5 / 9 + 273.15, "K": x}[u]


def _from_kelvin(k: float, u: str) -> float:
    return {"C": k - 273.15, "F": (k - 273.15) * 9 / 5 + 32, "K": k}[u]


def _degrees(x: float) -> str:
    """Temperatures keep two decimals (273.15, 22.22) rather than four significant digits."""
    r = round(x, 2)
    text = f"{abs(r):,.2f}".rstrip("0").rstrip(".")
    return ("negative " if r < 0 else "") + text


def convert_units(value: str | None) -> tuple[bool, str]:
    parsed = parse_unit_request(value or "")
    if parsed is None:
        return False, "Tell me like this: 10 kilometers in miles."
    amount, src_word, dst_word = parsed
    src, dst = _find_unit(src_word), _find_unit(dst_word)
    if src is None or dst is None:
        return False, "I don't know one of those units."

    if src.startswith("temp:") or dst.startswith("temp:"):
        if not (src.startswith("temp:") and dst.startswith("temp:")):
            return False, "Those units don't go together."
        s, d = src[5:], dst[5:]
        if _to_kelvin(amount, s) < 0:
            return False, "That's below absolute zero."
        result = _from_kelvin(_to_kelvin(amount, s), d)
        return True, f"{_degrees(amount)} {_TEMP_NAMES[s]} is {_degrees(result)} {_TEMP_NAMES[d]}."

    (cat_s, f_s, sing_s, plur_s), (cat_d, f_d, sing_d, plur_d) = _UNITS[src], _UNITS[dst]
    if cat_s != cat_d:
        return False, f"I can't convert {plur_s} to {plur_d}."
    result = amount * f_s / f_d
    name_s = sing_s if amount == 1 else plur_s
    name_d = sing_d if round(result, 3) == 1 else plur_d
    return True, f"{format_number(amount)} {name_s} is {format_number(result)} {name_d}."
