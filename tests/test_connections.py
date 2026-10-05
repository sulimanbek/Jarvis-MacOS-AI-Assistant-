import subprocess
from datetime import datetime

import pytest

from core import executor, mac_actions, router
from core.system_actions import SYSTEM_ACTIONS
from tools import calendar as cal
from tools import mail, media, shortcuts


def _proc(stdout="", returncode=0):
    return subprocess.CompletedProcess(args=["osascript"], returncode=returncode, stdout=stdout, stderr="")


# ── media ───────────────────────────────────────────────────────────────────

class FakeMusic:
    """Stands in for osascript: records every script and answers per script."""

    def __init__(self, running=True, state_line="playing|Starboy|The Weeknd", fail=False):
        self.running, self.state_line, self.fail, self.scripts = running, state_line, fail, []

    def __call__(self, script, timeout=12):
        self.scripts.append(script)
        if self.fail:
            return _proc(returncode=1)
        if "is running" in script:
            return _proc("true" if self.running else "false")
        if "player state" in script:
            return _proc(self.state_line)
        return _proc("")


@pytest.fixture
def music(monkeypatch):
    fake = FakeMusic()
    monkeypatch.setattr(media, "run_applescript", fake)
    return fake


@pytest.mark.parametrize("fn", [media.pause_music, media.resume_music, media.next_track,
                                media.previous_track, media.now_playing])
def test_media_never_launches_music_when_it_is_closed(fn, music):
    music.running = False
    ok, message = fn()
    assert ok is False and message == media.NOT_OPEN
    # Only the "is it running" probe may have been sent: anything else launches Music.
    assert all("is running" in s for s in music.scripts)


def test_media_commands_send_the_right_verbs(music):
    assert media.pause_music() == (True, "Paused.")
    assert media.resume_music() == (True, "Resuming.")
    assert media.next_track() == (True, "Next track.")
    assert media.previous_track() == (True, "Previous track.")
    sent = " ".join(music.scripts)
    for verb in ("to pause", "to play", "to next track", "to previous track"):
        assert verb in sent


def test_media_failure_is_reported(music):
    music.fail = True
    ok, message = media.pause_music()
    assert ok is False  # the "is running" probe itself fails -> treated as not open


def test_now_playing_variants(music):
    assert media.now_playing() == (True, "Playing Starboy by The Weeknd.")
    music.state_line = "paused|Starboy|The Weeknd"
    assert media.now_playing() == (True, "Paused on Starboy by The Weeknd.")
    music.state_line = "stopped"
    assert media.now_playing() == (True, "Nothing is playing.")


# ── calendar ────────────────────────────────────────────────────────────────

RAW = (
    "2026-10-5 9:00|false|Standup\n"
    "2026-10-5 14:30|false|Dentist\n"
    "2026-10-5 0:00|true|Public holiday\n"
    "garbage line\n"
    "2026-10-6 9:00|false|Design review | with Sam\n"
)
NOW = datetime(2026, 10, 5, 8, 0)


def test_parse_events_sorts_all_day_first_and_skips_junk():
    events = cal.parse_events(RAW)
    assert [e.title for e in events] == ["Public holiday", "Standup", "Dentist", "Design review | with Sam"]
    assert events[0].all_day is True


def _calendar_out(monkeypatch, out, returncode=0):
    monkeypatch.setattr(cal, "run_applescript", lambda script, timeout=30: _proc(out, returncode))


def test_today_message_reads_times_naturally(monkeypatch):
    _calendar_out(monkeypatch, "2026-10-5 9:00|false|Standup\n2026-10-5 14:30|false|Dentist\n"
                               "2026-10-5 0:00|true|Public holiday\n")
    ok, message = cal.today_message(NOW)
    assert ok
    assert message == "You have 3 events today: all day Public holiday, 9 AM Standup, 2:30 PM Dentist."


def test_today_message_empty_single_and_overflow(monkeypatch):
    _calendar_out(monkeypatch, "")
    assert cal.today_message(NOW) == (True, "Your calendar is clear today.")
    _calendar_out(monkeypatch, "2026-10-5 9:00|false|Standup\n")
    assert cal.today_message(NOW)[1] == "You have 1 event today: 9 AM Standup."
    many = "".join(f"2026-10-5 {h}:00|false|Event {h}\n" for h in range(8, 16))
    message = cal.today_message(NOW)[1] if _calendar_out(monkeypatch, many) is None else ""
    assert message.startswith("You have 8 events today:") and message.endswith(", and 2 more.")


def test_calendar_permission_failure_gives_help(monkeypatch):
    _calendar_out(monkeypatch, "", returncode=1)
    assert cal.today_message(NOW) == (False, cal.PERMISSION_HELP)
    assert cal.next_message(NOW) == (False, cal.PERMISSION_HELP)

    def boom(script, timeout=30):
        raise subprocess.TimeoutExpired("osascript", 30)

    monkeypatch.setattr(cal, "run_applescript", boom)
    assert cal.today_message(NOW) == (False, cal.PERMISSION_HELP)


def test_next_message_skips_past_and_all_day_events(monkeypatch):
    _calendar_out(monkeypatch, "2026-10-5 7:00|false|Already happened\n2026-10-5 0:00|true|Holiday\n"
                               "2026-10-6 9:00|false|Design review\n2026-10-5 15:00|false|Dentist\n")
    assert cal.next_message(NOW) == (True, "Your next event is Dentist, today at 3 PM.")
    _calendar_out(monkeypatch, "2026-10-6 9:00|false|Design review\n")
    assert cal.next_message(NOW)[1] == "Your next event is Design review, tomorrow at 9 AM."
    _calendar_out(monkeypatch, "2026-10-5 7:00|false|Already happened\n")
    assert cal.next_message(NOW) == (True, "Nothing coming up in the next week.")


# ── mail ────────────────────────────────────────────────────────────────────

def _mail_out(monkeypatch, out, returncode=0):
    monkeypatch.setattr(mail, "run_applescript", lambda script, timeout=30: _proc(out, returncode))


def test_mail_summary_variants(monkeypatch):
    _mail_out(monkeypatch, "0\n")
    assert mail.unread_message() == (True, "You have no unread email.")
    _mail_out(monkeypatch, "1\nSam Lee|Lunch tomorrow?\n")
    assert mail.unread_message() == (True, "You have 1 unread email. The latest: Sam Lee about Lunch tomorrow?.")
    _mail_out(monkeypatch, "12\nSam|Lunch\nAda|Invoice\nBob|Hi\n")
    ok, message = mail.unread_message()
    assert ok and message.startswith("You have 12 unread emails. The latest: Sam about Lunch; Ada about Invoice")
    _mail_out(monkeypatch, "5\n")
    assert mail.unread_message() == (True, "You have 5 unread emails.")


def test_mail_failure_gives_help(monkeypatch):
    _mail_out(monkeypatch, "", returncode=1)
    assert mail.unread_message() == (False, mail.PERMISSION_HELP)
    _mail_out(monkeypatch, "not a number\n")
    assert mail.unread_message() == (False, mail.PERMISSION_HELP)


# ── shortcuts ───────────────────────────────────────────────────────────────

NAMES = ["playlist", "Good Night", "Morning Routine"]


@pytest.mark.parametrize("spoken,expected", [
    ("run the shortcut playlist", "playlist"),
    ("Run the shortcut Good Night.", "Good Night"),
    ("good night", "Good Night"),
    ("start my morning routine shortcut", "Morning Routine"),
    ("run shortcut playlis", "playlist"),          # a near miss from speech recognition
])
def test_match_shortcut_finds_the_installed_name(spoken, expected):
    assert shortcuts.match_shortcut(spoken, NAMES) == expected


@pytest.mark.parametrize("spoken", ["run the shortcut banana", "", "run the shortcut"])
def test_match_shortcut_returns_none_when_nothing_fits(spoken):
    assert shortcuts.match_shortcut(spoken, NAMES) is None


def test_match_shortcut_with_no_installed_shortcuts():
    assert shortcuts.match_shortcut("run the shortcut playlist", []) is None


def test_list_shortcuts_parses_and_survives_errors(monkeypatch):
    out = subprocess.CompletedProcess(args=[], returncode=0, stdout="playlist\n\nGood Night\n", stderr="")
    monkeypatch.setattr(shortcuts.subprocess, "run", lambda *a, **k: out)
    assert shortcuts.list_shortcuts() == ["playlist", "Good Night"]
    monkeypatch.setattr(shortcuts.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess([], 1, "", "err"))
    assert shortcuts.list_shortcuts() == []

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("shortcuts", 1)

    monkeypatch.setattr(shortcuts.subprocess, "run", boom)
    assert shortcuts.list_shortcuts() == []


def _exec_shortcut(monkeypatch, names, spoken):
    ran = []
    monkeypatch.setattr(executor, "list_shortcuts", lambda: names)
    monkeypatch.setattr(executor, "run_shortcut", lambda name: ran.append(name) or True)
    monkeypatch.setattr(executor, "set_last_shortcut", lambda *a, **k: None)
    monkeypatch.setattr(executor, "set_last_action", lambda *a, **k: None)
    monkeypatch.setattr(executor, "_record", lambda *a, **k: None)
    return executor.execute({"tool": "shortcut", "name": spoken}, spoken), ran


def test_executor_runs_the_resolved_shortcut_not_the_sentence(monkeypatch):
    result, ran = _exec_shortcut(monkeypatch, NAMES, "run the shortcut playlist")
    assert result["ok"] and ran == ["playlist"]


def test_executor_says_what_exists_when_nothing_matches(monkeypatch):
    result, ran = _exec_shortcut(monkeypatch, NAMES, "run the shortcut banana")
    assert result["ok"] is False and result["code"] == "shortcut_not_found"
    assert "playlist" in result["message"] and ran == []


def test_executor_falls_back_to_the_given_name_when_the_list_is_unavailable(monkeypatch):
    result, ran = _exec_shortcut(monkeypatch, [], "Good Morning")
    assert result["ok"] and ran == ["Good Morning"]


# ── routing ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase,action", [
    ("pause", "pause"), ("Pause.", "pause"), ("pause the music", "pause"),
    ("resume", "resume"), ("keep playing", "resume"),
    ("next song", "next_track"), ("skip this song", "next_track"), ("play the next track", "next_track"),
    ("previous song", "previous_track"), ("go back a song", "previous_track"),
    ("what's playing", "now_playing"), ("what song is this", "now_playing"),
    ("what shortcuts do I have", "shortcuts_list"), ("list my shortcuts", "shortcuts_list"),
    ("what's on my calendar", "calendar_today"), ("what do I have today", "calendar_today"),
    ("check my schedule", "calendar_today"), ("do I have any meetings", "calendar_today"),
    ("when is my next meeting", "calendar_next"), ("what's my next appointment", "calendar_next"),
    ("check my email", "mail_unread"), ("do I have any new emails", "mail_unread"),
    ("what's my schedule", "calendar_today"), ("what's on my schedule today", "calendar_today"),
    ("any new mail", "mail_unread"), ("any new email", "mail_unread"), ("is there a new email", "mail_unread"), ("do I have any new unread emails", "mail_unread"),
    ("any unread mail", "mail_unread"), ("what's in my inbox", "mail_unread"),
])
def test_phrases_route_to_the_local_action(phrase, action):
    assert router.route(phrase) == {"tool": "system", "action": action}


@pytest.mark.parametrize("phrase", [
    "add lunch to my calendar", "schedule a meeting with sam", "cancel my next meeting",
    "send an email to sam", "reply to my email", "delete my unread mail",
    "the pause in that song is weird", "i need a pause from work", "skip to the end of the film",
    "run the shortcut playlist",
    "schedule a meeting for tomorrow", "schedule me a call with ada", "create a new event for friday",
    "write a new email to sam",
])
def test_phrases_that_change_things_or_are_not_commands_are_left_alone(phrase):
    assert router._route_apps(phrase.lower()) is None


def test_running_a_shortcut_is_not_mistaken_for_listing_them():
    assert router.route("run the shortcut playlist")["tool"] == "shortcut"


# ── Claude may not read private content ─────────────────────────────────────

@pytest.mark.parametrize("action", ["calendar_today", "calendar_next", "mail_unread",
                                    "clipboard_read", "screenshot"])
def test_claude_cannot_read_private_content(action, monkeypatch):
    ran = []
    monkeypatch.setattr(mac_actions, "execute", lambda d, u: ran.append(d) or {"ok": True, "message": "x"})
    result = mac_actions.run_model_action({"tool": "system", "action": action})
    assert result["ok"] is False and ran == []


@pytest.mark.parametrize("action", ["pause", "resume", "next_track", "previous_track", "now_playing", "shortcuts_list"])
def test_claude_can_use_harmless_actions(action, monkeypatch):
    monkeypatch.setattr(mac_actions, "execute", lambda d, u: {"ok": True, "message": "done"})
    assert mac_actions.run_model_action({"tool": "system", "action": action})["ok"] is True


def test_registry_has_the_new_actions():
    for name in ("pause", "resume", "next_track", "previous_track", "now_playing",
                 "calendar_today", "calendar_next", "mail_unread", "shortcuts_list"):
        assert name in SYSTEM_ACTIONS
