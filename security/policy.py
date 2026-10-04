import json
from pathlib import Path

_POLICY_PATH = Path(__file__).with_name("policy.json")

# Tool risk levels — controls whether confirmation is required.
# LOW:    execute automatically (read-only or reversible system actions)
# MEDIUM: confirm once before executing (opens apps, sites, plays music)
# HIGH:   confirm with explicit description (shortcuts — arbitrary macOS actions)
TOOL_RISK: dict[str, str] = {
    "system":   "low",      # volume, battery — safe and reversible
    "browser":  "medium",
    "app":      "medium",
    "music":    "medium",
    "open":     "medium",
    "shortcut": "high",     # arbitrary macOS Shortcut — treat as high risk
}


def get_tool_risk(tool: str) -> str:
    """Returns 'low', 'medium', or 'high'. Unknown tools default to 'high'."""
    return TOOL_RISK.get(tool, "high")

_DEFAULT_POLICY = {
    "require_confirmation_for_actions": True,
    "confirm_tools": ["app", "music", "shortcut", "browser", "open", "system"],
    "trusted_web_targets": ["youtube", "github", "netflix", "google", "chatgpt", "linkedin"],
    "blocked_url_patterns": [
        r"^https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0)(?::\d+)?",
        r"^https?://(?:10\.\d+\.\d+\.\d+)",
        r"^https?://(?:192\.168\.\d+\.\d+)",
        r"^https?://(?:172\.(?:1[6-9]|2\d|3[0-1])\.\d+\.\d+)",
        r"^file://",
    ],
    "strip_tracking_params": [
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "fbclid",
    ],
    "disable_unknown_site_search": True,
}


def requires_confirmation(tool: str | None) -> bool:
    """Single source of truth for whether a tool needs voice confirmation
    before executing, per the merged policy (defaults + policy.json)."""
    policy = get_policy()
    if not policy.get("require_confirmation_for_actions", True):
        return False
    tool = (tool or "").strip()
    if not tool:
        return False
    return tool in set(policy.get("confirm_tools", []))


def get_policy() -> dict:
    try:
        with open(_POLICY_PATH, encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            return dict(_DEFAULT_POLICY)

        merged = dict(_DEFAULT_POLICY)
        merged.update(loaded)
        return merged
    except Exception:
        return dict(_DEFAULT_POLICY)
