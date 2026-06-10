"""Invariants that must hold on every run: cash conservation, no negative
balances, pool roll-forward ties."""

import numpy as np
import pytest

from absengine.runner import run_deal
from tests.conftest import make_deal

SCENARIOS = [
    {"name": "zero"},
    {"name": "fast", "prepay": {"speed": {"type": "scalar", "value": 0.30}}},
    {"name": "loss-heavy",
     "prepay": {"speed": {"type": "scalar", "value": 0.05}},
     "loss": {"defaults": {"type": "cdr", "cdr": {"type": "scalar", "value": 0.10}},
              "severity": {"type": "scalar", "value": 0.6},
              "charge_off_lag": 2, "recovery_lag": 3}},
    {"name": "cum-loss",
     "loss": {"defaults": {"type": "cum_loss", "cum_net_loss": 0.10,
                           "timing": [0.1, 0.2, 0.3, 0.2, 0.1, 0.1],
                           "method": "original_MDR"},
              "severity": {"type": "scalar", "value": 0.5}}},
]


@pytest.mark.parametrize("scen", SCENARIOS, ids=lambda s: s["name"])
def test_invariants(scen):
    deal = make_deal(scenarios=[scen])
    res = run_deal(deal)

    # cash conservation each period: seeded == all step payments + retained
    paid_by_period = res.flows.groupby("period")["paid"].sum()
    for t in range(1, deal.num_periods + 1):
        paid = float(paid_by_period.get(t, 0.0))
        assert res.seeded[t - 1] == pytest.approx(paid + res.retained[t - 1], abs=1e-9)

    # no negative balances anywhere
    for col in ["beg_balance", "end_balance", "interest_paid", "prin_paid", "shortfall_end"]:
        assert (res.bonds[col] >= -1e-9).all(), col
    for col in ["beg_performing", "end_performing", "beg_trust", "end_trust",
                "pending_chargeoff", "defaults", "losses", "recoveries"]:
        assert (res.collateral[col] >= -1e-9).all(), col

    # pool roll-forward ties (no delays in this deal)
    c = res.collateral
    assert np.allclose(
        c["end_performing"],
        c["beg_performing"] - c["defaults"] - c["sched_prin"] - c["prepay_prin"],
        atol=1e-9,
    )
    assert np.allclose(
        c["end_trust"],
        c["beg_trust"] - c["chargeoffs"] - c["sched_prin"] - c["prepay_prin"],
        atol=1e-9,
    )

    # bond roll-forward
    for cid in ["A", "B"]:
        sub = res.bonds[res.bonds["class_id"] == cid]
        expected_end = sub["beg_balance"] - sub["prin_paid"] - sub["writedown"]
        assert np.allclose(sub["end_balance"], expected_end, atol=1e-9)
