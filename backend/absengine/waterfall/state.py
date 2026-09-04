from __future__ import annotations

from dataclasses import dataclass, field

from ..collateral.result import CollateralCashflows
from ..models.accounts import FeeSpec, ReserveAccount
from ..models.common import PoolBalanceBasis
from ..models.deal import Deal
from ..models.scenario import Scenario

_EPS = 1e-12


@dataclass
class FlowRecord:
    """One audit row per (step, target) - the debugger and UI drill-down are
    literally this log."""

    period: int
    waterfall: str
    step_id: str
    step_type: str
    source: str
    target: str
    due: float
    paid: float


@dataclass
class BondState:
    id: str
    balance: float
    original_balance: float
    shortfall: float = 0.0  # unpaid interest carried from prior periods
    writedown: float = 0.0
    # per-period working values, reset by the interpreter each period
    beg_balance_p: float = 0.0
    interest_accrued_p: float = 0.0
    interest_unpaid_p: float = 0.0  # current-period accrual still owed
    interest_paid_p: float = 0.0
    shortfall_paid_p: float = 0.0
    prin_paid_p: float = 0.0


class AvailableFunds:
    """Named cash buckets. draw() returns min(requested, available) and never
    overdraws."""

    def __init__(self):
        self.buckets: dict[str, float] = {}
        self.seeded: dict[str, float] = {}

    def seed(self, name: str, amount: float) -> None:
        self.buckets[name] = amount
        self.seeded[name] = amount

    def deposit(self, name: str, amount: float) -> None:
        """Move cash into a bucket mid-waterfall (e.g. fund_reserve)."""
        self.buckets[name] = self.buckets.get(name, 0.0) + max(amount, 0.0)

    def balance(self, name: str) -> float:
        return self.buckets.get(name, 0.0)

    def draw(self, name: str, amount: float) -> float:
        avail = self.buckets.get(name, 0.0)
        take = min(max(amount, 0.0), avail)
        if take > _EPS:
            self.buckets[name] = avail - take
        return take

    def total_remaining(self) -> float:
        return sum(self.buckets.values())


@dataclass
class EngineState:
    deal: Deal
    scenario: Scenario
    collat: CollateralCashflows
    bonds: dict[str, BondState]
    period: int = 0  # 1-based
    funds: AvailableFunds = field(default_factory=AvailableFunds)
    flows: list[FlowRecord] = field(default_factory=list)
    accounts: dict[str, float] = field(default_factory=dict)  # reserve balances
    trigger_states: dict = field(default_factory=dict)  # name -> TriggerState
    ysoc_stepdown_active: bool = False  # latched by the interpreter
    current_waterfall: str = ""
    prin_collections_p: float = 0.0
    residual_paid_p: float = 0.0
    fees_paid_p: float = 0.0
    # per-fee amounts paid this period, so a second pay_fees step (e.g. the
    # reserve-sourced twin of a collections step) only pays the remainder
    fee_paid_by_name_p: dict[str, float] = field(default_factory=dict)
    # swap net amounts this period by external-source name (negative = the
    # trust owes; payable via "swap:<name>" in a pay_fees step)
    external_net_p: dict[str, float] = field(default_factory=dict)

    @property
    def fees_by_name(self) -> dict[str, FeeSpec]:
        return {f.name: f for f in self.deal.fees}

    @property
    def reserves_by_name(self) -> dict[str, ReserveAccount]:
        return {r.name: r for r in self.deal.reserve_accounts}

    def record(self, step, target: str, due: float, paid: float) -> None:
        self.flows.append(
            FlowRecord(
                period=self.period,
                waterfall=self.current_waterfall,
                step_id=step.id,
                step_type=step.type,
                source=step.source,
                target=target,
                due=due,
                paid=paid,
            )
        )

    # ------------------------------------------------------------- pool bases
    # The ADJUSTED basis is owned here, not by CollateralCashflows: the YSOA
    # strike selection (stepdown) depends on bond state, and period 1 may use
    # the hard-coded closing amount.

    def ysoa_end(self) -> float:
        """Selected YSOA as of the end of the current period."""
        ysoc = self.deal.ysoc
        if ysoc is None:
            return 0.0
        key = (
            "ysoa_stepdown"
            if self.ysoc_stepdown_active and ysoc.stepdown_rate is not None
            else "ysoa_primary"
        )
        return float(self.collat.pool[key][self.period - 1])

    def _ysoa0(self) -> float:
        ysoc = self.deal.ysoc
        if ysoc is None:
            return 0.0
        if ysoc.initial_amount is not None:
            return ysoc.initial_amount
        return self.collat.ysoa0_primary

    def _ysoc_basis(self) -> PoolBalanceBasis:
        return self.deal.ysoc.basis if self.deal.ysoc is not None else PoolBalanceBasis.TRUST

    def pool_basis_beg(self, basis) -> float:
        if basis == PoolBalanceBasis.ADJUSTED:
            beg = float(self.collat.basis_beg(self._ysoc_basis())[self.period - 1])
            if self.period == 1:
                return beg - self._ysoa0()
            ysoc = self.deal.ysoc
            key = (
                "ysoa_stepdown"
                if self.ysoc_stepdown_active and ysoc is not None and ysoc.stepdown_rate is not None
                else "ysoa_primary"
            )
            return beg - float(self.collat.pool[key][self.period - 2])
        return float(self.collat.basis_beg(basis)[self.period - 1])

    def pool_basis_end(self, basis) -> float:
        if basis == PoolBalanceBasis.ADJUSTED:
            ysoc = self.deal.ysoc
            if self.period == 1 and ysoc is not None and ysoc.initial_amount is not None:
                # "hard-coded for the first period": closing balance - given YSOA
                return float(self.collat.basis_beg(self._ysoc_basis())[0]) - ysoc.initial_amount
            end = float(self.collat.basis_end(self._ysoc_basis())[self.period - 1])
            return end - self.ysoa_end()
        return float(self.collat.basis_end(basis)[self.period - 1])

    def original_pool_basis(self, basis) -> float:
        """Closing-date balance on the given basis (for pct_original specs)."""
        if basis == PoolBalanceBasis.ADJUSTED:
            return float(self.collat.basis_beg(self._ysoc_basis())[0]) - self._ysoa0()
        return self.collat.original_balance
