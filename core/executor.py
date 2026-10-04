from typing import Any

from core.system_actions import SYSTEM_ACTIONS
from memory.context import (
    set_last_action,
    set_last_app,
    set_last_browser_target,
    set_last_shortcut,
    set_last_song,
)
from tools.apps import is_app_running, open_app
from tools.browser import open_target
from tools.music import play_music_any
from tools.shortcuts import run_shortcut
from utils.logger import save_action


def _result(
    ok: bool,
    message: str,
    code: str,
    action_type: str,
    retryable: bool = False,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "message": (message or "").strip(),
        "code": code,
        "action_type": action_type,
        "retryable": bool(retryable),
        "data": data or {},
    }


def _record(user_input: str, action_type: str, ok: bool, details: str) -> None:
    save_action(
        action_type=action_type,
        user_input=user_input,
        result="success" if ok else "failure",
        details=(details or "")[:600],
    )


def execute(decision: dict, user_input: str) -> dict[str, Any]:
    tool = (decision.get("tool") or "").strip() or None

    if tool == "app":
        app_name = (decision.get("name") or "").strip()
        if not app_name:
            return _result(False, "I couldn't figure out which app to open.", "app_missing_name", "app")

        launch_ok = open_app(app_name)
        verified = is_app_running(app_name) if launch_ok else False
        ok = launch_ok and verified

        if ok:
            set_last_app(app_name)
            set_last_action("app", app_name)

        _record(user_input, "app", ok, f"App: {app_name}; launch_ok={launch_ok}; verified={verified}")

        if ok:
            return _result(True, f"Opening {app_name}.", "app_opened", "app", data={"name": app_name})
        return _result(False, "I couldn't open that app.", "app_open_failed", "app", retryable=True)

    if tool == "music":
        query = (decision.get("query") or "").strip()
        if not query:
            return _result(False, "What should I play?", "music_missing_query", "music")

        ok = play_music_any(query)

        if ok:
            set_last_song(query)
            set_last_action("music", query)

        _record(user_input, "music", ok, f"Query: {query}")

        if ok:
            return _result(True, f"Playing {query}.", "music_playing", "music", data={"query": query})
        return _result(False, "I couldn't play that.", "music_play_failed", "music", retryable=True)

    if tool == "shortcut":
        name = (decision.get("name") or "").strip()
        if not name:
            return _result(False, "I couldn't figure out which shortcut to run.", "shortcut_missing_name", "shortcut")

        ok = run_shortcut(name)

        if ok:
            set_last_shortcut(name)
            set_last_action("shortcut", name)

        _record(user_input, "shortcut", ok, f"Shortcut: {name}")

        if ok:
            return _result(True, "Done.", "shortcut_ran", "shortcut", data={"name": name})
        return _result(False, "Shortcut failed.", "shortcut_failed", "shortcut", retryable=True)

    if tool == "browser":
        target = (decision.get("target") or "").strip()
        if not target:
            return _result(False, "I couldn't figure out what website to open.", "browser_missing_target", "browser")

        query = (decision.get("query") or "").strip()
        ok = open_target(target, query=query or None)

        if ok:
            set_last_browser_target(target)
            set_last_action("browser", target)

        detail_suffix = f"; query={query}" if query else ""
        _record(user_input, "browser", ok, f"Target: {target}{detail_suffix}")

        if ok:
            if query:
                return _result(
                    True,
                    f"Opening {target} and searching for {query}.",
                    "browser_open_and_search_ok",
                    "browser",
                    data={"target": target, "query": query},
                )
            return _result(True, f"Opening {target}.", "browser_opened", "browser", data={"target": target})
        if query:
            return _result(
                False,
                "I couldn't run that site search. I only search on trusted websites.",
                "browser_site_search_blocked_or_failed",
                "browser",
                retryable=False,
            )
        return _result(False, "I couldn't open that website.", "browser_open_failed", "browser", retryable=True)

    if tool == "open":
        target = (decision.get("target") or "").strip()
        if not target:
            return _result(False, "I couldn't figure out what to open.", "open_missing_target", "open")

        query = (decision.get("query") or "").strip()
        ok = open_target(target, query=query or None)

        if ok:
            set_last_browser_target(target)
            set_last_action("open", target)

        detail_suffix = f"; query={query}" if query else ""
        _record(user_input, "open", ok, f"Target: {target}{detail_suffix}")

        if ok:
            if query:
                return _result(
                    True,
                    f"Opening {target} and searching for {query}.",
                    "open_target_with_query_ok",
                    "open",
                    data={"target": target, "query": query},
                )
            return _result(True, f"Opening {target}.", "open_target_opened", "open", data={"target": target})
        return _result(False, f"I couldn't open {target}.", "open_target_failed", "open", retryable=True)

    if tool == "system":
        action = (decision.get("action") or "").strip().lower()
        spec = SYSTEM_ACTIONS.get(action)

        if not spec:
            return _result(False, "I couldn't figure out which system action to perform.", "system_unknown_action", "system")

        value = (decision.get("value") or "").strip() or None
        ok, message, data = spec.handler(value)
        if ok:
            set_last_action("system", action)
        _record(user_input, "system", ok, f"Action: {action}; data={data}")

        if ok:
            return _result(True, message, f"system_{action}_ok", "system", data=data)
        return _result(False, message, f"system_{action}_failed", "system")

    response = (decision.get("response") or "").strip()
    unhandled_reason = decision.get("_unhandled_reason")

    if response and not unhandled_reason:
        save_action(
            action_type="brain",
            user_input=user_input,
            result="success",
            details=f"Reply: {response}",
        )
        return _result(True, response, "brain_response", "brain")

    if response and unhandled_reason:
        save_action(
            action_type="unhandled",
            user_input=user_input,
            result="failure",
            details=f"Reason: {unhandled_reason}; Response: {response}",
        )
        return _result(False, response, f"unhandled_{unhandled_reason}", "unknown")

    save_action(
        action_type="unhandled",
        user_input=user_input,
        result="failure",
        details=f"Decision: {decision}",
    )
    return _result(False, "I didn't understand that.", "unknown_decision", "unknown")