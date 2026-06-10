"""Golden tests 6-7: full deal vs an independent mini-model; allocation tree."""

import numpy as np
import pytest

from absengine.runner import run_deal
from tests.conftest import make_deal

TOL = 1e-6


def smm(annual: float) -> float:
    return 1 - (1 - annual) ** (1 / 12)


def independent_model():
    """Hand-rolled simulation of the conftest deal: 100 pool @8% WAC 12mo,
    5 CPR / 1 CDR / 50 sev / 1-period charge-off lag / 2-period recovery lag,
    A:80@5% -> B:20@7% sequential, 25bp trustee fee."""
    r = 0.08 / 12
    s, m = smm(0.05), smm(0.01)
    bal, defaults = 100.0, []
    pool = []  # per period dict
    for t in range(12):
        beg = bal
        d = beg * m
        p = beg - d
        n = 12 - t
        pmt = p * r / (1 - (1 + r) ** -n) if n > 1 else p * (1 + r)
        sched = p if n == 1 else pmt - p * r
        prepay = (p - sched) * s
        interest = p * r
        defaults.append(d)
        co = defaults[t - 1] if t >= 1 else 0.0
        loss, rec = co * 0.5, (defaults[t - 3] * 0.5 if t >= 3 else 0.0)
        pending = d  # only last period's defaults pend (lag 1)
        bal = p - sched - prepay
        pool.append(dict(beg_trust=beg + (defaults[t - 1] if t >= 1 else 0.0),
                         interest=interest, sched=sched, prepay=prepay,
                         rec=rec, loss=loss, co=co, end_perf=bal,
                         end_trust=bal + pending))

    # waterfall
    a_bal, b_bal, rows = 80.0, 20.0, []
    for t in range(12):
        pp = pool[t]
        int_cash = pp["interest"]
        prin_cash = pp["sched"] + pp["prepay"] + pp["rec"]
        fee_due = pp["beg_trust"] * 0.0025 / 12
        fee = min(fee_due, int_cash)
        int_cash -= fee
        a_int_due, b_int_due = a_bal * 0.05 / 12, b_bal * 0.07 / 12
        a_int = min(a_int_due, int_cash); int_cash -= a_int
        b_int = min(b_int_due, int_cash); int_cash -= b_int
        a_prin = min(prin_cash, a_bal); prin_cash -= a_prin; a_bal -= a_prin
        b_prin = min(prin_cash, b_bal); prin_cash -= b_prin; b_bal -= b_prin
        residual = prin_cash + int_cash
        rows.append(dict(fee=fee, a_int=a_int, b_int=b_int, a_prin=a_prin,
                         b_prin=b_prin, residual=residual,
                         a_bal=a_bal, b_bal=b_bal))
    return pool, rows


def test_two_tranche_deal_matches_independent_model(deal):
    pool, rows = independent_model()
    res = run_deal(deal)
    a = res.bonds[res.bonds["class_id"] == "A"].reset_index(drop=True)
    b = res.bonds[res.bonds["class_id"] == "B"].reset_index(drop=True)
    for t in range(12):
        assert res.collateral["interest"][t] == pytest.approx(pool[t]["interest"], abs=TOL)
        assert res.collateral["end_trust"][t] == pytest.approx(pool[t]["end_trust"], abs=TOL)
        assert res.fees_paid[t] == pytest.approx(rows[t]["fee"], abs=TOL)
        assert a["interest_paid"][t] == pytest.approx(rows[t]["a_int"], abs=TOL)
        assert b["interest_paid"][t] == pytest.approx(rows[t]["b_int"], abs=TOL)
        assert a["prin_paid"][t] == pytest.approx(rows[t]["a_prin"], abs=TOL)
        assert b["prin_paid"][t] == pytest.approx(rows[t]["b_prin"], abs=TOL)
        assert res.residual[t] == pytest.approx(rows[t]["residual"], abs=TOL)
        assert a["end_balance"][t] == pytest.approx(rows[t]["a_bal"], abs=TOL)
        if t < 11:  # final period takes the writedown
            assert b["end_balance"][t] == pytest.approx(rows[t]["b_bal"], abs=TOL)
    # WAL from the independent model
    a_prin = np.array([r["a_prin"] for r in rows])
    expected_wal = (a_prin * np.arange(1, 13)).sum() / a_prin.sum() / 12
    assert res.metrics["bonds"]["A"]["wal_years"] == pytest.approx(expected_wal, abs=1e-9)
    assert res.metrics["bonds"]["B"]["total_writedown"] == pytest.approx(
        rows[-1]["b_bal"], abs=TOL
    )


@pytest.mark.parametrize("oc", [0.0, 5.0])
def test_regular_pda_due_amount(oc):
    """regular_pda: due each period = max(0, total bonds - (pool_end - target_OC))."""
    deal = make_deal()
    step = deal.waterfall.waterfalls[1].steps[0]
    step.amount_rule = "regular_pda"
    step.target_oc.value = oc
    res = run_deal(deal)
    pda_flows = res.flows[res.flows["step_id"] == "p1"]
    bond_bal = {"A": 80.0, "B": 20.0}
    for t in range(1, 13):
        pool_end = float(res.collateral["end_trust"][t - 1])
        expected_due = max(0.0, sum(bond_bal.values()) - (pool_end - oc))
        rows = pda_flows[pda_flows["period"] == t]
        assert rows["due"].iloc[0] == pytest.approx(expected_due, abs=TOL)
        for _, row in rows.iterrows():
            bond_bal[row["target"]] -= row["paid"]


def make_tree_deal(targets: list[str]):
    """5 classes, 3-level tree: root sequential -> Group A pro-rata
    (A1, Group A2 sequential [A2a, A2b], A3) -> B1."""
    classes = [
        {"id": "A1", "balance": 40.0, "coupon": {"type": "fixed", "rate": 0.05}},
        {"id": "A2a", "balance": 10.0, "coupon": {"type": "fixed", "rate": 0.05}},
        {"id": "A2b", "balance": 10.0, "coupon": {"type": "fixed", "rate": 0.05}},
        {"id": "A3", "balance": 20.0, "coupon": {"type": "fixed", "rate": 0.05}},
        {"id": "B1", "balance": 20.0, "coupon": {"type": "fixed", "rate": 0.07}},
    ]
    tree = {
        "type": "group", "name": "root", "mode": "sequential",
        "children": [
            {"type": "group", "name": "Group A", "mode": "pro_rata", "children": [
                {"type": "class", "class_id": "A1"},
                {"type": "group", "name": "Group A2", "mode": "sequential", "children": [
                    {"type": "class", "class_id": "A2a"},
                    {"type": "class", "class_id": "A2b"},
                ]},
                {"type": "class", "class_id": "A3"},
            ]},
            {"type": "class", "class_id": "B1"},
        ],
    }
    deal = make_deal()
    cfg = deal.model_dump()
    cfg["structure"] = {"classes": classes, "allocation_tree": tree}
    cfg["waterfall"]["waterfalls"][0]["steps"][1]["targets"] = ["A1", "A2a", "A2b", "A3", "B1"]
    cfg["waterfall"]["waterfalls"][1]["steps"][0]["targets"] = targets
    from absengine.models.deal import Deal

    return Deal.model_validate(cfg)


def test_three_level_tree_pro_rata_with_nested_sequential():
    """A dollar to Group A splits pro-rata across A1 / Group A2 / A3; Group
    A2's share fills A2a before A2b."""
    deal = make_tree_deal(["Group A", "B1"])
    res = run_deal(deal)
    p1 = res.bonds[res.bonds["period"] == 1].set_index("class_id")
    prin = float(res.collateral["sched_prin"][0] + res.collateral["prepay_prin"][0]
                 + res.collateral["recoveries"][0])
    # weights by current balance: A1 40/80, A2 20/80, A3 20/80
    assert p1.loc["A1", "prin_paid"] == pytest.approx(prin * 0.5, abs=TOL)
    assert p1.loc["A3", "prin_paid"] == pytest.approx(prin * 0.25, abs=TOL)
    # Group A2's pro-rata share goes sequential: all to A2a first
    assert p1.loc["A2a", "prin_paid"] == pytest.approx(prin * 0.25, abs=TOL)
    assert p1.loc["A2b", "prin_paid"] == pytest.approx(0.0, abs=TOL)
    assert p1.loc["B1", "prin_paid"] == pytest.approx(0.0, abs=TOL)


def test_collapse_rule_listed_classes_equal_group_target():
    """Listing all of a pro-rata group's classes in order == targeting the
    group: the tree mode wins over listed order."""
    by_group = run_deal(make_tree_deal(["Group A", "B1"]))
    by_list = run_deal(make_tree_deal(["A1", "A2a", "A2b", "A3", "B1"]))
    cols = ["interest_paid", "prin_paid", "end_balance"]
    assert np.allclose(by_group.bonds[cols].to_numpy(), by_list.bonds[cols].to_numpy(), atol=TOL)
