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
from .models.structure import GroupNode
from .waterfall import run_waterfall


class UnsupportedFeatureError(Exception):
    """A modeled-but-not-yet-implemented feature was used (clear phase boundary)."""


def check_supported(deal: Deal) -> None:
    if deal.dates is None:
        for c in deal.structure.classes:
            if c.day_count != DayCount.THIRTY_360:
                raise UnsupportedFeatureError(
                    f"class {c.id}: {c.day_count.value} day count needs deal dates "
                    f"(set deal.dates for a payment calendar)"
                )

    def walk(node):
        if isinstance(node, GroupNode):
            if node.mode == "target_balance":
                raise UnsupportedFeatureError(
                    f"group {node.name!r}: target_balance allocation is not implemented yet"
                )
            for ch in node.children:
                walk(ch)

    walk(deal.structure.allocation_tree)

    for wf in deal.waterfall.waterfalls:
        for step in wf.steps:
            if step.source.startswith("external:"):
                raise UnsupportedFeatureError(f"step {step.id}: external sources are not implemented yet")
    for trig in deal.triggers:
        if trig.type == "delinquency":
            raise UnsupportedFeatureError(
                f"trigger {trig.name!r}: delinquency triggers need delinquency "
                f"modeling in the collateral engine (not implemented yet)"
            )


# backwards-compatible alias (tests / older callers)
check_phase1_support = check_supported


def run_deal(deal: Deal, scenario: Scenario | str | None = None) -> DealRunResult:
    if scenario is None:
        scen = deal.scenarios[0]
    elif isinstance(scenario, str):
        scen = deal.scenario_by_name(scenario)
    else:
        scen = scenario

    check_supported(deal)
    collat = project_pool(deal.collateral, scen, deal.num_periods, deal.ysoc)
    wf = run_waterfall(deal, scen, collat)
    # reported ysoa/adjusted_pool stay at the primary strike (dealer-report
    # convention; the PDA formulas use the stepdown strike internally once it
    # latches - wf.ysoa/wf.adjusted_pool carry the realized path). Period 1
    # honors the hard-coded closing YSOA when configured.
    if deal.ysoc is not None and deal.ysoc.initial_amount is not None:
        basis = collat.basis_beg(deal.ysoc.basis)
        collat.pool["ysoa"][0] = deal.ysoc.initial_amount
        collat.pool["adjusted_pool"][0] = float(basis[0]) - deal.ysoc.initial_amount

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
        accounts=wf.accounts,
        triggers=wf.triggers,
        metrics=metrics,
    )
