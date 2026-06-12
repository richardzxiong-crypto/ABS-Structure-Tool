"""The period loop - runs the waterfall period-by-period in plain Python.

Path-dependent state (shortfalls, reserves, triggers) means this must NOT be
vectorized; readability of this loop is the product.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..collateral.result import CollateralCashflows
from ..dates.daycount import year_frac
from ..models.common import DayCount, PoolBalanceBasis
from ..models.deal import Deal, tree_seniority_order
from ..models.scenario import Scenario
from ..models.structure import FixedCoupon, FloatingCoupon
from ..scenarios.expand import expand
from .state import AvailableFunds, BondState, EngineState, FlowRecord
from .steps import STEP_REGISTRY

_EPS = 1e-9


@dataclass
class WaterfallOutput:
    bonds: pd.DataFrame  # one row per (period, class)
    flows: pd.DataFrame  # the FlowRecord audit log
    residual: np.ndarray
    fees_paid: np.ndarray
    retained: np.ndarray  # cash left in buckets after all steps (per period)
    seeded: np.ndarray
    accounts: pd.DataFrame  # reserve balances, one row per (period, account)
    ysoa: np.ndarray  # realized (strike-selected) YSOA per period
    adjusted_pool: np.ndarray  # realized adjusted pool balance per period


def _accrual_paths(deal: Deal, scenario: Scenario) -> dict[str, np.ndarray]:
    """Per-class accrual rate path: interest_t = balance * path[t-1].

    With DealDates: rate * year_frac(payment_date(t-1), payment_date(t)) per
    the class day count (period 1 accrues from the closing date - typically a
    short period). Without dates: flat rate/12.
    """
    n = deal.num_periods
    if deal.dates is not None:
        pay = [deal.dates.payment_date(t) for t in range(n + 1)]
        pay_adj = [deal.dates.adjusted_payment_date(t) for t in range(n + 1)]
    paths: dict[str, np.ndarray] = {}
    for c in deal.structure.classes:
        if isinstance(c.coupon, FixedCoupon):
            annual = np.full(n, c.coupon.rate)
        elif isinstance(c.coupon, FloatingCoupon):
            curve = scenario.index_curves.get(c.coupon.index)
            if curve is None:
                raise ValueError(
                    f"class {c.id}: floating index {c.coupon.index!r} has no curve in "
                    f"scenario {scenario.name!r} (index_curves)"
                )
            annual = expand(curve, n) + c.coupon.margin
            if c.coupon.cap is not None:
                annual = np.minimum(annual, c.coupon.cap)
            if c.coupon.floor is not None:
                annual = np.maximum(annual, c.coupon.floor)
        else:
            raise TypeError(f"unknown CouponSpec {type(c.coupon)}")
        if deal.dates is not None:
            # ACT classes accrue between business-day-adjusted payment dates;
            # 30/360 stays on the unadjusted calendar (market convention)
            cal = pay if c.day_count == DayCount.THIRTY_360 else pay_adj
            yf = np.array([year_frac(cal[t - 1], cal[t], c.day_count) for t in range(1, n + 1)])
        else:
            yf = np.full(n, 1.0 / 12.0)
        paths[c.id] = annual * yf
    return paths


def run_waterfall(deal: Deal, scenario: Scenario, collat: CollateralCashflows) -> WaterfallOutput:
    num_periods = deal.num_periods
    bonds: dict[str, BondState] = {}
    for c in deal.structure.classes:
        bonds[c.id] = BondState(id=c.id, balance=c.balance, original_balance=c.balance)
    accrual = _accrual_paths(deal, scenario)

    state = EngineState(deal=deal, scenario=scenario, collat=collat, bonds=bonds)
    state.accounts = {r.name: r.initial_balance for r in deal.reserve_accounts}
    int_coll = collat.interest_collections()
    prin_coll = collat.principal_collections(scenario.recoveries_to)

    bond_rows: list[dict] = []
    account_rows: list[dict] = []
    residual = np.zeros(num_periods)
    fees_paid = np.zeros(num_periods)
    retained = np.zeros(num_periods)
    seeded = np.zeros(num_periods)
    ysoa_used = np.zeros(num_periods)
    adjusted_used = np.zeros(num_periods)
    seniority = tree_seniority_order(deal)
    ysoc = deal.ysoc

    for t in range(1, num_periods + 1):
        state.period = t
        state.funds = AvailableFunds()
        state.residual_paid_p = 0.0
        state.fees_paid_p = 0.0
        state.fee_paid_by_name_p = {}
        state.prin_collections_p = float(prin_coll[t - 1])

        # YSOC stepdown latches once the trigger class starts the period at 0
        if (
            ysoc is not None
            and ysoc.stepdown_when_class_zero is not None
            and not state.ysoc_stepdown_active
            and bonds[ysoc.stepdown_when_class_zero].balance <= _EPS
        ):
            state.ysoc_stepdown_active = True

        # accrue bond interest
        for b in bonds.values():
            b.beg_balance_p = b.balance
            b.interest_accrued_p = b.balance * float(accrual[b.id][t - 1])
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
        for name, bal in state.accounts.items():
            state.funds.seed(f"reserve:{name}", bal)
        seeded[t - 1] = sum(state.funds.seeded.values())

        # execute waterfalls in order (Phase 2: trigger conditions skip steps)
        for wf in deal.waterfall.waterfalls:
            state.current_waterfall = wf.name
            for step in wf.steps:
                STEP_REGISTRY.handler_for(step).execute(step, state)

        # reserve accounts carry whatever is left in their buckets
        for name in state.accounts:
            state.accounts[name] = state.funds.balance(f"reserve:{name}")
            account_rows.append({"period": t, "account": name, "balance": state.accounts[name]})

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
        ysoa_used[t - 1] = state.ysoa_end() if ysoc is not None else 0.0
        adjusted_used[t - 1] = state.pool_basis_end(PoolBalanceBasis.ADJUSTED)

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
        accounts=pd.DataFrame(account_rows, columns=["period", "account", "balance"]),
        ysoa=ysoa_used,
        adjusted_pool=adjusted_used,
    )
