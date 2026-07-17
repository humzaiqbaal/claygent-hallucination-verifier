"""
Per-model capability differences for thinking control and the effort parameter.

Copied from ai-personalization-engine/app/model_capabilities.py (sibling
portfolio project) rather than shared as a library: each portfolio project
here is a standalone, independently deployable tree, not a monorepo package.
Keep this in sync manually if the underlying model capabilities change.
"""

from __future__ import annotations

THINKING_UNSUPPORTED_MODELS = {"claude-haiku-4-5"}
THINKING_ALWAYS_ON_MODELS = {"claude-fable-5"}
EFFORT_UNSUPPORTED_MODELS = {"claude-haiku-4-5"}

VALID_EFFORT_LEVELS = ["low", "medium", "high", "xhigh", "max"]


def build_thinking_kwarg(model: str, enable_thinking: bool) -> dict:
    """Returns the {"thinking": ...} kwarg to pass to messages.create(), or an
    empty dict when the parameter should be omitted entirely for this model.
    """
    if model in THINKING_ALWAYS_ON_MODELS:
        return {}
    if model in THINKING_UNSUPPORTED_MODELS:
        return {"thinking": {"type": "disabled"}}
    if enable_thinking:
        return {"thinking": {"type": "adaptive"}}
    return {"thinking": {"type": "disabled"}}


def resolve_effort(model: str, enable_thinking: bool, effort: str | None) -> str | None:
    """Returns the effort level to actually send, or None if effort shouldn't
    be sent at all for this model/preference combination.
    """
    if not effort or model in EFFORT_UNSUPPORTED_MODELS:
        return None
    thinking_is_active = enable_thinking or model in THINKING_ALWAYS_ON_MODELS
    if not thinking_is_active:
        return None
    return effort
