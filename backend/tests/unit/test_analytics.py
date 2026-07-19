"""Analytics layer: breakeven solver, sensitivity matrix, price/yield."""

import pytest

from absengine.analytics.breakeven import solve_breakevens
from absengine.analytics.matrix import price_yield_table, sensitivity_matrix
from absengine.analytics.stress import loss_dial, scale_loss, scale_prepay, with_loss_level
from absengine.models.scenario import CumLossDefaults, ScalarRate, Scenario, VectorRate
from tests.conftest import make_deal


def test_stress_transforms_do_not_mutate():
    scen = Scenario(prepay={"speed": {"type": "scalar", "value": 0.10}})
    out = scale_prepay(scen, 2.0)
    assert out.prepay.speed.value == pytest.approx(0.20)
    assert scen.prepay.speed.value == pytest.approx(0.10)

    scen2 = Scenario(loss={"defaults": {"type": "cdr", "cdr": {"type": "vector", "values": [0.02, 0.04]}}})
    out2 = scale_loss(scen2, 1.5)
    assert out2.loss.defaults.cdr.values == pytest.approx([0.03, 0.06])
    assert scen2.loss.defaults.cdr.values == pytest.approx([0.02, 0.04])


def test_loss_dial_adapts_to_spec():
    cdr_scen = Scenario()
    assert loss_dial(cdr_scen)[0] == "cdr_multiplier"
    cl_scen = Scenario(loss={"defaults": {"type": "cum_loss", "cum_net_loss": 0.05, "timing": [1.0]}})
    dial, base, cap = loss_dial(cl_scen)
    assert dial == "cnl_level" and base == pytest.approx(0.05) and cap == 1.0
    assert with_loss_level(cl_scen, 0.30).loss.defaults.cum_net_loss == pytest.approx(0.30)


def test_breakeven_ordering_matches_seniority():
    """On the 2-tranche A/B deal, B must break at a lower CNL than A, and both
    breakevens must be reproducible: running at the level minus a step doesn't
    write down; at the level it does."""
    deal = make_deal(scenarios=[{
        "name": "base",
        "loss": {"defaults": {"type": "cum_loss", "cum_net_loss": 0.02,
                              "timing": [0.4, 0.3, 0.2, 0.1]},
                 "severity": {"type": "scalar", "value": 0.5}},
    }])
    be = solve_breakevens(deal, "base")
    assert be["dial"] == "cnl_level"
    b_wd = be["classes"]["B"]["writedown"]
    a_wd = be["classes"]["A"]["writedown"]
    assert b_wd is not None and b_wd > 0
    assert a_wd is None or a_wd > b_wd

    from absengine.analytics.stress import with_loss_level as wll
    from absengine.runner import run_deal

    tol = be["cap"] / 2000.0
    below = run_deal(deal, wll(deal.scenarios[0], max(b_wd - 2 * tol, 0.0)))
    at = run_deal(deal, wll(deal.scenarios[0], b_wd + tol))
    wd = lambda res: float(res.bonds[res.bonds["class_id"] == "B"]["writedown"].sum())
    assert wd(below) <= 1.0
    assert wd(at) > 1.0


def test_matrix_shape_and_monotone_wal():
    deal = make_deal()
    mx = sensitivity_matrix(deal, None, prepay_mults=[0.5, 2.0], loss_mults=[1.0])
    assert len(mx["cells"]) == 2 and len(mx["cells"][0]) == 1
    slow = mx["cells"][0][0]["classes"]["A"]["wal_years"]
    fast = mx["cells"][1][0]["classes"]["A"]["wal_years"]
    assert fast < slow  # faster prepay shortens senior WAL


def test_price_yield_monotone_in_price():
    deal = make_deal()
    py = price_yield_table(deal, None, prices=[98.0, 100.0, 102.0])
    ys = [py["classes"]["A"]["yields"][p] for p in ("98.0", "100.0", "102.0")]
    assert all(y is not None for y in ys)
    assert ys[0] > ys[1] > ys[2]  # discount yields more than premium
