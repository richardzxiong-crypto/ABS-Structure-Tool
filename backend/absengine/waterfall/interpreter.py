"""The period loop - runs the waterfall period-by-period in plain Python.

Path-dependent state (shortfalls, reserves, triggers) means this must NOT be
vectorized; readability of this loop is the product.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..collateral.result import CollateralCashflows
from ..models.deal import Deal, tree_seniority_order
from ..models.scenario import Scenario
from ..models.structure import FixedCoupon
from .state import AvailableFunds, BondState, EngineState, FlowRecord
from .steps import STEP_REGISTRY


@dataclass
class WaterfallOutput:
    bonds: pd.DataFrame  # one row per (period, class)
    flows: pd.DataFrame  # the FlowRecord audit log
    residual: np.ndarray
    fees_paid: np.ndarray
    retained: np.ndarray  # cash left in buckets after all steps (per period)
    seeded: np.ndarray


def run_waterfall(deal: Deal, scenario: Scenario, collat: CollateralCashflows) -> WaterfallOutput:
    num_periods = deal.num_periods
    bonds: dict[str, BondState] = {}
    for c in deal.structure.classes:
        assert isinstance(c.coupon, FixedCoupon)  # Phase 1; guarded by check_phase1_support
        bonds[c.id] = BondState(
            id=c.id,
            balance=c.balance,
            original_balance=c.balance,
            monthly_rate=c.coupon.rate / 12.0,
        )

    state = EngineState(deal=deal, scenario=scenario, collat=collat, bonds=bonds)
    int_coll = collat.interest_collections()
    prin_coll = collat.principal_collections(scenario.recoveries_to)

    bond_rows: list[dict] = []
    residual = np.zeros(num_periods)
    fees_paid = np.zeros(num_periods)
    retained = np.zeros(num_periods)
    seeded = np.zeros(num_periods)
    seniority = tree_seniority_order(deal)

    for t in range(1, num_periods + 1):
        state.period = t
        state.funds = AvailableFunds()
        state.residual_paid_p = 0.0
        state.fees_paid_p = 0.0
        state.prin_collections_p = float(prin_coll[t - 1])

        # accrue bond interest (Phase 1: fixed coupon, 30/360 monthly)
        for b in bonds.values():
            b.beg_balance_p = b.balance
            b.interest_accrued_p = b.balance * b.monthly_rate
            b.interest_unpaid_p = b.interest_accrued_p
            b.interest_paid_p = 0.0
            b.shortfall_paid_p = 0.0
            b.prin_paid_p = 0.0

        # seed funds buckets
        if deal.waterfall.mode == "combined":
            state.funds.seed("total_collections", float(int_coll[t - 1]) + float(prin_coll[t - 1]))
        else:
            state.funds.seed("interest_collections", float(int_coll[t - 1]))
            state.funds.seed("principal_collections", float(prin_coll[t - 1]))
        seeded[t - 1] = sum(state.funds.seeded.values())

        # execute waterfalls in order (Phase 2: trigger conditions skip steps)
        for wf in deal.waterfall.waterfalls:
            state.current_waterfall = wf.name
            for step in wf.steps:
                STEP_REGISTRY.handler_for(step).execute(step, state)

        # roll unpaid current interest into the shortfall ledger
        for b in bonds.values():
            b.shortfall = b.shortfall - b.shortfall_paid_p + b.interest_unpaid_p

        # final period: remaining bond balances are uncollateralized ->
        # writedowns in reverse seniority (what breakeven detects)
        if t == num_periods:
            for cid in reversed(seniority):
                b = bonds[cid]
                if b.balance > 1e-9:
                    b.writedown = b.balance
                    b.balance = 0.0

        residual[t - 1] = state.residual_paid_p
        fees_paid[t - 1] = state.fees_paid_p
        retained[t - 1] = state.funds.total_remaining()

        for cid in seniority:
            b = bonds[cid]
            bond_rows.append(
                {
                    "period": t,
                    "class_id": cid,
                    "beg_balance": b.beg_balance_p,
                    "interest_accrued": b.interest_accrued_p,
                    "interest_paid": b.interest_paid_p,
                    "shortfall_paid": b.shortfall_paid_p,
                    "shortfall_end": b.shortfall,
                    "prin_paid": b.prin_paid_p,
                    "end_balance": b.balance,
                    "writedown": b.writedown if t == num_periods else 0.0,
                }
            )

    flows_df = pd.DataFrame(
        [vars(f) for f in state.flows],
        columns=[f for f in FlowRecord.__dataclass_fields__],
    )
    return WaterfallOutput(
        bonds=pd.DataFrame(bond_rows),
        flows=flows_df,
        residual=residual,
        fees_paid=fees_paid,
        retained=retained,
        seeded=seeded,
    )
