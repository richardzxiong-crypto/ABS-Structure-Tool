from ...models.structure import tree_class_ids
from ...models.waterfall import PayInterestShortfallStep
from .. import amount_rules
from ..allocation import allocate_across, node_capacity, resolve_targets
from ..state import EngineState
from .base import STEP_REGISTRY


@STEP_REGISTRY.register("pay_interest_shortfall", config_model=PayInterestShortfallStep)
class PayInterestShortfallHandler:
    def execute(self, cfg: PayInterestShortfallStep, state: EngineState) -> None:
        resolved = resolve_targets(cfg.targets, state.deal.structure.allocation_tree)
        capacity = amount_rules.shortfall_capacity(state)
        basis = amount_rules.current_balance_basis(state)
        due_by_class = {
            cid: capacity(cid) for node in resolved for cid in tree_class_ids(node)
        }
        total_due = sum(node_capacity(n, capacity) for n in resolved)
        cash = state.funds.draw(cfg.source, total_due)
        dist = allocate_across(cash, resolved, capacity, basis)
        for cid, amt in dist.items():
            bond = state.bonds[cid]
            bond.shortfall_paid_p += amt
        for cid, due in due_by_class.items():
            state.record(cfg, target=cid, due=due, paid=dist.get(cid, 0.0))
