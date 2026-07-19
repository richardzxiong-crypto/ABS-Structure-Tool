"""Loss breakeven solver: for each class, the stress level at which it first
takes a writedown (principal breakeven) or first misses timely interest
(shortfall breakeven).

The dial adapts to the scenario: absolute CNL level for cum-loss scenarios
("A4 breaks at 9.8% CNL"), CDR multiplier for CDR scenarios ("breaks at
4.3x base CDR"). Assumes both events are monotone in the dial - true for
sensible waterfalls (more loss never heals a class).

One engine run per distinct stress level, shared across every class and both
events via a memo cache, so solving the whole capital structure costs on the
order of 50-100 runs.
"""

from __future__ import annotations

from ..models.deal import Deal
from ..models.scenario import Scenario
from ..runner import run_deal
from .stress import loss_dial, with_loss_level

_WD_TOL = 1.0  # $ of writedown that counts as broken
_SF_TOL = 0.01  # $ of period-end unpaid interest that counts as a miss


class _Prober:
    """Memoized 'run the deal at stress level x' -> per-class break flags."""

    def __init__(self, deal: Deal, scenario: Scenario):
        self.deal = deal
        self.scenario = scenario
        self.cache: dict[float, dict[str, dict[str, bool]]] = {}
        self.runs = 0

    def probe(self, x: float) -> dict[str, dict[str, bool]]:
        key = round(x, 10)
        if key not in self.cache:
            res = run_deal(self.deal, with_loss_level(self.scenario, x))
            self.runs += 1
            flags: dict[str, dict[str, bool]] = {}
            for c in self.deal.structure.classes:
                sub = res.bonds[res.bonds["class_id"] == c.id]
                flags[c.id] = {
                    "writedown": float(sub["writedown"].sum()) > _WD_TOL,
                    "interest_shortfall": float(sub["shortfall_end"].max()) > _SF_TOL,
                }
            self.cache[key] = flags
        return self.cache[key]


def _bisect(prober: _Prober, cid: str, event: str, lo: float, hi: float, tol: float) -> float:
    """Smallest x in (lo, hi] where the event occurs; P(lo)=False, P(hi)=True."""
    while hi - lo > tol:
        mid = (lo + hi) / 2.0
        if prober.probe(mid)[cid][event]:
            hi = mid
        else:
            lo = mid
    return hi


def solve_breakevens(deal: Deal, scenario: Scenario | str | None = None) -> dict:
    """Per-class breakeven levels for both events.

    Returns {dial, base, cap, runs, classes: {cid: {writedown, interest_shortfall}}}
    where each event value is the breakeven level, 0.0 if broken even with no
    losses, or None if the class survives the cap.
    """
    if scenario is None:
        scen = deal.scenarios[0]
    elif isinstance(scenario, str):
        scen = deal.scenario_by_name(scenario)
    else:
        scen = scenario

    dial, base, cap = loss_dial(scen)
    tol = cap / 2000.0  # 5bp of CNL / 0.025x of a 50x CDR cap
    prober = _Prober(deal, scen)

    at_zero = prober.probe(0.0)
    at_cap = prober.probe(cap)

    out: dict[str, dict[str, float | None]] = {}
    for c in deal.structure.classes:
        out[c.id] = {}
        for event in ("writedown", "interest_shortfall"):
            if at_zero[c.id][event]:
                out[c.id][event] = 0.0
            elif not at_cap[c.id][event]:
                out[c.id][event] = None  # survives the cap
            else:
                out[c.id][event] = _bisect(prober, c.id, event, 0.0, cap, tol)

    return {
        "dial": dial,
        "base": base,
        "cap": cap,
        "runs": prober.runs,
        "classes": out,
    }
