from ...models.deal import tree_seniority_order
from ...models.waterfall import RetireBondsStep
from ..state import EngineState
from .base import STEP_REGISTRY

# absolute-dollar slack for the "can we retire everything" test (float dust)
_RETIRE_EPS = 1e-6


@STEP_REGISTRY.register("retire_bonds", config_model=RetireBondsStep)
class RetireBondsHandler:
    """Optional reserve-to-retire feature: if the source bucket plus the
    reserve covers the total remaining bond balance (checked after the
    interest/fee clauses have drawn), retire every class - source cash first,
    then the reserve. No-op otherwise."""

    def execute(self, cfg: RetireBondsStep, state: EngineState) -> None:
        total = sum(b.balance for b in state.bonds.values())
        if total <= _RETIRE_EPS:
            return
        bucket = f"reserve:{cfg.reserve}"
        avail = state.funds.balance(cfg.source) + state.funds.balance(bucket)
        if avail + _RETIRE_EPS < total:
            return
        cash = state.funds.draw(cfg.source, total)
        cash += state.funds.draw(bucket, total - cash)
        for cid in tree_seniority_order(state.deal):
            b = state.bonds[cid]
            amt = min(b.balance, cash)
            if amt > 0.0:
                b.balance -= amt
                b.prin_paid_p += amt
                cash -= amt
            state.record(cfg, target=cid, due=b.beg_balance_p, paid=amt)
        if cfg.release_reserve_remainder:
            leftover = state.funds.draw(bucket, state.funds.balance(bucket))
            if leftover > 0.0:
                state.funds.deposit(cfg.source, leftover)
                state.record(cfg, target=cfg.source, due=leftover, paid=leftover)
