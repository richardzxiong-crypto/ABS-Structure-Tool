"""Sensitivity matrix (prepay x loss grid) and price/yield tables - thin
loops over run_deal on the already-validated engine."""

from __future__ import annotations

import numpy as np

from ..models.deal import Deal
from ..models.scenario import Scenario
from ..runner import run_deal
from .metrics import yield_from_price
from .stress import scale_loss, scale_prepay

DEFAULT_PREPAY_MULTS = [0.5, 0.75, 1.0, 1.25, 1.5]
DEFAULT_LOSS_MULTS = [0.5, 1.0, 1.5, 2.0, 3.0]
DEFAULT_PRICES = [96.0, 97.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0, 104.0]


def _resolve(deal: Deal, scenario: Scenario | str | None) -> Scenario:
    if scenario is None:
        return deal.scenarios[0]
    if isinstance(scenario, str):
        return deal.scenario_by_name(scenario)
    return scenario


def sensitivity_matrix(
    deal: Deal,
    scenario: Scenario | str | None = None,
    prepay_mults: list[float] | None = None,
    loss_mults: list[float] | None = None,
) -> dict:
    """Run the deal on a grid of (prepay multiple x loss multiple) around the
    scenario's base assumptions. Each cell reports per-class WAL / yield /
    writedown and the pool's realized cum net loss."""
    scen = _resolve(deal, scenario)
    pm = prepay_mults or DEFAULT_PREPAY_MULTS
    lm = loss_mults or DEFAULT_LOSS_MULTS

    cells = []
    for p in pm:
        row = []
        for loss_m in lm:
            res = run_deal(deal, scale_loss(scale_prepay(scen, p), loss_m))
            row.append({
                "prepay_mult": p,
                "loss_mult": loss_m,
                "pool_cnl_pct": res.metrics["pool"]["cum_net_loss_pct"],
                "classes": {
                    cid: {
                        "wal_years": m["wal_years"],
                        "yield": m["yield"],
                        "writedown": m["total_writedown"],
                    }
                    for cid, m in res.metrics["bonds"].items()
                },
            })
        cells.append(row)

    return {
        "scenario": scen.name,
        "prepay_mults": pm,
        "loss_mults": lm,
        "class_ids": [c.id for c in deal.structure.classes],
        "cells": cells,  # cells[i][j] = (prepay_mults[i], loss_mults[j])
    }


def price_yield_table(
    deal: Deal,
    scenario: Scenario | str | None = None,
    prices: list[float] | None = None,
) -> dict:
    """Yield at a grid of prices for every class, on one base-scenario run.
    Cashflows = interest + shortfall repayments + principal actually paid."""
    scen = _resolve(deal, scenario)
    grid = prices or DEFAULT_PRICES
    res = run_deal(deal, scen)

    out: dict[str, dict] = {}
    for c in deal.structure.classes:
        sub = res.bonds[res.bonds["class_id"] == c.id]
        cfs = (
            sub["prin_paid"].to_numpy()
            + sub["interest_paid"].to_numpy()
            + sub["shortfall_paid"].to_numpy()
        )
        out[c.id] = {
            "wal_years": res.metrics["bonds"][c.id]["wal_years"],
            "yields": {str(p): yield_from_price(p, c.balance, np.asarray(cfs)) for p in grid},
        }

    return {"scenario": scen.name, "prices": grid, "classes": out}
