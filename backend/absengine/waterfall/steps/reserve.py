from ...models.waterfall import FundReserveStep
from .. import amount_rules
from ..state import EngineState
from .base import STEP_REGISTRY


@STEP_REGISTRY.register("fund_reserve", config_model=FundReserveStep)
class FundReserveHandler:
    """Deposit into the reserve bucket up to its target balance."""

    def execute(self, cfg: FundReserveStep, state: EngineState) -> None:
        bucket = f"reserve:{cfg.account}"
        target = amount_rules.reserve_target(state, cfg.account)
        due = max(0.0, target - state.funds.balance(bucket))
        paid = state.funds.draw(cfg.source, due)
        state.funds.deposit(bucket, paid)
        state.record(cfg, target=cfg.account, due=due, paid=paid)
