from __future__ import annotations

from dataclasses import dataclass, field

from ..collateral.result import CollateralCashflows
from ..models.accounts import FeeSpec
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
    monthly_rate: float
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
    current_waterfall: str = ""
    prin_collections_p: float = 0.0
    residual_paid_p: float = 0.0
    fees_paid_p: float = 0.0

    @property
    def fees_by_name(self) -> dict[str, FeeSpec]:
        return {f.name: f for f in self.deal.fees}

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

    def pool_basis_beg(self, basis) -> float:
        return float(self.collat.basis_beg(basis)[self.period - 1])

    def pool_basis_end(self, basis) -> float:
        return float(self.collat.basis_end(basis)[self.period - 1])
