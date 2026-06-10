from ...models.waterfall import PayInterestStep
from .. import amount_rules
from ..allocation import allocate_across, node_capacity, resolve_targets
from ..state import EngineState
from .base import STEP_REGISTRY


@STEP_REGISTRY.register("pay_interest", config_model=PayInterestStep)
class PayInterestHandler:
    def execute(self, cfg: PayInterestStep, state: EngineState) -> None:
        resolved = resolve_targets(cfg.targets, state.deal.structure.allocation_tree)
        capacity = amount_rules.interest_capacity(state)
        basis = amount_rules.current_balance_basis(state)
        due_by_class = {
            cid: state.bonds[cid].interest_unpaid_p
            for node in resolved
            for cid in _leaves(node)
        }
        total_due = sum(node_capacity(n, capacity) for n in resolved)
        cash = state.funds.draw(cfg.source, total_due)
        dist = allocate_across(cash, resolved, capacity, basis)
        for cid, amt in dist.items():
            bond = state.bonds[cid]
            bond.interest_unpaid_p -= amt
            bond.interest_paid_p += amt
        for cid, due in due_by_class.items():
            state.record(cfg, target=cid, due=due, paid=dist.get(cid, 0.0))


def _leaves(node):
    from ...models.structure import tree_class_ids

    return tree_class_ids(node)
