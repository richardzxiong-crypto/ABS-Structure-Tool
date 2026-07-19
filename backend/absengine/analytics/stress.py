"""Scenario transforms for analytics: scale prepay / loss assumptions.

All transforms return deep copies - the input scenario is never mutated.
"""

from __future__ import annotations

from ..models.scenario import CDRDefaults, CumLossDefaults, RampRate, ScalarRate, Scenario, VectorRate


def _scale_rate(spec, m: float):
    if isinstance(spec, ScalarRate):
        return ScalarRate(value=spec.value * m)
    if isinstance(spec, VectorRate):
        return VectorRate(values=[v * m for v in spec.values])
    if isinstance(spec, RampRate):
        return RampRate(start=spec.start * m, end=spec.end * m, periods=spec.periods)
    raise TypeError(f"unknown RateSpec {type(spec)}")


def scale_prepay(scen: Scenario, m: float) -> Scenario:
    """Multiply the prepay speed by m (works for CPR and ABS units)."""
    out = scen.model_copy(deep=True)
    out.prepay.speed = _scale_rate(out.prepay.speed, m)
    return out


def scale_loss(scen: Scenario, m: float) -> Scenario:
    """Multiply the loss assumption by m: cum_net_loss for cum-loss scenarios,
    the CDR vector for CDR scenarios."""
    out = scen.model_copy(deep=True)
    d = out.loss.defaults
    if isinstance(d, CumLossDefaults):
        d.cum_net_loss = d.cum_net_loss * m
    elif isinstance(d, CDRDefaults):
        d.cdr = _scale_rate(d.cdr, m)
    else:
        raise TypeError(f"unknown DefaultSpec {type(d)}")
    return out


def with_loss_level(scen: Scenario, x: float) -> Scenario:
    """Set the absolute loss level: cum_net_loss = x for cum-loss scenarios;
    for CDR scenarios x is a multiplier on the base CDR (the natural dial)."""
    d = scen.loss.defaults
    if isinstance(d, CumLossDefaults):
        out = scen.model_copy(deep=True)
        out.loss.defaults.cum_net_loss = x
        return out
    return scale_loss(scen, x)


def loss_dial(scen: Scenario) -> tuple[str, float, float]:
    """(dial name, base value, sensible solver cap) for this scenario's
    default spec: absolute CNL level for cum-loss, CDR multiplier for CDR."""
    d = scen.loss.defaults
    if isinstance(d, CumLossDefaults):
        return "cnl_level", d.cum_net_loss, 1.0
    return "cdr_multiplier", 1.0, 50.0
