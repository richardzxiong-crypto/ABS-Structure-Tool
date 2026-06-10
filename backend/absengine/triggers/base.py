"""Trigger registry + state machine enums. Evaluation lands in Phase 2; the
interpreter will own the cure/latch state machine, handlers stay one-line
comparisons."""

from enum import Enum

from ..registry import Registry

TRIGGER_REGISTRY = Registry("triggers")


class TriggerState(str, Enum):
    PASSING = "passing"
    FAILING = "failing"
    CURED = "cured"
    PERMANENTLY_FAILED = "permanently_failed"
