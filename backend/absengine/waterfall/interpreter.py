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
from ..models.waterfall import StepCondition
from ..scenarios.expand import expand
from ..triggers import TRIGGER_REGISTRY, TriggerState
from .state import AvailableFunds, BondState, EngineState, FlowRecord
from .steps import STEP_REGISTRY

_EPS = 1e-9

_OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}


def _cmp(measured: float, op: str, threshold: float) -> bool:
    return _OPS[op](measured, threshold)


def _condition_met(cond: StepCondition, states: dict[str, TriggerState]) -> bool:
    st = states[cond.trigger]
    passing = st in (TriggerState.PASSING, TriggerState.CURED)
    return passing if cond.when == "pass" else not passing


@dataclass
class WaterfallOutput:
    bonds: pd.DataFrame  # one row per (period, class)
    flows: pd.DataFrame  # the FlowRecord audit log
    residual: np.ndarray
    fees_paid: np.ndarray
    retained: np.ndarray  # cash left in buckets after all steps (per period)
    seeded: np.ndarray
    accounts: pd.DataFrame  # reserve balances, one row per (period, account)
    triggers: pd.DataFrame  # one row per (period, trigger): measured/threshold/state
    externals: pd.DataFrame  # one row per (period, source): net / seeded receipt
    ysoa: np.ndarray  # realized (strike-selected) YSOA per period
    adjusted_pool: np.ndarray  # realized adjusted pool balance per period


def _year_fracs(deal: Deal, day_count: DayCount) -> np.ndarray:
    """Accrual fraction per period for a day count on the deal calendar.

    With DealDates: year_frac(payment_date(t-1), payment_date(t)) (period 1
    accrues from the closing date - typically short); ACT day counts accrue
    between business-day-adjusted dates, 30/360 on the unadjusted calendar.
    Without dates: flat 1/12.
    """
    n = deal.num_periods
    if deal.dates is None:
        return np.full(n, 1.0 / 12.0)
    if day_count == DayCount.THIRTY_360:
        cal = [deal.dates.payment_date(t) for t in range(n + 1)]
    else:
        cal = [deal.dates.adjusted_payment_date(t) for t in range(n + 1)]
    return np.array([year_frac(cal[t - 1], cal[t], day_count) for t in range(1, n + 1)])


def _index_path(deal: Deal, scenario: Scenario, index: str, who: str) -> np.ndarray:
    curve = scenario.index_curves.get(index)
    if curve is None:
        raise ValueError(
            f"{who}: index {index!r} has no curve in scenario {scenario.name!r} (index_curves)"
        )
    return expand(curve, deal.num_periods)


def _accrual_paths(deal: Deal, scenario: Scenario) -> dict[str, np.ndarray]:
    """Per-class accrual rate path: interest_t = balance * path[t-1]."""
    n = deal.num_periods
    paths: dict[str, np.ndarray] = {}
    for c in deal.structure.classes:
        if isinstance(c.coupon, FixedCoupon):
            annual = np.full(n, c.coupon.rate)
        elif isinstance(c.coupon, FloatingCoupon):
            annual = _index_path(deal, scenario, c.coupon.index, f"class {c.id}") + c.coupon.margin
            if c.coupon.cap is not None:
                annual = np.minimum(annual, c.coupon.cap)
            if c.coupon.floor is not None:
                annual = np.maximum(annual, c.coupon.floor)
        else:
            raise TypeError(f"unknown CouponSpec {type(c.coupon)}")
        paths[c.id] = annual * _year_fracs(deal, c.day_count)
    return paths


def _external_amount_paths(deal: Deal, scenario: Scenario) -> dict[str, np.ndarray]:
    """kind='amount' sources: dollars per period inside the active window
    (scenario.external_amounts overrides the deal-level amount)."""
    n = deal.num_periods
    out: dict[str, np.ndarray] = {}
    for x in deal.external_sources:
        if x.kind != "amount":
            continue
        spec = scenario.external_amounts.get(x.name, x.amount)
        path = np.maximum(expand(spec, n), 0.0)
        out[x.name] = _window(path, x.start_period, x.end_period, n)
    return out


def _window(path: np.ndarray, start: int, end: int | None, n: int) -> np.ndarray:
    mask = np.zeros(n, dtype=bool)
    last = n if end is None else min(end, n)
    if start <= last:
        mask[start - 1:last] = True
    return np.where(mask, path, 0.0)


def _swap_net(deal: Deal, scenario: Scenario, x, t: int, bonds: dict[str, BondState]) -> float:
    """Net swap amount for period t: notional x (index + spread - fixed) x accrual."""
    if t < x.start_period or (x.end_period is not None and t > x.end_period):
        return 0.0
    if x.notional_class is not None:
        notional = bonds[x.notional_class].beg_balance_p
    else:
        sched = x.notional_schedule
        notional = sched[t - 1] if t - 1 < len(sched) else sched[-1]
    idx = float(_index_path(deal, scenario, x.index, f"external source {x.name!r}")[t - 1])
    yf = float(_year_fracs(deal, x.day_count)[t - 1])
    return notional * (idx + x.spread - x.fixed_rate) * yf


def run_waterfall(deal: Deal, scenario: Scenario, collat: CollateralCashflows) -> WaterfallOutput:
    num_periods = deal.num_periods
    bonds: dict[str, BondState] = {}
    for c in deal.structure.classes:
        bonds[c.id] = BondState(id=c.id, balance=c.balance, original_balance=c.balance)
    accrual = _accrual_paths(deal, scenario)

    state = EngineState(deal=deal, scenario=scenario, collat=collat, bonds=bonds)
    state.accounts = {r.name: r.initial_balance for r in deal.reserve_accounts}
    state.trigger_states = {trig.name: TriggerState.PASSING for trig in deal.triggers}
    int_coll = collat.interest_collections()
    prin_coll = collat.principal_collections(scenario.recoveries_to)

    bond_rows: list[dict] = []
    account_rows: list[dict] = []
    trigger_rows: list[dict] = []
    external_rows: list[dict] = []
    ext_amounts = _external_amount_paths(deal, scenario)
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

        # evaluate triggers (determination precedes distribution); the
        # interpreter owns the cure/latch state machine
        for trig in deal.triggers:
            res = TRIGGER_REGISTRY.handler_for(trig).measure(trig, state)
            measured, threshold = res if res is not None else (None, None)
            passes = res is None or _cmp(measured, trig.operator, threshold)
            prev = state.trigger_states[trig.name]
            if prev == TriggerState.PERMANENTLY_FAILED:
                new = prev
            elif passes:
                new = TriggerState.PASSING if prev == TriggerState.PASSING else TriggerState.CURED
            else:
                new = TriggerState.FAILING if trig.curable else TriggerState.PERMANENTLY_FAILED
            state.trigger_states[trig.name] = new
            trigger_rows.append({
                "period": t, "trigger": trig.name, "measured": measured,
                "threshold": threshold, "state": new.value,
            })

        # seed funds buckets
        if deal.waterfall.mode == "combined":
            state.funds.seed("total_collections", float(int_coll[t - 1]) + float(prin_coll[t - 1]))
        else:
            state.funds.seed("interest_collections", float(int_coll[t - 1]))
            state.funds.seed("principal_collections", float(prin_coll[t - 1]))
        for name, bal in state.accounts.items():
            state.funds.seed(f"reserve:{name}", bal)
        # external sources: fixed amounts, or swap net receipts (a negative
        # swap net is owed by the trust and payable via "swap:<name>" fees)
        state.external_net_p = {}
        for x in deal.external_sources:
            if x.kind == "swap":
                net = _swap_net(deal, scenario, x, t, bonds)
            else:
                net = float(ext_amounts[x.name][t - 1])
            state.external_net_p[x.name] = net
            receipt = max(net, 0.0)
            state.funds.seed(f"external:{x.name}", receipt)
            external_rows.append({"period": t, "source": x.name, "net": net, "receipt": receipt})
        seeded[t - 1] = sum(state.funds.seeded.values())

        # execute waterfalls in order; a step with a condition runs only when
        # its trigger's state matches (pass = passing/cured, fail = failing/
        # permanently_failed)
        for wf in deal.waterfall.waterfalls:
            state.current_waterfall = wf.name
            for step in wf.steps:
                if step.condition is not None and not _condition_met(
                    step.condition, state.trigger_states
                ):
                    continue
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
        triggers=pd.DataFrame(
            trigger_rows, columns=["period", "trigger", "measured", "threshold", "state"]
        ),
        externals=pd.DataFrame(external_rows, columns=["period", "source", "net", "receipt"]),
        ysoa=ysoa_used,
        adjusted_pool=adjusted_used,
    )
