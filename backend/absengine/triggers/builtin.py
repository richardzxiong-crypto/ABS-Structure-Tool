"""Built-in trigger handlers: one-line measurements. The interpreter owns the
cure/latch state machine; a handler just answers "what is the measured value
and threshold this period?" (None = no test scheduled -> treated as passing).

Measurements are taken at determination (period start, after bond interest
accrual, before any distribution):
- cum_net_loss: realized cum loss through this collection period / original
  balance, vs a stepped schedule (last entry with period <= t applies).
- pool_factor: beginning basis balance / original balance.
- oc_test: beginning basis balance / total beginning bond balance.
- ic_test: this period's interest collections / total bond interest accrued.
- delinquency: delinquent balance / beginning basis balance, averaged over
  the last `lookback` collection periods (the delinquent balance comes from
  the scenario's delinquency vector applied to the performing balance).
"""

from __future__ import annotations

from ..models.triggers import (
    CumNetLossTrigger,
    DelinquencyTrigger,
    ICTestTrigger,
    OCTestTrigger,
    PoolFactorTrigger,
)
from .base import TRIGGER_REGISTRY


@TRIGGER_REGISTRY.register("cum_net_loss", config_model=CumNetLossTrigger)
class CumNetLossHandler:
    def measure(self, cfg: CumNetLossTrigger, state) -> tuple[float, float] | None:
        threshold = None
        for period, value in sorted(cfg.schedule):
            if period <= state.period:
                threshold = value
        if threshold is None:
            return None
        cnl = float(state.collat.pool["cum_net_loss"][state.period - 1])
        return cnl / state.collat.original_balance, threshold


@TRIGGER_REGISTRY.register("pool_factor", config_model=PoolFactorTrigger)
class PoolFactorHandler:
    def measure(self, cfg: PoolFactorTrigger, state) -> tuple[float, float] | None:
        factor = state.pool_basis_beg(cfg.basis) / state.collat.original_balance
        return factor, cfg.threshold


@TRIGGER_REGISTRY.register("oc_test", config_model=OCTestTrigger)
class OCTestHandler:
    def measure(self, cfg: OCTestTrigger, state) -> tuple[float, float] | None:
        bonds = sum(b.beg_balance_p for b in state.bonds.values())
        if bonds <= 0:
            return None  # nothing outstanding: test is moot
        return state.pool_basis_beg(cfg.basis) / bonds, cfg.threshold


@TRIGGER_REGISTRY.register("ic_test", config_model=ICTestTrigger)
class ICTestHandler:
    def measure(self, cfg: ICTestTrigger, state) -> tuple[float, float] | None:
        accrued = sum(b.interest_accrued_p for b in state.bonds.values())
        if accrued <= 0:
            return None
        interest = float(state.collat.interest_collections()[state.period - 1])
        return interest / accrued, cfg.threshold


@TRIGGER_REGISTRY.register("delinquency", config_model=DelinquencyTrigger)
class DelinquencyHandler:
    def measure(self, cfg: DelinquencyTrigger, state) -> tuple[float, float] | None:
        t = state.period
        ratios = []
        for p in range(max(1, t - cfg.lookback + 1), t + 1):
            pool = float(state.collat.basis_beg(cfg.basis)[p - 1])
            if pool <= 0:
                continue
            ratios.append(float(state.collat.pool["delinquent_balance"][p - 1]) / pool)
        if not ratios:
            return None  # pool gone: nothing to test
        return sum(ratios) / len(ratios), cfg.threshold
