"""Trigger evaluation: state machine (cure vs latch), schedule lookup, and
conditional waterfall steps switching principal from pro-rata to sequential."""

import pytest

from absengine.models.deal import Deal
from absengine.runner import run_deal
from tests.conftest import make_deal


def _states(res, name):
    sub = res.triggers[res.triggers["trigger"] == name]
    return dict(zip(sub["period"], sub["state"]))


# ---------------------------------------------------------------- state machine

def test_pool_factor_cure_vs_latch():
    """operator '<' with threshold 0.9: fails while the factor is >= 0.9,
    passes (cures) once the pool amortizes below it."""
    base = make_deal().model_dump()
    for curable, terminal in [(True, "cured"), (False, "permanently_failed")]:
        cfg = dict(base)
        cfg["triggers"] = [{"type": "pool_factor", "name": "pf", "operator": "<",
                            "threshold": 0.9, "curable": curable}]
        res = run_deal(Deal.model_validate(cfg))
        st = _states(res, "pf")
        assert st[1] in ("failing", "permanently_failed")  # factor starts at 1.0
        assert st[max(st)] == terminal  # factor ends near 0
        if curable:
            assert "cured" in st.values()


def test_cnl_schedule_steps_and_no_test_before_first_entry():
    cfg = make_deal(scenarios=[{
        "name": "base",
        "loss": {"defaults": {"type": "cdr", "cdr": {"type": "scalar", "value": 0.30}},
                 "severity": {"type": "scalar", "value": 1.0}},
    }]).model_dump()
    cfg["triggers"] = [{"type": "cum_net_loss", "name": "cnl", "operator": "<=",
                        "schedule": [[3, 0.005], [6, 0.02]], "curable": True}]
    res = run_deal(Deal.model_validate(cfg))
    sub = res.triggers[res.triggers["trigger"] == "cnl"]
    by_p = sub.set_index("period")
    import pandas as pd

    # no schedule entry before period 3 -> no test -> passing with null threshold
    assert by_p.loc[1, "state"] == "passing" and pd.isna(by_p.loc[1, "threshold"])
    assert by_p.loc[3, "threshold"] == pytest.approx(0.005)
    assert by_p.loc[6, "threshold"] == pytest.approx(0.02)  # stepped up
    # 30 CDR / 100% severity blows through 0.5% quickly
    assert by_p.loc[3, "state"] == "failing"


def test_delinquency_trigger_measures_scenario_delinquency_with_lookback():
    """Delinquency 2% for 3 periods then 8%: a 3-period average trigger at 5%
    fails only once the average crosses, later than the raw level does."""
    cfg = make_deal(scenarios=[{
        "name": "base",
        "delinquency": {"type": "vector", "values": [0.02, 0.02, 0.02, 0.08]},
        "loss": {"defaults": {"type": "cdr", "cdr": {"type": "scalar", "value": 0.0}}},
    }]).model_dump()
    cfg["triggers"] = [
        {"type": "delinquency", "name": "dq1", "operator": "<=", "threshold": 0.05, "lookback": 1},
        {"type": "delinquency", "name": "dq3", "operator": "<=", "threshold": 0.05, "lookback": 3},
    ]
    res = run_deal(Deal.model_validate(cfg))
    c = res.collateral.set_index("period")
    # delinquent balance = share x post-default performing balance (no defaults here)
    assert c.loc[1, "delinquent_balance"] == pytest.approx(0.02 * c.loc[1, "beg_performing"])
    assert c.loc[4, "delinquent_balance"] == pytest.approx(0.08 * c.loc[4, "beg_performing"])
    m1 = res.triggers[res.triggers["trigger"] == "dq1"].set_index("period")
    m3 = res.triggers[res.triggers["trigger"] == "dq3"].set_index("period")
    assert m1.loc[4, "measured"] == pytest.approx(0.08)
    assert m3.loc[4, "measured"] == pytest.approx((0.02 + 0.02 + 0.08) / 3)
    assert m3.loc[5, "measured"] == pytest.approx((0.02 + 0.08 + 0.08) / 3)
    assert m1.loc[4, "state"] == "failing"
    assert m3.loc[4, "state"] == "passing" and m3.loc[5, "state"] == "failing"
    # measurement only: cash is untouched (interest = full accrual)
    assert c.loc[4, "interest"] == pytest.approx(c.loc[4, "beg_performing"] * 0.08 / 12)


def test_delinquency_withhold_cash_effect():
    """withhold: the delinquent share pays no interest and no scheduled
    principal that period; the missed sched stays in the balance."""
    base = make_deal(scenarios=[{
        "name": "base",
        "loss": {"defaults": {"type": "cdr", "cdr": {"type": "scalar", "value": 0.0}}},
    }])
    dq = make_deal(scenarios=[{
        "name": "base",
        "delinquency": {"type": "vector", "values": [0.10, 0.10, 0.10, 0.0]},
        "delinquency_cash_effect": "withhold",
        "loss": {"defaults": {"type": "cdr", "cdr": {"type": "scalar", "value": 0.0}}},
    }])
    b = run_deal(base).collateral.set_index("period")
    d = run_deal(dq).collateral.set_index("period")
    assert d.loc[1, "interest"] == pytest.approx(0.9 * b.loc[1, "interest"])
    assert d.loc[1, "sched_prin"] == pytest.approx(0.9 * b.loc[1, "sched_prin"])
    assert d.loc[1, "end_performing"] > b.loc[1, "end_performing"]
    assert d.loc[4, "interest"] == pytest.approx(d.loc[4, "beg_performing"] * 0.08 / 12)
    # once delinquency clears the balance re-amortizes and still pays off
    assert d["end_performing"].iloc[-1] == pytest.approx(0.0, abs=1e-9)
    # roll-forward ties
    assert (d["end_performing"] - (d["beg_performing"] - d["sched_prin"] - d["prepay_prin"])).abs().max() < 1e-9


# ------------------------------------------------- conditional waterfall switch

def _switch_deal() -> Deal:
    """A/B pay principal pro rata while the CNL test passes; sequential
    (A first) after it fails. Same total cash either way."""
    cfg = make_deal(scenarios=[{
        "name": "base",
        "loss": {"defaults": {"type": "cdr", "cdr": {"type": "scalar", "value": 0.12}},
                 "severity": {"type": "scalar", "value": 1.0}},
    }]).model_dump()
    cfg["triggers"] = [{"type": "cum_net_loss", "name": "cnl_test", "operator": "<=",
                        "schedule": [[1, 0.02]], "curable": True}]
    cfg["structure"]["allocation_tree"] = {
        "type": "group", "name": "root", "mode": "sequential",
        "children": [{
            "type": "group", "name": "notes", "mode": "pro_rata",
            "children": [{"type": "class", "class_id": "A"},
                         {"type": "class", "class_id": "B"}],
        }],
    }
    prin = [s for s in cfg["waterfall"]["waterfalls"][1]["steps"] if s["type"] == "pay_principal"]
    assert prin, "expected a principal step to replace"
    steps = cfg["waterfall"]["waterfalls"][1]["steps"]
    idx = steps.index(prin[0])
    steps[idx:idx + 1] = [
        {**prin[0], "id": "prin_pro_rata", "targets": ["notes"],
         "condition": {"trigger": "cnl_test", "when": "pass"}},
        {**prin[0], "id": "prin_seq_a", "targets": ["A"],
         "condition": {"trigger": "cnl_test", "when": "fail"}},
        {**prin[0], "id": "prin_seq_b", "targets": ["B"],
         "condition": {"trigger": "cnl_test", "when": "fail"}},
    ]
    return Deal.model_validate(cfg)


def test_conditional_steps_switch_pro_rata_to_sequential():
    deal = _switch_deal()
    res = run_deal(deal)

    st = _states(res, "cnl_test")
    fail_from = min(p for p, s in st.items() if s in ("failing", "permanently_failed"))
    assert fail_from > 1  # passes at least the first period

    bonds = res.bonds.set_index(["period", "class_id"])
    # while passing: pro rata -> both classes receive principal
    pre = fail_from - 1
    assert bonds.loc[(pre, "A"), "prin_paid"] > 0
    assert bonds.loc[(pre, "B"), "prin_paid"] > 0
    # after failure: sequential -> B gets nothing while A is outstanding
    assert bonds.loc[(fail_from, "A"), "prin_paid"] > 0
    assert bonds.loc[(fail_from, "B"), "prin_paid"] == pytest.approx(0.0, abs=1e-9)
    assert bonds.loc[(fail_from, "A"), "end_balance"] > 0

    # only the matching conditional step ever fires
    f = res.flows
    pro_rata_periods = set(f[f["step_id"] == "prin_pro_rata"]["period"])
    seq_periods = set(f[f["step_id"] == "prin_seq_a"]["period"])
    assert pro_rata_periods == {p for p, s in st.items() if s in ("passing", "cured")}
    assert not (pro_rata_periods & seq_periods)


def test_delinquent_balance_past_maturity_is_a_balloon():
    """A share withheld at the final scheduled payment stays outstanding and
    is due (and paid, net of the delinquent share) in every later period."""
    deal = make_deal(num_periods=15, scenarios=[{
        "name": "base",
        "delinquency": {"type": "vector", "values": [0.0] * 11 + [0.5, 0.5, 0.0]},
        "delinquency_cash_effect": "withhold",
        "loss": {"defaults": {"type": "cdr", "cdr": {"type": "scalar", "value": 0.0}}},
    }])
    c = run_deal(deal).collateral.set_index("period")
    assert c.loc[12, "end_performing"] > 0  # half the final payment withheld
    assert c.loc[13, "sched_prin"] == pytest.approx(0.5 * c.loc[13, "beg_performing"])
    assert c.loc[14, "end_performing"] == pytest.approx(0.0, abs=1e-9)
