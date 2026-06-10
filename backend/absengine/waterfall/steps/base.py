from __future__ import annotations

from typing import Protocol

from ...registry import Registry
from ..state import EngineState

STEP_REGISTRY = Registry("waterfall_steps")


class StepHandler(Protocol):
    def execute(self, cfg, state: EngineState) -> None: ...
