from ...models.structure import tree_class_ids
from ...models.waterfall import PayPrincipalStep
from .. import amount_rules
from ..allocation import allocate_across, resolve_targets
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
        due = amount_rules.principal_due(state, cfg, resolved)
        target_cap = sum(capacity(cid) for node in resolved for cid in tree_class_ids(node))
        cash = state.funds.draw(cfg.source, min(due, target_cap))
        dist = allocate_across(cash, resolved, capacity, basis)
        for cid, amt in dist.items():
            bond = state.bonds[cid]
            bond.balance = max(0.0, bond.balance - amt)
            bond.prin_paid_p += amt
        for node in resolved:
            for cid in tree_class_ids(node):
                state.record(cfg, target=cid, due=due, paid=dist.get(cid, 0.0))


def _any_original_basis(resolved) -> bool:
    from ...models.structure import GroupNode

    return any(isinstance(n, GroupNode) and n.pro_rata_basis == "original" for n in resolved)
