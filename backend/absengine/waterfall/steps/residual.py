from ...models.waterfall import ReleaseResidualStep
from ..state import EngineState
from .base import STEP_REGISTRY


@STEP_REGISTRY.register("release_residual", config_model=ReleaseResidualStep)
class ReleaseResidualHandler:
    def execute(self, cfg: ReleaseResidualStep, state: EngineState) -> None:
        due = state.funds.balance(cfg.source)
        paid = state.funds.draw(cfg.source, due)
        state.residual_paid_p += paid
        state.record(cfg, target=cfg.to, due=due, paid=paid)
