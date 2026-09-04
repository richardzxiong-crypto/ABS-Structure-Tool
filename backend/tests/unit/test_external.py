"""External cash sources: fixed amounts seeded into external:<name> buckets,
scenario overrides, active windows, and swap net receipts / payments."""

import numpy as np
import pytest
from pydantic import ValidationError

from absengine.models.deal import Deal
from absengine.runner import UnsupportedFeatureError, check_supported, run_deal
from tests.conftest import make_deal


def _with_external(source: dict, steps_patch=None, **overrides) -> Deal:
    cfg = make_deal(**overrides).model_dump()
    cfg["external_sources"] = [source]
    if steps_patch:
        steps_patch(cfg)
    return Deal.model_validate(cfg)


def _conserved(res, n):
    paid = res.flows.groupby("period")["paid"].sum()
    for t in range(1, n + 1):
        assert res.seeded[t - 1] == pytest.approx(float(paid.get(t, 0.0)) + res.retained[t - 1], abs=1e-9)


def test_amount_source_feeds_a_step_and_window_applies():
    def patch(cfg):
        # a sponsor top-up pays class B interest from periods 2-4 only
        cfg["waterfall"]["waterfalls"][0]["steps"].append(
            {"type": "pay_interest", "id": "x1", "source": "external:topup", "targets": ["B"]})
        # sweep whatever is left to the residual so nothing is stranded
        cfg["waterfall"]["waterfalls"][1]["steps"].append(
            {"type": "release_residual", "id": "x2", "source": "external:topup"})
        # make the interest bucket unable to pay B: pay A only from collections
        cfg["waterfall"]["waterfalls"][0]["steps"][1]["targets"] = ["A"]

    deal = _with_external(
        {"name": "topup", "amount": {"type": "scalar", "value": 5.0}, "start_period": 2, "end_period": 4},
        patch,
    )
    res = run_deal(deal)
    ext = res.externals.set_index("period")
    assert ext.loc[1, "receipt"] == 0.0 and ext.loc[2, "receipt"] == 5.0 and ext.loc[5, "receipt"] == 0.0
    b = res.bonds[res.bonds["class_id"] == "B"].set_index("period")
    assert b.loc[1, "interest_paid"] == 0.0  # nothing external yet, collections go to A only
    for t in (2, 3, 4):
        assert b.loc[t, "interest_paid"] == pytest.approx(b.loc[t, "interest_accrued"])
    assert b.loc[5, "interest_paid"] == 0.0
    # 5 - B's interest lands in the residual via the sweep step
    x = res.flows[(res.flows["step_id"] == "x2") & (res.flows["period"] == 2)]["paid"].iloc[0]
    assert x == pytest.approx(5.0 - b.loc[2, "interest_accrued"])
    _conserved(res, deal.num_periods)


def test_scenario_override_replaces_deal_amount():
    def patch(cfg):
        cfg["waterfall"]["waterfalls"][1]["steps"].append(
            {"type": "release_residual", "id": "x2", "source": "external:grant"})
        cfg["scenarios"].append({
            "name": "generous",
            "external_amounts": {"grant": {"type": "vector", "values": [10.0, 0.0]}},
        })

    deal = _with_external({"name": "grant", "amount": {"type": "scalar", "value": 1.0}}, patch)
    base = run_deal(deal, "base").externals.set_index("period")["receipt"]
    gen = run_deal(deal, "generous").externals.set_index("period")["receipt"]
    assert (base == 1.0).all()
    assert gen.loc[1] == 10.0 and (gen.loc[2:] == 0.0).all()


def test_unused_external_cash_is_retained():
    deal = _with_external({"name": "idle", "amount": {"type": "scalar", "value": 2.0}})
    res = run_deal(deal)
    assert np.allclose(res.retained, 2.0)
    _conserved(res, deal.num_periods)


def test_swap_receipt_and_payment_legs():
    """Trust pays 4% fixed, receives SOFR on class A's balance. Scenario 1:
    SOFR 6% -> net receipt 2%/12 x A balance seeded into the bucket.
    Scenario 2: SOFR 2% -> the trust owes 2%/12 x A, paid via swap:hedge."""
    def patch(cfg):
        cfg["waterfall"]["waterfalls"][0]["steps"].insert(
            0, {"type": "pay_fees", "id": "s0", "source": "interest_collections", "fees": ["swap:hedge"]})
        cfg["waterfall"]["waterfalls"][0]["steps"].append(
            {"type": "release_residual", "id": "s1", "source": "external:hedge"})
        cfg["scenarios"][0]["index_curves"] = {"SOFR": {"type": "scalar", "value": 0.06}}
        cfg["scenarios"].append({"name": "low", "index_curves": {"SOFR": {"type": "scalar", "value": 0.02}}})

    deal = _with_external(
        {"name": "hedge", "kind": "swap", "notional_class": "A", "fixed_rate": 0.04, "index": "SOFR"},
        patch,
    )
    hi = run_deal(deal, "base")
    a = hi.bonds[hi.bonds["class_id"] == "A"].set_index("period")
    ext = hi.externals.set_index("period")
    for t in (1, 2, 3):
        expect = a.loc[t, "beg_balance"] * 0.02 / 12.0
        assert ext.loc[t, "net"] == pytest.approx(expect)
        assert ext.loc[t, "receipt"] == pytest.approx(expect)
    assert (hi.flows[hi.flows["step_id"] == "s0"]["paid"] == 0.0).all()  # nothing owed
    _conserved(hi, deal.num_periods)

    lo = run_deal(deal, "low")
    ext = lo.externals.set_index("period")
    s0 = lo.flows[lo.flows["step_id"] == "s0"].set_index("period")
    a = lo.bonds[lo.bonds["class_id"] == "A"].set_index("period")
    for t in (1, 2, 3):
        owed = a.loc[t, "beg_balance"] * 0.02 / 12.0
        assert ext.loc[t, "net"] == pytest.approx(-owed) and ext.loc[t, "receipt"] == 0.0
        assert s0.loc[t, "due"] == pytest.approx(owed) and s0.loc[t, "paid"] == pytest.approx(owed)
    trustee = lo.flows[(lo.flows["target"] == "trustee") & (lo.flows["period"] == 1)]["paid"].iloc[0]
    assert lo.fees_paid[0] == pytest.approx(a.loc[1, "beg_balance"] * 0.02 / 12.0 + trustee)
    _conserved(lo, deal.num_periods)


def test_swap_notional_schedule_extends_last_value():
    def patch(cfg):
        cfg["scenarios"][0]["index_curves"] = {"SOFR": {"type": "scalar", "value": 0.05}}

    deal = _with_external(
        {"name": "cap", "kind": "swap", "notional_schedule": [100.0, 50.0], "fixed_rate": 0.02,
         "index": "SOFR", "spread": 0.01},
        patch,
    )
    ext = run_deal(deal).externals.set_index("period")
    assert ext.loc[1, "net"] == pytest.approx(100.0 * 0.04 / 12.0)
    assert ext.loc[2, "net"] == pytest.approx(50.0 * 0.04 / 12.0)
    assert ext.loc[3, "net"] == pytest.approx(50.0 * 0.04 / 12.0)


def test_validation_and_gates():
    with pytest.raises(ValidationError, match="unknown notional class"):
        _with_external({"name": "s", "kind": "swap", "notional_class": "Z", "index": "SOFR"})
    with pytest.raises(ValidationError, match="needs an index"):
        _with_external({"name": "s", "kind": "swap", "notional_class": "A"})
    with pytest.raises(ValidationError, match="unknown fees"):
        _with_external(
            {"name": "s", "amount": {"type": "scalar", "value": 1.0}},
            lambda cfg: cfg["waterfall"]["waterfalls"][0]["steps"][0]["fees"].append("swap:s"),
        )
    # swap without an index curve in a scenario: valid, not runnable
    deal = _with_external({"name": "s", "kind": "swap", "notional_class": "A", "index": "SOFR"})
    with pytest.raises(UnsupportedFeatureError, match="no curve"):
        check_supported(deal)
