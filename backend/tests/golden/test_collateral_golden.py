"""Golden tests 1-5: collateral engine vs independent hand calculations (1e-6)."""

import numpy as np
import pytest

from absengine.collateral.base import project_pool
from absengine.models.collateral import CollateralPool, Repline
from absengine.models.scenario import (
    CDRDefaults,
    CumLossDefaults,
    LossAssumption,
    PrepayAssumption,
    ScalarRate,
    Scenario,
)

TOL = 1e-6


def smm(cpr: float) -> float:
    return 1 - (1 - cpr) ** (1 / 12)


def make_pool(**kw) -> CollateralPool:
    rep = {"id": "R1", "balance": 100_000.0, "gross_rate": 0.06,
           "original_term": 12, "remaining_term": 12}
    rep.update(kw)
    return CollateralPool(replines=[Repline(**rep)])


# ------------------------------------------------------------------ test 1

def test_zero_speed_matches_closed_form_annuity():
    pool = make_pool()
    cf = project_pool(pool, Scenario(), 12)
    r = 0.06 / 12
    pmt = 100_000 * r / (1 - (1 + r) ** -12)
    bal = 100_000.0
    for t in range(12):
        interest = bal * r
        sched = pmt - interest
        assert cf.pool["interest"][t] == pytest.approx(interest, abs=TOL)
        assert cf.pool["sched_prin"][t] == pytest.approx(sched, abs=TOL)
        bal -= sched
        assert cf.pool["end_performing"][t] == pytest.approx(bal, abs=TOL)
    assert cf.pool["end_performing"][-1] == pytest.approx(0.0, abs=TOL)
    assert cf.pool["sched_prin"].sum() == pytest.approx(100_000.0, abs=TOL)


# ------------------------------------------------------------------ test 2

def test_10cpr_voluntary_hand_computed():
    pool = make_pool()
    scen = Scenario(prepay=PrepayAssumption(speed=ScalarRate(value=0.10)))
    cf = project_pool(pool, scen, 12)
    r = 0.06 / 12
    s = smm(0.10)
    bal = 100_000.0
    for t in range(12):
        n = 12 - t
        pmt = bal * r / (1 - (1 + r) ** -n) if n > 1 else bal * (1 + r)
        sched = bal if n == 1 else pmt - bal * r
        prepay = (bal - sched) * s
        assert cf.pool["sched_prin"][t] == pytest.approx(sched, abs=TOL)
        assert cf.pool["prepay_prin"][t] == pytest.approx(prepay, abs=TOL)
        bal -= sched + prepay
    assert cf.pool["end_performing"][-1] == pytest.approx(0.0, abs=TOL)


def test_all_in_speed_backs_out_voluntary():
    """10 all-in speed + 2 CDR: vol_SMM = 1-(1-allin_SMM)/(1-MDR); prepay
    never touches the defaulted balance."""
    pool = make_pool()
    mdr = smm(0.02)
    allin = smm(0.10)
    vol = 1 - (1 - allin) / (1 - mdr)
    scen = Scenario(
        prepay=PrepayAssumption(speed=ScalarRate(value=0.10), speed_type="all_in"),
        loss=LossAssumption(defaults=CDRDefaults(cdr=ScalarRate(value=0.02)),
                            severity=ScalarRate(value=1.0)),
    )
    cf = project_pool(pool, scen, 12)
    r = 0.06 / 12
    bal = 100_000.0
    for t in range(12):
        d = bal * mdr
        p = bal - d
        n = 12 - t
        pmt = p * r / (1 - (1 + r) ** -n) if n > 1 else p * (1 + r)
        sched = p if n == 1 else pmt - p * r
        prepay = (p - sched) * vol  # base excludes defaults + sched
        assert cf.pool["defaults"][t] == pytest.approx(d, abs=TOL)
        assert cf.pool["prepay_prin"][t] == pytest.approx(prepay, abs=TOL)
        bal = p - sched - prepay
    # all-in survivorship check: (1-mdr)(1-vol) == 1-allin
    assert (1 - mdr) * (1 - vol) == pytest.approx(1 - allin, abs=1e-12)


# ------------------------------------------------------------------ test 3

def test_chargeoff_and_recovery_pipeline():
    """2 CDR / 40% severity / 3-period charge-off lag / 4-period recovery lag."""
    pool = make_pool(remaining_term=24, original_term=24)
    scen = Scenario(
        loss=LossAssumption(
            defaults=CDRDefaults(cdr=ScalarRate(value=0.02)),
            severity=ScalarRate(value=0.40),
            charge_off_lag=3,
            recovery_lag=4,
        )
    )
    n = 36
    cf = project_pool(pool, scen, n)
    d = cf.pool["defaults"]
    for t in range(n):
        co = d[t - 3] if t >= 3 else 0.0
        rec = d[t - 7] * 0.60 if t >= 7 else 0.0
        loss = (d[t - 3] if t >= 3 else 0.0) * 0.40
        assert cf.pool["chargeoffs"][t] == pytest.approx(co, abs=TOL)
        assert cf.pool["recoveries"][t] == pytest.approx(rec, abs=TOL)
        assert cf.pool["losses"][t] == pytest.approx(loss, abs=TOL)
        # pending bucket = defaults of the last 3 periods
        pending = d[max(0, t - 2): t + 1].sum()
        assert cf.pool["pending_chargeoff"][t] == pytest.approx(pending, abs=TOL)
        # trust balance = performing + pending; diverges while bucket is full
        assert cf.pool["end_trust"][t] == pytest.approx(
            cf.pool["end_performing"][t] + pending, abs=TOL
        )
    assert cf.pool["pending_chargeoff"][:10].max() > 0
    # everything defaulted eventually charges off and recovers (horizon covers lags)
    assert cf.pool["chargeoffs"].sum() == pytest.approx(d.sum(), abs=TOL)
    assert cf.pool["recoveries"].sum() == pytest.approx(d.sum() * 0.60, abs=TOL)


# ------------------------------------------------------------------ test 4

@pytest.mark.parametrize("method", ["aggregate_MDR", "original_MDR"])
def test_cum_loss_timing_hits_target(method):
    """8% cum net loss, 5-period timing - both methods hit the target with no
    prepayments; per-period defaults match the hand calc."""
    pool = make_pool()
    timing = [0.2, 0.3, 0.25, 0.15, 0.10]
    scen = Scenario(
        loss=LossAssumption(
            defaults=CumLossDefaults(cum_net_loss=0.08, timing=timing, method=method),
            severity=ScalarRate(value=0.5),
        )
    )
    cf = project_pool(pool, scen, 12)
    for t in range(5):
        target_default = 0.08 * timing[t] * 100_000 / 0.5
        assert cf.pool["defaults"][t] == pytest.approx(target_default, abs=1e-4)
    assert cf.pool["cum_net_loss"][-1] == pytest.approx(0.08 * 100_000, abs=1e-4)


def test_aggregate_mdr_scales_down_with_prepays_original_does_not():
    """With prepays, aggregate_MDR (a rate path on actual balance) realizes
    less loss than the input; original_MDR keeps dollar defaults fixed."""
    pool = make_pool()
    timing = [0.2, 0.3, 0.25, 0.15, 0.10]
    base = dict(cum_net_loss=0.08, timing=timing)
    prepay = PrepayAssumption(speed=ScalarRate(value=0.30))

    def run(method):
        scen = Scenario(
            prepay=prepay,
            loss=LossAssumption(
                defaults=CumLossDefaults(**base, method=method),
                severity=ScalarRate(value=0.5),
            ),
        )
        return project_pool(pool, scen, 12).pool["cum_net_loss"][-1]

    assert run("original_MDR") == pytest.approx(0.08 * 100_000, abs=1e-4)
    assert run("aggregate_MDR") < 0.08 * 100_000 - 100


# ------------------------------------------------------------------ test 5

def test_collection_delay_combines_first_periods():
    """delay 1: repline periods 1+2 collections flow to trust period 1;
    repline period k+1 flows to trust period k thereafter."""
    plain = project_pool(make_pool(), Scenario(), 12)
    delayed = project_pool(make_pool(collection_delay=1), Scenario(), 12)
    ref = plain.pool
    for fld in ["interest", "sched_prin", "prepay_prin"]:
        assert delayed.pool[fld][0] == pytest.approx(ref[fld][0] + ref[fld][1], abs=TOL)
        for t in range(1, 11):
            assert delayed.pool[fld][t] == pytest.approx(ref[fld][t + 1], abs=TOL)
        assert delayed.pool[fld][11] == pytest.approx(0.0, abs=TOL)
    # balances as of the latest mapped repline period
    assert delayed.pool["end_performing"][0] == pytest.approx(ref["end_performing"][1], abs=TOL)
    assert delayed.pool["beg_performing"][0] == pytest.approx(ref["beg_performing"][0], abs=TOL)


def test_funding_delay_shifts_later():
    """delay 1: repline period t shows up in trust period t+1; trust period 1
    sees nothing from this repline."""
    plain = project_pool(make_pool(), Scenario(), 13)
    delayed = project_pool(make_pool(funding_delay=1), Scenario(), 13)
    ref = plain.pool
    for fld in ["interest", "sched_prin", "beg_performing", "end_performing"]:
        assert delayed.pool[fld][0] == pytest.approx(0.0, abs=TOL)
        for t in range(12):
            assert delayed.pool[fld][t + 1] == pytest.approx(ref[fld][t], abs=TOL)


def test_two_replines_with_delays_aggregate():
    pool = CollateralPool(replines=[
        Repline(id="X", balance=50_000, gross_rate=0.06, original_term=12,
                remaining_term=12, collection_delay=1),
        Repline(id="Y", balance=50_000, gross_rate=0.06, original_term=12,
                remaining_term=12, funding_delay=1),
    ])
    cf = project_pool(pool, Scenario(), 13)
    x = cf.replines["X"]
    y = cf.replines["Y"]
    assert np.allclose(cf.pool["sched_prin"], x["sched_prin"] + y["sched_prin"], atol=TOL)
    assert y["sched_prin"][0] == 0.0
    assert x["sched_prin"][-1] == 0.0
