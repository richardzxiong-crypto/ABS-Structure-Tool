from ...models.waterfall import PayFeesStep
from .. import amount_rules
from ..state import EngineState
from .base import STEP_REGISTRY


@STEP_REGISTRY.register("pay_fees", config_model=PayFeesStep)
class PayFeesHandler:
    def execute(self, cfg: PayFeesStep, state: EngineState) -> None:
        fees = state.fees_by_name
        for name in cfg.fees:
            already = state.fee_paid_by_name_p.get(name, 0.0)
            due = max(0.0, amount_rules.fee_due(state, fees[name]) - already)
            paid = state.funds.draw(cfg.source, due)
            state.fees_paid_p += paid
            state.fee_paid_by_name_p[name] = already + paid
            state.record(cfg, target=name, due=due, paid=paid)
