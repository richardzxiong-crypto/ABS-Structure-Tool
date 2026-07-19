"""Trigger evaluation: state machine (cure vs latch), schedule lookup, and
conditional waterfall steps switching principal from pro-rata to sequential."""

import pytest

from absengine.models.deal import Deal
from absengine.runner import UnsupportedFeatureError, check_supported, run_deal
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


def test_delinquency_trigger_rejected():
    cfg = make_deal().model_dump()
    cfg["triggers"] = [{"type": "delinquency", "name": "dq", "threshold": 0.05}]
    with pytest.raises(UnsupportedFeatureError, match="delinquency"):
        check_supported(Deal.model_validate(cfg))


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
