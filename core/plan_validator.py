"""
core/plan_validator.py

Validates LLM-generated multi-step plans before any execution.
Acts as a hard security gate: unknown tools, missing params, or
oversized plans are rejected before a single step runs.
"""

from dataclasses import dataclass

from core.system_actions import SYSTEM_ACTIONS

# Only these tools may appear in agent plans.
# Expanding this list is the ONLY way to grant new capabilities.
ALLOWED_TOOLS: frozenset[str] = frozenset({
    "app",
    "browser",
    "music",
    "system",
    "shortcut",
    "open",
})

# Allowed values for system action param — derived from the single
# registry in core/system_actions.py so this can never drift out of
# sync with what the executor actually implements.
ALLOWED_SYSTEM_ACTIONS: frozenset[str] = frozenset(SYSTEM_ACTIONS.keys())

# Required params per tool (value must be non-empty string)
_REQUIRED: dict[str, list[str]] = {
    "app":      ["name"],
    "browser":  ["target"],
    "music":    ["query"],
    "system":   ["action"],
    "shortcut": ["name"],
    "open":     ["target"],
}

MAX_STEPS = 5


@dataclass
class ValidationResult:
    valid: bool
    error: str | None = None


def validate_plan(plan: object) -> ValidationResult:
    """
    Returns ValidationResult(valid=True) if the plan is safe to execute,
    or ValidationResult(valid=False, error=<reason>) otherwise.
    """
    if not isinstance(plan, dict):
        return ValidationResult(False, "Plan is not a dict")

    goal = plan.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        return ValidationResult(False, "Plan missing 'goal' string")

    steps = plan.get("steps")
    if not isinstance(steps, list):
        return ValidationResult(False, "Plan missing 'steps' list")

    if not steps:
        return ValidationResult(False, "Plan has zero steps")

    if len(steps) > MAX_STEPS:
        return ValidationResult(False, f"Too many steps ({len(steps)} > {MAX_STEPS})")

    for i, step in enumerate(steps):
        err = _validate_step(i, step)
        if err:
            return ValidationResult(False, err)

    return ValidationResult(True)


def _validate_step(index: int, step: object) -> str | None:
    prefix = f"Step {index}"

    if not isinstance(step, dict):
        return f"{prefix} is not a dict"

    tool = step.get("tool")
    if not isinstance(tool, str) or not tool:
        return f"{prefix}: missing 'tool'"

    if tool not in ALLOWED_TOOLS:
        return f"{prefix}: unknown tool '{tool}'"

    for param in _REQUIRED.get(tool, []):
        value = step.get(param)
        if not isinstance(value, str) or not value.strip():
            return f"{prefix}: tool '{tool}' requires non-empty '{param}'"

    # Extra check: system actions must be from the allowlist
    if tool == "system":
        action = step.get("action", "")
        if action not in ALLOWED_SYSTEM_ACTIONS:
            return f"{prefix}: unknown system action '{action}'"

    return None
