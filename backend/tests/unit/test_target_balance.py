"""target_balance allocation: a group is paid principal only down to its
scheduled / pct-of-pool target; the excess flows to the next listed target
(companion classes). Interest steps ignore the target."""

import numpy as np
import pytest
from pydantic import ValidationError

from absengine.models.deal import Deal
from absengine.models.structure import ClassNode, GroupNode, TargetBalanceSpec
from absengine.runner import run_deal
from absengine.waterfall.allocation import allocate, allocate_across, node_capacity
from tests.conftest import make_deal


def cls(cid):
    return ClassNode(class_id=cid)


# ---------------------------------------------------------------- allocator

def test_group_cap_limits_take_and_overflow_goes_to_next_target():
    pac = GroupNode(name="PAC", mode="target_balance", children=[cls("A")],
                    target_balance_spec=TargetBalanceSpec(schedule=[70.0]))
    cap = {"A": 80.0, "B": 20.0}
    group_cap = lambda g: 10.0  # balance 80 - target 70
    assert node_capacity(pac, cap.get, group_cap) == 10.0
    out = allocate_across(15.0, [pac, cls("B")], cap.get, cap.get, group_cap)
    assert out == {"A": 10.0, "B": 5.0}


def test_without_group_cap_target_balance_acts_sequentially():
    grp = GroupNode(name="S", mode="target_balance", children=[cls("A"), cls("B")],
                    target_balance_spec=TargetBalanceSpec(schedule=[0.0]))
    cap = {"A": 4.0, "B": 6.0}
    assert allocate(7.0, grp, cap.get, cap.get) == {"A": 4.0, "B": 3.0}


def test_pro_rata_distribution_inside_group():
    grp = GroupNode(name="S", mode="target_balance", children=[cls("A"), cls("B")],
                    target_balance_spec=TargetBalanceSpec(schedule=[0.0], distribution="pro_rata"))
    cap = {"A": 100.0, "B": 100.0}
    basis = {"A": 60.0, "B": 40.0}
    out = allocate(10.0, grp, cap.get, basis.get, lambda g: 10.0)
    assert out["A"] == pytest.approx(6.0) and out["B"] == pytest.approx(4.0)


def test_target_balance_spec_required():
    with pytest.raises(ValidationError, match="target_balance_spec"):
        GroupNode(name="g", mode="target_balance", children=[cls("A")])


def test_schedule_beyond_end_is_zero():
    spec = TargetBalanceSpec(schedule=[50.0, 40.0])
    assert spec.target_for(1, 0.0) == 50.0
    assert spec.target_for(2, 0.0) == 40.0
    assert spec.target_for(3, 0.0) == 0.0
    assert TargetBalanceSpec(kind="pct_of_pool", pct=0.5).target_for(7, 90.0) == 45.0


# ---------------------------------------------------------------- end to end

def _pac_deal(spec: dict, num_periods: int = 12) -> Deal:
    cfg = make_deal(num_periods=num_periods).model_dump()
    cfg["structure"]["allocation_tree"] = {
        "type": "group", "name": "root", "mode": "sequential",
        "children": [
            {"type": "group", "name": "PAC", "mode": "target_balance",
             "children": [{"type": "class", "class_id": "A"}],
             "target_balance_spec": spec},
            {"type": "class", "class_id": "B"},
        ],
    }
    # scheduled class first (to its target), companion next, then the
    # scheduled class absorbs whatever is left once the companion is gone
    cfg["waterfall"]["waterfalls"][1]["steps"][0]["targets"] = ["PAC", "B", "A"]
    return Deal.model_validate(cfg)


def _by_class(res, cid):
    return res.bonds[res.bonds["class_id"] == cid].set_index("period")


def test_scheduled_class_tracks_schedule_and_companion_takes_excess():
    schedule = [76.0, 72.0, 68.0, 64.0, 60.0, 56.0, 52.0, 48.0, 44.0, 40.0, 36.0, 32.0]
    deal = _pac_deal({"kind": "schedule", "schedule": schedule})
    res = run_deal(deal)
    a, b = _by_class(res, "A"), _by_class(res, "B")
    prin = res.collateral.set_index("period")
    coll = prin["sched_prin"] + prin["prepay_prin"] + prin["recoveries"]

    # periods 1-4: cap = 4 each period (80->76->72->68->64), collections
    # ~8.4 -> A lands exactly on schedule, the companion takes the excess
    for t in range(1, 5):
        assert a.loc[t, "prin_paid"] == pytest.approx(4.0, abs=1e-9)
        assert a.loc[t, "end_balance"] == pytest.approx(schedule[t - 1], abs=1e-9)
        assert b.loc[t, "prin_paid"] == pytest.approx(coll[t] - 4.0, abs=1e-9)
    # period 5: the companion is retired mid-period and A (listed again after
    # B) absorbs the remainder below its schedule
    assert b.loc[5, "end_balance"] == pytest.approx(0.0, abs=1e-9)
    assert a.loc[5, "prin_paid"] == pytest.approx(coll[5] - b.loc[5, "beg_balance"], abs=1e-9)
    assert a.loc[5, "end_balance"] < schedule[4]
    # thereafter A takes every dollar of collections
    for t in range(6, deal.num_periods + 1):
        assert a.loc[t, "prin_paid"] == pytest.approx(min(coll[t], a.loc[t, "beg_balance"]), abs=1e-9)
    assert a["end_balance"].iloc[-1] == pytest.approx(0.0, abs=1e-9)

    # cash conservation still holds with the tree cap in play
    paid = res.flows.groupby("period")["paid"].sum()
    for t in range(1, deal.num_periods + 1):
        assert res.seeded[t - 1] == pytest.approx(float(paid.get(t, 0.0)) + res.retained[t - 1], abs=1e-9)


def test_pct_of_pool_target():
    deal = _pac_deal({"kind": "pct_of_pool", "pct": 0.5, "pool_basis": "trust"})
    res = run_deal(deal)
    a, b = _by_class(res, "A"), _by_class(res, "B")
    pool_end = res.collateral.set_index("period")["end_trust"]
    for t in range(1, deal.num_periods + 1):
        target = 0.5 * pool_end[t]
        # never paid below target while the companion is outstanding
        if b.loc[t, "end_balance"] > 1e-9:
            assert a.loc[t, "end_balance"] >= target - 1e-9
        # above target -> companion got nothing this period
        if a.loc[t, "end_balance"] > target + 1e-9:
            assert b.loc[t, "prin_paid"] == pytest.approx(0.0, abs=1e-9)
    assert np.isclose(a["end_balance"].iloc[-1], 0.0) and np.isclose(b["end_balance"].iloc[-1], 0.0)


def test_interest_step_ignores_target_cap():
    """Listing both classes of a 2-class target_balance group on pay_interest
    collapses into the group; with a zero schedule (cap 0 for principal) the
    interest step still pays both in full."""
    cfg = make_deal().model_dump()
    cfg["structure"]["allocation_tree"] = {
        "type": "group", "name": "root", "mode": "sequential",
        "children": [
            {"type": "group", "name": "S", "mode": "target_balance",
             "children": [{"type": "class", "class_id": "A"}, {"type": "class", "class_id": "B"}],
             "target_balance_spec": {"kind": "schedule", "schedule": [100.0] * 12}},
        ],
    }
    res = run_deal(Deal.model_validate(cfg))
    a = _by_class(res, "A")
    int_coll = res.collateral.set_index("period")["interest"] - res.collateral.set_index("period")["servicing_fee"]
    for t in range(1, 13):
        accrued_total = res.bonds[res.bonds["period"] == t]["interest_accrued"].sum()
        if int_coll[t] >= accrued_total + res.fees_paid[t - 1]:
            assert a.loc[t, "interest_paid"] == pytest.approx(a.loc[t, "interest_accrued"], abs=1e-9)
    assert a.loc[1, "interest_paid"] == pytest.approx(a.loc[1, "interest_accrued"], abs=1e-9)
    # principal: cap = 100 - 100 = 0 in every period -> nothing paid, cash retained
    assert a["prin_paid"].sum() == pytest.approx(0.0)
    assert res.residual.sum() > 0  # principal collections fall through to residual
