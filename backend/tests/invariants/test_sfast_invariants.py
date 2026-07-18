"""Invariants on the full SFAST 2026-1 deal (library copy) across all its
scenarios, including the stress path that exercises reserve draws, interest
shortfalls, priority-PDA tiers, and final-period writedowns.

Cash conservation must exclude bucket-to-bucket transfers from "paid":
fund_reserve deposits and the retire step's reserve release move cash between
buckets (it stays in `retained` or is paid by a later step), so summing every
flow row would double-count them.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from absengine.models.deal import Deal
from absengine.runner import run_deal

DEAL_PATH = Path(__file__).resolve().parents[3] / "deals" / "sfast-2026-1" / "deal.json"

deal = Deal.model_validate(json.loads(DEAL_PATH.read_text()))


def _external_paid_by_period(res):
    f = res.flows
    transfers = (f["step_type"] == "fund_reserve") | (
        (f["step_type"] == "retire_bonds") & (f["target"] == f["source"])
    )
    return f[~transfers].groupby("period")["paid"].sum()


@pytest.mark.parametrize("scen", [s.name for s in deal.scenarios])
def test_sfast_invariants(scen):
    res = run_deal(deal, scen)

    # cash conservation: seeded == external payments + retained, every period
    paid = _external_paid_by_period(res)
    for t in range(1, deal.num_periods + 1):
        assert res.seeded[t - 1] == pytest.approx(
            float(paid.get(t, 0.0)) + res.retained[t - 1], abs=1e-6
        ), f"period {t}"

    # no negative balances or payments anywhere
    for col in ["beg_balance", "end_balance", "interest_paid", "shortfall_paid",
                "prin_paid", "shortfall_end", "writedown"]:
        assert (res.bonds[col] >= -1e-6).all(), col
    for col in ["beg_performing", "end_performing", "beg_trust", "end_trust",
                "pending_chargeoff", "defaults", "losses", "recoveries", "ysoa",
                "adjusted_pool"]:
        assert (res.collateral[col] >= -1e-6).all(), col
    assert (res.accounts["balance"] >= -1e-6).all()

    # bond roll-forward ties per class
    for c in deal.structure.classes:
        sub = res.bonds[res.bonds["class_id"] == c.id]
        assert np.allclose(
            sub["end_balance"], sub["beg_balance"] - sub["prin_paid"] - sub["writedown"],
            atol=1e-6,
        ), c.id

    # writedowns only in the final period, and total principal + writedown
    # returns each class's original balance
    wd = res.bonds[res.bonds["writedown"] > 0]
    assert (wd["period"] == deal.num_periods).all()
    for c in deal.structure.classes:
        sub = res.bonds[res.bonds["class_id"] == c.id]
        assert sub["prin_paid"].sum() + sub["writedown"].sum() == pytest.approx(
            c.balance, abs=1e-6
        ), c.id


def test_stress_exercises_the_hard_paths():
    """The stress scenario must actually hit the machinery the Intex tie-out
    scenarios never touch."""
    res = run_deal(deal, "stress")
    f = res.flows

    # aggregate_MDR fits the loss to the target exactly
    assert res.metrics["pool"]["cum_net_loss_pct"] == pytest.approx(0.20, abs=1e-9)

    # reserve is drawn (and never below zero, asserted above)
    draws = f[(f["source"] == "reserve:reserve") & (f["paid"] > 0)]
    assert draws["paid"].sum() > 1e6

    # every priority-PDA tier binds
    for sid in ["first_alloc", "second_alloc", "third_alloc"]:
        assert f[(f["step_id"] == sid) & (f["paid"] > 0)].shape[0] > 0, sid

    # interest shortfalls accrue on the subordinates
    assert (res.bonds[res.bonds["class_id"].isin(["B", "C"])]["shortfall_end"] > 1.0).any()

    # writedowns land in reverse seniority: C and B wiped before A4 partial,
    # A1-A3 whole
    wd = {m: res.metrics["bonds"][m]["total_writedown"] for m in res.metrics["bonds"]}
    assert wd["C"] == pytest.approx(58_600_000)
    assert wd["B"] == pytest.approx(71_880_000)
    assert 0 < wd["A4"] < 119_520_000
    assert wd["A1"] == wd["A2A"] == wd["A2B"] == wd["A3"] == 0
