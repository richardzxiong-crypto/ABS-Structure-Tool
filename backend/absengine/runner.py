"""run_deal(deal, scenario) -> DealRunResult - the one true engine entry point.
All analytics (breakeven, matrices, dec tables) are thin loops over this."""

from __future__ import annotations

import numpy as np

from .analytics.metrics import principal_window, wal_years, yield_from_price
from .analytics.result import DealRunResult
from .collateral.base import project_pool
from .models.common import DayCount
from .models.deal import Deal
from .models.scenario import Scenario
from .models.structure import FixedCoupon, GroupNode
from .models.waterfall import PayPrincipalStep
from .waterfall import run_waterfall


class UnsupportedFeatureError(Exception):
    """A modeled-but-not-yet-implemented feature was used (clear Phase boundary)."""


def check_phase1_support(deal: Deal) -> None:
    for c in deal.structure.classes:
        if not isinstance(c.coupon, FixedCoupon):
            raise UnsupportedFeatureError(f"class {c.id}: floating coupons land in Phase 2")
        if c.day_count != DayCount.THIRTY_360:
            raise UnsupportedFeatureError(f"class {c.id}: only 30/360 in Phase 1")

    def walk(node):
        if isinstance(node, GroupNode):
            if node.mode == "target_balance":
                raise UnsupportedFeatureError(
                    f"group {node.name!r}: target_balance allocation lands in Phase 2"
                )
            for ch in node.children:
                walk(ch)

    walk(deal.structure.allocation_tree)

    for wf in deal.waterfall.waterfalls:
        for step in wf.steps:
            if step.condition is not None:
                raise UnsupportedFeatureError(f"step {step.id}: trigger conditions land in Phase 2")
            if step.source.startswith(("reserve:", "external:")):
                raise UnsupportedFeatureError(f"step {step.id}: source {step.source!r} lands in Phase 2")
            if step.type == "fund_reserve":
                raise UnsupportedFeatureError(f"step {step.id}: reserve accounts land in Phase 2")
            if isinstance(step, PayPrincipalStep) and step.amount_rule in ("priority_pda", "turbo"):
                raise UnsupportedFeatureError(
                    f"step {step.id}: amount_rule {step.amount_rule!r} lands in Phase 2"
                )
    if deal.triggers:
        raise UnsupportedFeatureError("trigger evaluation lands in Phase 2")
    if deal.reserve_accounts:
        raise UnsupportedFeatureError("reserve accounts land in Phase 2")
    if deal.ysoc is not None:
        raise UnsupportedFeatureError("YSOC lands in Phase 2")


def run_deal(deal: Deal, scenario: Scenario | str | None = None) -> DealRunResult:
    if scenario is None:
        scen = deal.scenarios[0]
    elif isinstance(scenario, str):
        scen = deal.scenario_by_name(scenario)
    else:
        scen = scenario

    check_phase1_support(deal)
    collat = project_pool(deal.collateral, scen, deal.num_periods)
    wf = run_waterfall(deal, scen, collat)

    metrics: dict = {"bonds": {}}
    for c in deal.structure.classes:
        sub = wf.bonds[wf.bonds["class_id"] == c.id]
        prin = sub["prin_paid"].to_numpy()
        cfs = prin + sub["interest_paid"].to_numpy() + sub["shortfall_paid"].to_numpy()
        m = {
            "wal_years": wal_years(prin),
            "principal_window": principal_window(prin),
            "total_writedown": float(sub["writedown"].sum()),
            "yield": yield_from_price(c.price, c.balance, cfs) if c.price else None,
        }
        metrics["bonds"][c.id] = m
    metrics["pool"] = {
        "cum_net_loss": float(collat.pool["cum_net_loss"][-1]),
        "cum_net_loss_pct": float(collat.pool["cum_net_loss"][-1] / collat.original_balance),
        "total_residual": float(wf.residual.sum()),
    }

    return DealRunResult(
        deal_id=deal.id,
        scenario_name=scen.name,
        num_periods=deal.num_periods,
        collateral=collat.to_frame(),
        bonds=wf.bonds,
        flows=wf.flows,
        residual=wf.residual,
        fees_paid=wf.fees_paid,
        retained=wf.retained,
        seeded=wf.seeded,
        metrics=metrics,
    )
