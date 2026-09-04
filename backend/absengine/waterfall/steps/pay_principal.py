from ...models.structure import GroupNode, tree_class_ids
from ...models.waterfall import PayPrincipalStep
from .. import amount_rules
from ..allocation import allocate_by_node, node_capacity, resolve_targets
from ..state import EngineState
from .base import STEP_REGISTRY


@STEP_REGISTRY.register("pay_principal", config_model=PayPrincipalStep)
class PayPrincipalHandler:
    def execute(self, cfg: PayPrincipalStep, state: EngineState) -> None:
        resolved = resolve_targets(cfg.targets, state.deal.structure.allocation_tree)
        capacity = amount_rules.principal_capacity(state)
        basis = (
            amount_rules.original_balance_basis(state)
            if _any_original_basis(resolved)
            else amount_rules.current_balance_basis(state)
        )
        group_cap = amount_rules.target_balance_cap(state)
        due = amount_rules.principal_due(state, cfg, resolved)
        target_cap = sum(node_capacity(node, capacity, group_cap) for node in resolved)
        cash = state.funds.draw(cfg.source, min(due, target_cap))
        per_node = allocate_by_node(cash, resolved, capacity, basis, group_cap)
        distributed = 0.0
        for node, dist in zip(resolved, per_node):
            for cid, amt in dist.items():
                bond = state.bonds[cid]
                bond.balance = max(0.0, bond.balance - amt)
                bond.prin_paid_p += amt
                distributed += amt
            for cid in tree_class_ids(node):
                state.record(cfg, target=cid, due=due, paid=dist.get(cid, 0.0))
        # anything the tree could not place (rounding at caps) stays in the bucket
        undistributed = cash - distributed
        if undistributed > 1e-12:
            state.funds.deposit(cfg.source, undistributed)


def _any_original_basis(resolved) -> bool:
    return any(isinstance(n, GroupNode) and n.pro_rata_basis == "original" for n in resolved)
