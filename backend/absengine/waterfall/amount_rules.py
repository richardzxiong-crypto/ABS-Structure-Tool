"""Amount-due rules - one place computing "how much does this step owe"."""

from __future__ import annotations

from ..models.accounts import FeeSpec
from ..models.structure import AllocationNode, tree_class_ids
from ..models.waterfall import PayPrincipalStep, TargetOCSpec
from .state import EngineState


def fee_due(state: EngineState, fee: FeeSpec) -> float:
    return state.pool_basis_beg(fee.basis) * fee.rate / 12.0 + fee.fixed


def interest_capacity(state: EngineState):
    return lambda cid: state.bonds[cid].interest_unpaid_p


def shortfall_capacity(state: EngineState):
    return lambda cid: state.bonds[cid].shortfall - state.bonds[cid].shortfall_paid_p


def principal_capacity(state: EngineState):
    return lambda cid: state.bonds[cid].balance


def current_balance_basis(state: EngineState):
    return lambda cid: state.bonds[cid].beg_balance_p


def original_balance_basis(state: EngineState):
    return lambda cid: state.bonds[cid].original_balance


def target_oc_amount(state: EngineState, spec: TargetOCSpec, pool_basis) -> float:
    if spec.kind == "fixed":
        main = spec.value
    elif spec.kind == "pct_current_pool":
        main = spec.value * state.pool_basis_end(pool_basis)
    elif spec.kind == "pct_original_pool":
        main = spec.value * state.original_pool_basis(pool_basis)
    else:
        raise ValueError(spec.kind)

    if spec.floor_kind == "none":
        return main
    if spec.floor_kind == "fixed":
        floor = spec.floor_value
    elif spec.floor_kind == "pct_original_pool":
        floor = spec.floor_value * state.original_pool_basis(pool_basis)
    else:
        raise ValueError(spec.floor_kind)
    return max(main, floor)


def reserve_target(state: EngineState, name: str) -> float:
    acct = state.reserves_by_name[name]
    if acct.target_kind == "fixed":
        return acct.target_value
    if acct.target_kind == "pct_current_pool":
        from ..models.common import PoolBalanceBasis

        return acct.target_value * state.pool_basis_end(PoolBalanceBasis.TRUST)
    if acct.target_kind == "pct_original_pool":
        return acct.target_value * state.collat.original_balance
    raise ValueError(acct.target_kind)


def principal_due(state: EngineState, step: PayPrincipalStep, resolved: list[AllocationNode]) -> float:
    """Total principal this step is obligated to distribute."""
    if step.amount_rule == "collections":
        return state.prin_collections_p
    if step.amount_rule == "regular_pda":
        total_bonds = sum(b.balance for b in state.bonds.values())
        pool_end = state.pool_basis_end(step.pool_basis)
        oc = target_oc_amount(state, step.target_oc, step.pool_basis)
        return max(0.0, total_bonds - (pool_end - oc))
    if step.amount_rule == "priority_pda":
        # cumulative tiers (First/Second/Third Allocations) come from
        # consecutive steps with growing target sets: balances update between
        # steps, so "minus prior allocations" is automatic
        target_bal = sum(
            state.bonds[cid].balance for node in resolved for cid in tree_class_ids(node)
        )
        pool_end = state.pool_basis_end(step.pool_basis)
        return max(0.0, target_bal - pool_end)
    if step.amount_rule == "turbo":
        return state.funds.balance(step.source)
    raise ValueError(step.amount_rule)
