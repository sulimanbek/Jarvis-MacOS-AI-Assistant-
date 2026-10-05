import difflib
import re

from config import BRAIN_MODE
from core.brain_claude import think_claude
from core.brain_local import think_local
from memory.context import (
    get_last_action,
    get_last_app,
    get_last_browser_target,
    get_last_shortcut,
    get_last_song,
)
from tools import live
from tools.browser import WEB_TARGETS

APP_ALIASES = {
    "safari": "Safari",
    "music": "Music",
    "apple music": "Music",
    "spotify": "Spotify",
    "notes": "Notes",
    "calendar": "Calendar",
    "mail": "Mail",
    "messages": "Messages",
    "finder": "Finder",
    "terminal": "Terminal",
    "system settings": "System Settings",
    "settings": "System Settings",
    "photos": "Photos",
    "photo": "Photos",
    "app store": "App Store",
    "store": "App Store",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "facetime": "FaceTime",
    "whatsapp": "WhatsApp",
    "telegram": "Telegram",
    "discord": "Discord",
    "visual studio code": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "pycharm": "PyCharm",
}

ALLOWED_TOOLS = {"app", "music", "shortcut", "browser", "open", "system", None}


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _fuzzy_match(target: str, candidates: list) -> str | None:
    """Tolerate STT mishearings of a known name (e.g. "saffari" -> "safari")
    without over-matching on short/ambiguous strings."""
    if not target or len(target) < 3:
        return None
    matches = difflib.get_close_matches(target, candidates, n=1, cutoff=0.75)
    return matches[0] if matches else None


def _unhandled(response: str, reason: str) -> dict[str, str | None]:
    """Tag a genuine failure/dead-end response (as opposed to a real
    conversational answer) so the executor can log it distinctly, closing
    the loop on what Jarvis couldn't handle."""
    return {"tool": None, "response": response, "_unhandled_reason": reason}


def _strip_trailing_punctuation(text: str) -> str:
    return re.sub(r"[\s.!?,;:]+$", "", text or "")


def _clean_target(text: str) -> str:
    text = (text or "").strip().lower()
    text = text.rstrip(".,!?;:")
    text = text.replace("www.", "")
    text = re.sub(r"^the\s+", "", text)
    text = re.sub(r"\s+website$", "", text)
    text = re.sub(r"\s+site$", "", text)
    return text


def _extract_play_query(original: str, lowered: str) -> str | None:
    match = re.search(r"\bplay\b", lowered)
    if not match:
        return None

    query = original[match.end():].strip()

    fillers = [
        r"^some\s+",
        r"^the\s+song\s+",
        r"^song\s+",
        r"^music\s+",
        r"^on\s+apple\s+music\s+",
        r"^from\s+apple\s+music\s+",
    ]

    for pattern in fillers:
        query = re.sub(pattern, "", query, flags=re.IGNORECASE)

    query = _strip_trailing_punctuation(query)
    return query or None


def _extract_open_target(original: str) -> str | None:
    lowered = original.lower().strip()
    for prefix in ("open ", "launch ", "start "):
        if lowered.startswith(prefix):
            return _clean_target(original[len(prefix):])
    return None


def _extract_open_and_search(original: str, lowered: str) -> dict[str, str | None] | None:
    pattern = r"^(?:open|launch|start)\s+(.+?)\s+(?:and\s+)?search\s+(?:for\s+)?(.+)$"
    match = re.match(pattern, lowered.strip())
    if not match:
        return None

    target = _clean_target(match.group(1))
    query = _strip_trailing_punctuation(original[original.lower().find("search") + len("search"):])
    query = re.sub(r"^\s*for\s+", "", query, flags=re.IGNORECASE).strip()
    query = query.strip('"').strip("'")

    if not target or not query:
        return None

    return {"tool": "browser", "target": target, "query": query}


def _extract_search_on_site(original: str, lowered: str) -> dict[str, str | None] | None:
    patterns = [
        r"^search\s+(.+?)\s+for\s+(.+)$",   # search youtube for ai news
        r"^find\s+(.+?)\s+on\s+(.+)$",      # find ai news on youtube
        r"^look\s+up\s+(.+?)\s+on\s+(.+)$", # look up ai news on youtube
    ]

    for pattern in patterns:
        match = re.match(pattern, lowered.strip())
        if not match:
            continue

        if pattern.startswith("^search"):
            target_raw = match.group(1)
            query_raw = match.group(2)
        else:
            query_raw = match.group(1)
            target_raw = match.group(2)

        target = _clean_target(target_raw)
        query = _strip_trailing_punctuation(query_raw).strip().strip('"').strip("'")
        if target and query:
            return {"tool": "browser", "target": target, "query": query}

    return None


def _is_repeat_music_request(lowered: str) -> bool:
    phrases = [
        "play it again",
        "play that again",
        "play the song again",
        "play it",
        "play that",
        "play the song",
    ]
    return any(phrase in lowered for phrase in phrases)


def _is_repeat_open_request(lowered: str) -> bool:
    phrases = [
        "open it again",
        "open that again",
        "launch it again",
        "start it again",
    ]
    return any(phrase in lowered for phrase in phrases)


def _route_memory(lowered: str) -> dict[str, str | None] | None:
    if "what was that song" in lowered or "what song was that" in lowered:
        last_song = get_last_song()
        if last_song:
            return {"tool": None, "response": f"The last song was {last_song}."}
        return _unhandled("I don't remember the last song yet.", "music_memory_missing")

    if _is_repeat_music_request(lowered):
        last_song = get_last_song()
        if last_song:
            return {"tool": "music", "query": last_song}
        return _unhandled("I don't know which song you mean yet.", "music_memory_missing")

    if "open the last app" in lowered:
        last_app = get_last_app()
        if last_app:
            return {"tool": "app", "name": last_app}
        return _unhandled("I don't remember the last app yet.", "app_memory_missing")

    if _is_repeat_open_request(lowered):
        last_action = get_last_action() or {}
        action_type = last_action.get("type")
        action_value = last_action.get("value")

        if action_type == "app" and action_value:
            return {"tool": "app", "name": action_value}

        if action_type == "browser" and action_value:
            return {"tool": "browser", "target": action_value}

        if action_type == "open" and action_value:
            return {"tool": "open", "target": action_value}

        last_target = get_last_browser_target()
        if last_target:
            return {"tool": "browser", "target": last_target}

        last_app = get_last_app()
        if last_app:
            return {"tool": "app", "name": last_app}

        return _unhandled("I don't know what you want me to open again yet.", "open_memory_missing")

    if "run that shortcut again" in lowered or "run the last shortcut" in lowered:
        last_shortcut = get_last_shortcut()
        if last_shortcut:
            return {"tool": "shortcut", "name": last_shortcut}
        return _unhandled("I don't remember the last shortcut yet.", "shortcut_memory_missing")

    if "do that again" in lowered:
        last_action = get_last_action() or {}
        action_type = last_action.get("type")
        action_value = last_action.get("value")

        if action_type == "music" and action_value:
            return {"tool": "music", "query": action_value}

        if action_type == "app" and action_value:
            return {"tool": "app", "name": action_value}

        if action_type == "browser" and action_value:
            return {"tool": "browser", "target": action_value}

        if action_type == "open" and action_value:
            return {"tool": "open", "target": action_value}

        if action_type == "shortcut" and action_value:
            return {"tool": "shortcut", "name": action_value}

        if action_type == "system" and action_value:
            return {"tool": "system", "action": action_value}

        return _unhandled("I don't remember the last action yet.", "action_memory_missing")

    return None


def _route_system(lowered: str) -> dict[str, str | None] | None:
    if any(phrase in lowered for phrase in ["volume up", "increase volume", "turn it up", "raise volume"]):
        return {"tool": "system", "action": "volume_up"}

    if any(phrase in lowered for phrase in ["volume down", "decrease volume", "turn it down", "lower volume"]):
        return {"tool": "system", "action": "volume_down"}

    if any(phrase in lowered for phrase in ["mute", "mute volume", "silence audio"]):
        return {"tool": "system", "action": "mute"}

    if any(phrase in lowered for phrase in ["unmute", "turn sound back on"]):
        return {"tool": "system", "action": "unmute"}

    if any(phrase in lowered for phrase in ["lock screen", "lock the screen", "lock my mac"]):
        return {"tool": "system", "action": "lock_screen"}

    if any(phrase in lowered for phrase in ["sleep display", "turn off display", "turn off the screen"]):
        return {"tool": "system", "action": "sleep_display"}

    if any(phrase in lowered for phrase in ["battery status", "battery level", "how much battery do i have"]):
        return {"tool": "system", "action": "battery_status"}

    if any(phrase in lowered for phrase in ["current volume", "what's the volume", "what is the volume", "volume status", "volume level"]):
        return {"tool": "system", "action": "volume_status"}

    if any(phrase in lowered for phrase in ["brightness up", "increase brightness", "brighten the screen", "brighten the display"]):
        return {"tool": "system", "action": "brightness_up"}

    if any(phrase in lowered for phrase in ["brightness down", "decrease brightness", "dim the screen", "dim the display"]):
        return {"tool": "system", "action": "brightness_down"}

    if any(phrase in lowered for phrase in ["read my clipboard", "what's on my clipboard", "what is on my clipboard", "check my clipboard", "check clipboard"]):
        return {"tool": "system", "action": "clipboard_read"}

    if any(phrase in lowered for phrase in ["take a screenshot", "take screenshot", "capture the screen", "capture my screen"]):
        return {"tool": "system", "action": "screenshot"}

    return None


# Words that mean "change something" rather than "read it out". "schedule" and "new" are
# deliberately NOT here as bare words: "check my schedule" and "any new emails" are reads.
# "schedule" only counts as an edit when used as a verb ("schedule a meeting").
_EDIT_VERBS = re.compile(
    r"\b(add|create|put|make|set|book|cancel|delete|remove|move|reschedule|"
    r"send|compose|write|reply|forward|draft)\b"
    r"|\bschedule (?:a|an|another|me|us|it|something|some)\b"
)


def _sys(action: str) -> dict[str, str | None]:
    return {"tool": "system", "action": action}


def _route_apps(lowered: str) -> dict[str, str | None] | None:
    """Music controls, calendar, mail and shortcut listing: answered locally."""
    t = _strip_trailing_punctuation(lowered).replace("\u2019", "'")

    # Music transport. Anchored, so ordinary sentences containing these words
    # ("the pause in the film") are not taken for commands.
    if re.fullmatch(r"(?:please )?(?:pause|hold)(?: the)?(?: music| song| track| playback| it)?", t):
        return _sys("pause")
    if re.fullmatch(r"(?:please )?(?:resume|unpause)(?: the)?(?: music| song| track| playback| it)?"
                    r"|keep playing|continue (?:the )?(?:music|song)", t):
        return _sys("resume")
    if re.fullmatch(r"(?:please )?(?:next|skip)(?: this| the)?(?: song| track)?"
                    r"|(?:play )?(?:the )?next (?:song|track)", t):
        return _sys("next_track")
    if re.fullmatch(r"(?:please )?(?:previous|go back)(?: a| the)?(?: song| track)?"
                    r"|(?:play )?(?:the )?previous (?:song|track)", t):
        return _sys("previous_track")
    if re.fullmatch(r"what(?:'s| is)(?: currently)? playing(?: now| right now)?"
                    r"|what song is (?:this|playing)(?: now)?|what(?:'s| is) this song", t):
        return _sys("now_playing")

    # Listing shortcuts (running one is handled further down).
    if re.search(r"\b(?:what|which|list)\b.*\bshortcuts\b", t) and "run" not in t:
        return _sys("shortcuts_list")

    if _EDIT_VERBS.search(t):
        return None  # asking to change something, not to read it

    # Calendar.
    if re.search(r"\bnext (?:meeting|event|appointment)\b|\bwhat'?s next on my (?:calendar|schedule)\b", t):
        return _sys("calendar_next")
    if (re.search(r"\b(?:my|the) (?:calendar|schedule|agenda)\b", t)
            or re.search(r"\bdo i have (?:any )?(?:meetings|events|appointments)\b", t)
            or re.search(r"\bwhat do i have (?:on )?today\b", t)):
        return _sys("calendar_today")

    # Mail (read-only).
    if (re.search(r"\b(?:check|read)\b.*\b(?:e-?mails?|mail|inbox)\b", t)
            or re.search(r"\bdo i have (?:any )?(?:new |unread )?(?:e-?mails?|mail)\b", t)
            or re.search(r"\b(?:any|unread|new) (?:new |unread )?(?:e-?mails?|mail)\b", t)
            or re.search(r"\bwhat'?s in my inbox\b|\bhow many unread\b", t)):
        return _sys("mail_unread")

    return None


# ── Live data: weather, news, time, prices, facts ───────────────────────────

# A phrase that starts like this is about something else ("open the weather app").
_NOT_A_QUESTION = re.compile(
    r"^(?:open|launch|start|play|close|quit|go to|set|add|create|remind|note|turn|text|send|write|"
    r"install|download|search|google|look up|take|make|schedule|cancel|delete)\b"
)
_TAIL = r"(?: (?:right now|now|today|tonight|tomorrow|outside|currently|please))*"
_CITY = r"(?: in (?P<city>[a-z][a-z .'-]{1,40}?))?"

_CURRENCIES = {
    "us dollars": "USD", "us dollar": "USD", "american dollars": "USD", "dollars": "USD", "dollar": "USD", "usd": "USD", "bucks": "USD",
    "euros": "EUR", "euro": "EUR", "eur": "EUR",
    "british pounds": "GBP", "pounds sterling": "GBP", "pounds": "GBP", "pound": "GBP", "gbp": "GBP",
    "dirhams": "AED", "dirham": "AED", "aed": "AED", "emirati dirhams": "AED", "uae dirhams": "AED",
    "saudi riyals": "SAR", "riyals": "SAR", "riyal": "SAR", "sar": "SAR",
    "yen": "JPY", "jpy": "JPY", "rupees": "INR", "rupee": "INR", "indian rupees": "INR", "inr": "INR",
    "canadian dollars": "CAD", "cad": "CAD", "australian dollars": "AUD", "aud": "AUD",
    "swiss francs": "CHF", "francs": "CHF", "chf": "CHF", "yuan": "CNY", "cny": "CNY", "renminbi": "CNY",
    "turkish lira": "TRY", "lira": "TRY", "kuwaiti dinars": "KWD", "dinars": "KWD", "kwd": "KWD",
    "egyptian pounds": "EGP", "egp": "EGP", "qatari riyals": "QAR", "qar": "QAR",
    "pakistani rupees": "PKR", "pkr": "PKR", "rubles": "RUB", "rand": "ZAR",
    "singapore dollars": "SGD", "sgd": "SGD", "pesos": "MXN", "won": "KRW",
}
_CUR = "|".join(sorted(map(re.escape, _CURRENCIES), key=len, reverse=True))
_COIN = "|".join(sorted(map(re.escape, live.COINS), key=len, reverse=True))
_SITE_WORDS = {"youtube", "github", "netflix", "google", "reddit", "amazon", "twitter", "linkedin", "spotify", "wikipedia"}
_PRONOUN_START = re.compile(r"^(?:the|a|an|my|your|our|this|that|it|there|he|she|they|we|you|i|going|gonna|best|worst|calling|at)\b")


def _route_live(original: str, lowered: str) -> dict[str, str | None] | None:
    t = _strip_trailing_punctuation(lowered).replace("\u2019", "'")
    t = re.sub(r"^(?:hey |ok |okay )?(?:jarvis[,]? )?(?:please |can you |could you )?", "", t)
    if not t or _NOT_A_QUESTION.match(t) or len(t.split()) > 12:
        return None
    # "the weather app", "the news channel": a thing, not a question about the weather or news.
    if re.search(r"\b(?:app|apps|channel|widget|icon|website|site|extension|station|podcast)$", t):
        return None

    def act(action: str, value: str | None = None) -> dict[str, str | None]:
        return {"tool": "system", "action": action, **({"value": value} if value else {})}

    # Time and date. No internet needed for your own clock.
    m = re.fullmatch(r"(?:what(?:'s| is)? the |what time is it|tell me the )(?:current )?(?:time)?(?: right now| now)?" + _CITY + _TAIL, t) \
        if re.match(r"(?:what time is it|what(?:'s| is)? the (?:current )?time|tell me the time)", t) else None
    if m:
        return act("time_now", (m.group("city") or "").strip() or None)
    if re.fullmatch(r"what(?:'s| is)(?: the| today'?s)? (?:date|day)(?: (?:it is|is it))?(?: today)?|what day is it(?: today)?|what(?:'s| is) today'?s date", t):
        return act("date_today")

    # Weather and forecast.
    if re.search(r"\b(?:weather|forecast|temperature)\b|\bhow (?:hot|cold|warm) is it\b|\b(?:is it|will it)(?: going to| gonna)? (?:rain|snow)\b|\bis it raining\b", t):
        city = re.search(r" in (?P<city>[a-z][a-z .'-]{1,40}?)" + _TAIL + "$", t)
        place = (city.group("city").strip() if city else None) or None
        return act("weather_tomorrow" if "tomorrow" in t else "weather", place)

    # News.
    m = re.fullmatch(r"(?:(?:what(?:'s| is)|tell me|give me|read me|read|get me|show me)(?: me)?(?: the)? )?(?:the )?(?:latest |top |today'?s |breaking |current )*(?:news|headlines)"
                     r"(?: (?:today|now|right now))?(?: (?:about|on|for|regarding) (?P<topic>.+))?", t) \
        or re.fullmatch(r"what(?:'s| is) (?:going on|happening) in the world(?: today| right now)?|what(?:'s| is) in the news", t)
    if m:
        topic = (m.groupdict().get("topic") or "").strip()
        return act("news", topic or None)

    # Crypto prices (a named list only).
    m = (re.fullmatch(r"(?:what(?:'s| is) )?(?:the )?(?:current )?price (?:of|for) (?P<c>" + _COIN + r")" + _TAIL, t)
         or re.fullmatch(r"how much is (?:a |one |1 )?(?P<c>" + _COIN + r")(?: worth| coin)?" + _TAIL, t)
         or re.fullmatch(r"(?:what(?:'s| is) )?(?:the )?(?P<c>" + _COIN + r")(?: coin)? (?:price|rate)" + _TAIL, t)
         or re.fullmatch(r"what(?:'s| is) (?P<c>" + _COIN + r") (?:at|trading at|worth)" + _TAIL, t))
    if m:
        return act("price", m.group("c"))

    # Currency.
    amount = r"(?P<amt>\d[\d,]*\.?\d*|a|one|an)?"
    m = (re.fullmatch(r"(?:how much is|what(?:'s| is)|convert) " + amount + r" ?(?P<src>" + _CUR + r") (?:in|to|into) (?P<dst>" + _CUR + r")" + _TAIL, t)
         or re.fullmatch(r"(?:the )?(?:exchange rate|rate)(?: (?:from|of))? " + amount + r" ?(?P<src>" + _CUR + r") (?:to|in|into|against) (?P<dst>" + _CUR + r")" + _TAIL, t)
         # "100 dollars in dirhams": with no lead-in, an actual amount is required so ordinary talk isn't caught
         or re.fullmatch(r"(?P<amt>\d[\d,]*\.?\d*|a|one|an) ?(?P<src>" + _CUR + r") (?:in|to|into) (?P<dst>" + _CUR + r")" + _TAIL, t))
    if m:
        amt = (m.group("amt") or "1").replace(",", "")
        amt = "1" if amt in ("a", "an", "one") else amt
        return act("convert", f"{amt} {_CURRENCIES[m.group('src')]} to {_CURRENCIES[m.group('dst')]}")

    # Facts about a person or thing.
    m = re.fullmatch(r"(?P<lead>who (?:is|was)|tell me about|wikipedia) (?P<topic>.+)", t)
    if m:
        topic = m.group("topic").strip()
        # "who is the president" needs live information (Claude), but "tell me about the Roman
        # Empire" is an encyclopedia question; "the weather" and "the news" were handled above.
        if m.group("lead") == "tell me about" and topic.startswith("the "):
            topic = topic[4:]
        if (topic and len(topic.split()) <= 5 and not _PRONOUN_START.match(topic)
                and topic not in ("you", "me", "yourself", "weather", "news", "time", "date", "day")):
            return act("wiki", topic)
    return None


def _extract_web_search(lowered: str) -> str | None:
    """The query from "search the web for X", "google X", "look up X"; None if it names a site."""
    t = _strip_trailing_punctuation(lowered).replace("\u2019", "'")
    t = re.sub(r"^(?:hey |ok |okay )?(?:jarvis[,]? )?(?:please |can you |could you )?", "", t)
    m = (re.fullmatch(r"(?:web search|search (?:the )?(?:web|internet|online|google))(?: for| about)? (?P<q>.+)", t)
         or re.fullmatch(r"search for (?P<q>.+)", t)
         or re.fullmatch(r"(?:google|look up|lookup) (?P<q>.+)", t))
    if not m:
        return None
    query = m.group("q").strip()
    site = re.search(r" on (?P<s>[a-z]+)$", query)
    if not query or (site and site.group("s") in _SITE_WORDS) or query in _SITE_WORDS:
        return None
    return query


def _extract_reminder_text(original: str, lowered: str) -> str | None:
    patterns = [
        r"^remind me to\s+(.+)$",
        r"^remind me\s+(.+)$",
        r"^set a reminder to\s+(.+)$",
        r"^add a reminder to\s+(.+)$",
        r"^add a reminder\s+(.+)$",
        r"^create a reminder to\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, lowered.strip())
        if match:
            text = _strip_trailing_punctuation(original[match.start(1):].strip())
            return text or None
    return None


def _extract_note_text(original: str, lowered: str) -> str | None:
    patterns = [
        r"^take a note\s*(?:that|:)?\s+(.+)$",
        r"^add a note\s*(?:that|:)?\s+(.+)$",
        r"^make a note\s*(?:that|:)?\s+(.+)$",
        r"^note that\s+(.+)$",
        r"^note\s*:\s*(.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, lowered.strip())
        if match:
            text = _strip_trailing_punctuation(original[match.start(1):].strip())
            return text or None
    return None


def _route_fast(original: str, lowered: str) -> dict[str, str | None] | None:
    memory_decision = _route_memory(lowered)
    if memory_decision:
        return memory_decision

    system_decision = _route_system(lowered)
    if system_decision:
        return system_decision

    apps_decision = _route_apps(lowered)
    if apps_decision:
        return apps_decision

    live_decision = _route_live(original, lowered)
    if live_decision:
        return live_decision

    reminder_text = _extract_reminder_text(original, lowered)
    if reminder_text:
        return {"tool": "system", "action": "reminder_add", "value": reminder_text}

    note_text = _extract_note_text(original, lowered)
    if note_text:
        return {"tool": "system", "action": "note_add", "value": note_text}

    web_search_decision = _extract_open_and_search(original, lowered)
    if web_search_decision:
        return web_search_decision

    search_site_decision = _extract_search_on_site(original, lowered)
    if search_site_decision:
        return search_site_decision

    if re.search(r"\bplay\b", lowered):
        query = _extract_play_query(original, lowered)
        if query:
            if query.lower() in {"it", "that", "the song"}:
                last_song = get_last_song()
                if last_song:
                    return {"tool": "music", "query": last_song}
                return _unhandled("I don't know which song you mean yet.", "music_memory_missing")
            return {"tool": "music", "query": query}

    open_target = _extract_open_target(original)
    if open_target:
        if open_target in APP_ALIASES:
            return {"tool": "app", "name": APP_ALIASES[open_target]}

        for alias, app_name in APP_ALIASES.items():
            if alias in open_target or open_target in alias:
                return {"tool": "app", "name": app_name}

        if open_target in WEB_TARGETS:
            return {"tool": "browser", "target": open_target}

        # Tolerate STT mishearings of a known app/site name before giving up
        # and treating it as a generic (unknown) open/search target.
        fuzzy_app = _fuzzy_match(open_target, list(APP_ALIASES.keys()))
        if fuzzy_app:
            return {"tool": "app", "name": APP_ALIASES[fuzzy_app]}

        fuzzy_site = _fuzzy_match(open_target, list(WEB_TARGETS.keys()))
        if fuzzy_site:
            return {"tool": "browser", "target": fuzzy_site}

        return {"tool": "open", "target": open_target}

    if "shortcut" in lowered:
        return {"tool": "shortcut", "name": original}

    return None


def _validate_decision(decision: dict) -> dict[str, str | None]:
    if not isinstance(decision, dict):
        return _unhandled("I had trouble understanding that.", "malformed_llm_output")

    tool = decision.get("tool")
    if tool not in ALLOWED_TOOLS:
        return _unhandled("I had trouble deciding what to do.", "disallowed_tool")

    if tool == "app":
        name = (decision.get("name") or "").strip()
        if not name:
            return _unhandled("I couldn't figure out which app to open.", "app_name_missing")
        return {"tool": "app", "name": name}

    if tool == "music":
        query = (decision.get("query") or "").strip()
        if not query:
            return _unhandled("I couldn't figure out what to play.", "music_query_missing")
        return {"tool": "music", "query": query}

    if tool == "shortcut":
        name = (decision.get("name") or "").strip()
        if not name:
            return _unhandled("I couldn't figure out which shortcut to run.", "shortcut_name_missing")
        return {"tool": "shortcut", "name": name}

    if tool == "browser":
        target = (decision.get("target") or "").strip()
        if not target:
            return _unhandled("I couldn't figure out what website to open.", "browser_target_missing")
        query = (decision.get("query") or "").strip()
        if query:
            return {"tool": "browser", "target": _clean_target(target), "query": query}
        return {"tool": "browser", "target": _clean_target(target)}

    if tool == "open":
        target = (decision.get("target") or "").strip()
        if not target:
            return _unhandled("I couldn't figure out what to open.", "open_target_missing")
        return {"tool": "open", "target": _clean_target(target)}

    if tool == "system":
        action = (decision.get("action") or "").strip()
        if not action:
            return _unhandled("I couldn't figure out which system action to perform.", "system_action_missing")
        value = (decision.get("value") or "").strip()
        result: dict[str, str | None] = {"tool": "system", "action": action}
        if value:
            result["value"] = value
        return result

    response = (decision.get("response") or "").strip()
    if not response:
        return _unhandled("I didn't catch that.", "llm_empty_response")
    return {"tool": None, "response": response}


def _route_llm(original: str) -> dict[str, str | None]:
    # Claude first when enabled. It returns None if the bridge is down or its
    # turn failed, and then the local model takes over exactly as before.
    if BRAIN_MODE == "claude":
        claude_decision = think_claude(original)
        if claude_decision is not None:
            return claude_decision
    return _validate_decision(think_local(original))


# Verbs that signal independent actions in a compound command
_ACTION_VERBS = re.compile(
    r"\b(open|launch|start|play|search|go to|navigate|check|mute|unmute|"
    r"turn up|turn down|close|lock|sleep|run)\b"
)

_SEQUENCE_PHRASES = (
    " and then ", " after that ", " followed by ", " then ", " also ",
)


def _is_multi_step(lowered: str) -> bool:
    """
    Return True when the command is clearly compound — multiple independent
    actions that need to be sequenced rather than a single tool call.
    """
    # Explicit sequencing language
    if any(phrase in lowered for phrase in _SEQUENCE_PHRASES):
        return True

    # Two or more distinct action verbs with a conjunction between them
    verb_matches = _ACTION_VERBS.findall(lowered)
    return len(verb_matches) >= 2 and " and " in lowered


def route(text: str) -> dict[str, str | None]:
    original = _normalize_text(text)
    lowered  = original.lower()

    if not original:
        return _unhandled("I didn't catch that.", "empty_input")

    # 1. Multi-step detection: hand off to agent pipeline before any
    #    single-action fast-path can greedily swallow part of a compound
    #    command (e.g. "open Safari and then play some music" must not
    #    collapse into a bare music decision).
    if _is_multi_step(lowered):
        return {"tool": "__agent__", "text": original}

    # 1b. A general web search: Claude does it properly (it has live search). If Claude isn't
    #     available, fall back to Wikipedia and the news rather than guessing.
    web_query = _extract_web_search(lowered)
    if web_query:
        if BRAIN_MODE == "claude":
            claude_decision = think_claude(original)
            if claude_decision is not None:
                return claude_decision
        return {"tool": "system", "action": "web_search", "value": web_query}

    # 2. Fast-path: regex/string matching (zero LLM cost)
    fast_decision = _route_fast(original, lowered)
    if fast_decision:
        return fast_decision

    # 3. Single-tool LLM fallback
    return _route_llm(original)