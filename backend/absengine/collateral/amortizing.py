"""Level-pay amortizing loan projection ("amortizing_loan" asset class).

Per-repline pipeline each period (on the repline's own timeline):
  defaults -> interest on performing -> scheduled principal -> voluntary prepay
  -> charge-off after charge_off_lag -> recovery cash recovery_lag later.
Defaulted balance stops performing immediately but stays in trust balance
until charged off. Repline cashflows are then mapped onto the trust timeline
via collection_delay / funding_delay.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..models.collateral import CollateralPool, Repline
from ..models.scenario import CDRDefaults, CumLossDefaults, Scenario
from ..scenarios.expand import annual_to_monthly, expand
from .base import ASSET_REGISTRY
from .result import POOL_FIELDS, REPLINE_FIELDS, CollateralCashflows

_EPS = 1e-12


@dataclass
class _ReplineRun:
    """Raw projection arrays on the repline timeline (index 0 = repline period 1)."""

    arrays: dict[str, np.ndarray]


def _target_dollar_defaults(spec: CumLossDefaults, sev: np.ndarray, b0: float, n: int) -> np.ndarray:
    """Per-period default dollars implied by cum-loss + timing distribution."""
    timing = np.zeros(n)
    raw = np.asarray(spec.timing, dtype=float)
    total = raw.sum()
    if total > 0:
        raw = raw / total
    m = min(len(raw), n)
    timing[:m] = raw[:m]
    target_loss = spec.cum_net_loss * timing * b0
    d_star = np.zeros(n)
    for t in range(n):
        if target_loss[t] > 0:
            if sev[t] <= 0:
                raise ValueError("cum_loss defaults require severity > 0 in loss periods")
            d_star[t] = target_loss[t] / sev[t]
    return d_star


def _level_pay_sched(balance: float, monthly_rate: float, n_rem: int) -> float:
    """Scheduled principal this period for a level-pay loan."""
    if n_rem <= 0 or balance <= _EPS:
        return 0.0
    if n_rem == 1:
        return balance
    if monthly_rate <= 0:
        return balance / n_rem
    pmt = balance * monthly_rate / (1.0 - (1.0 + monthly_rate) ** (-n_rem))
    return min(max(pmt - balance * monthly_rate, 0.0), balance)


def _aggregate_mdr_path(d_star: np.ndarray, rep: Repline, n: int) -> np.ndarray:
    """Convert target default dollars to an MDR path on a zero-prepay reference
    amortization. Applying this *rate* path to the actual balance is the
    aggregate_MDR convention: faster actual runoff lowers realized loss."""
    mdr = np.zeros(n)
    p = rep.balance
    r = rep.gross_rate / 12.0
    n_rem = rep.remaining_term
    for t in range(n):
        if p <= _EPS or n_rem <= 0:
            break
        d = min(d_star[t], p)
        mdr[t] = d / p
        p -= d
        sched = _level_pay_sched(p, r, n_rem)
        p -= sched
        n_rem -= 1
    return mdr


def _project_repline(rep: Repline, scenario: Scenario, rep_t: int) -> dict[str, np.ndarray]:
    a = {f: np.zeros(rep_t) for f in REPLINE_FIELDS}
    if rep_t == 0:
        return a

    smm = annual_to_monthly(expand(scenario.prepay.speed, rep_t))
    sev = np.clip(expand(scenario.loss.severity, rep_t), 0.0, 1.0)
    spec = scenario.loss.defaults
    if isinstance(spec, CDRDefaults):
        mdr_path = annual_to_monthly(expand(spec.cdr, rep_t))
        d_star = None
    elif isinstance(spec, CumLossDefaults):
        d_star = _target_dollar_defaults(spec, sev, rep.balance, rep_t)
        mdr_path = _aggregate_mdr_path(d_star, rep, rep_t) if spec.method == "aggregate_MDR" else None
    else:
        raise TypeError(f"unknown DefaultSpec {type(spec)}")

    p = rep.balance
    r = rep.gross_rate / 12.0
    n_rem = rep.remaining_term

    for t in range(rep_t):
        beg = p
        a["beg_performing"][t] = beg
        if beg <= _EPS or n_rem <= 0:
            a["end_performing"][t] = beg
            continue

        # 1. defaults (move to pending charge-off; stop performing immediately)
        if mdr_path is not None:
            d = beg * mdr_path[t]
        else:
            d = min(d_star[t], beg)  # original_MDR: dollars fixed off original balance
        d = min(d, beg)
        mdr_t = d / beg if beg > 0 else 0.0
        p = beg - d

        # 2. interest accrues on performing balance only
        a["interest"][t] = p * r

        # 3. scheduled principal (level pay, recomputed on remaining term)
        sched = _level_pay_sched(p, r, n_rem)

        # 4. voluntary prepay - base excludes defaulted balance and this
        #    period's scheduled principal; defaulted portion can never prepay
        base = p - sched
        if scenario.prepay.speed_type == "all_in":
            vol = 1.0 - (1.0 - smm[t]) / (1.0 - mdr_t) if mdr_t < 1.0 else 0.0
            vol = min(max(vol, 0.0), 1.0)
        else:
            vol = smm[t]
        prepay = min(base * vol, base)

        p = p - sched - prepay
        n_rem -= 1

        a["defaults"][t] = d
        a["sched_prin"][t] = sched
        a["prepay_prin"][t] = prepay
        a["end_performing"][t] = p

    # 5./6. charge-offs, losses, recoveries via lag shifts (FIFO with fixed
    # lags == index arithmetic). Flows past the horizon are truncated; deals
    # should set num_periods to cover runoff + lags.
    co_lag = scenario.loss.charge_off_lag
    rec_lag = scenario.loss.recovery_lag
    for t in range(rep_t):
        td = t - co_lag  # default period feeding this period's charge-off
        if td >= 0:
            a["chargeoffs"][t] = a["defaults"][td]
            a["losses"][t] = a["defaults"][td] * sev[td]  # severity locked at default
        tr = t - co_lag - rec_lag
        if tr >= 0:
            a["recoveries"][t] = a["defaults"][tr] * (1.0 - sev[tr])

    # pending charge-off bucket: defaulted within the last co_lag periods
    pending = 0.0
    for t in range(rep_t):
        pending += a["defaults"][t] - a["chargeoffs"][t]
        a["pending_chargeoff"][t] = pending
        prev_pending = a["pending_chargeoff"][t - 1] if t > 0 else 0.0
        a["beg_trust"][t] = a["beg_performing"][t] + prev_pending
        a["end_trust"][t] = a["end_performing"][t] + pending
    return a


def _map_to_trust(rep: Repline, raw: dict[str, np.ndarray], num_periods: int) -> dict[str, np.ndarray]:
    """Map repline-timeline arrays to the trust timeline.

    repline period t -> trust period max(1, t - collection_delay) + funding_delay.
    Flows sum on collision; beg balances take the earliest mapped repline
    period, end balances the latest.
    """
    d, f = rep.collection_delay, rep.funding_delay
    out = {fld: np.zeros(num_periods) for fld in REPLINE_FIELDS}
    flow_fields = ["defaults", "chargeoffs", "losses", "recoveries", "interest",
                   "sched_prin", "prepay_prin"]
    seen: set[int] = set()
    rep_t = len(raw["beg_performing"])
    for t_rep in range(1, rep_t + 1):
        t_tr = max(1, t_rep - d) + f
        if t_tr > num_periods:
            break
        i, j = t_tr - 1, t_rep - 1
        for fld in flow_fields:
            out[fld][i] += raw[fld][j]
        if t_tr not in seen:
            seen.add(t_tr)
            out["beg_performing"][i] = raw["beg_performing"][j]
            out["beg_trust"][i] = raw["beg_trust"][j]
        out["end_performing"][i] = raw["end_performing"][j]
        out["end_trust"][i] = raw["end_trust"][j]
        out["pending_chargeoff"][i] = raw["pending_chargeoff"][j]
    return out


@ASSET_REGISTRY.register("amortizing_loan", config_model=CollateralPool)
class AmortizingLoanModel:
    def project(self, pool: CollateralPool, scenario: Scenario, num_periods: int) -> CollateralCashflows:
        replines: dict[str, dict[str, np.ndarray]] = {}
        for rep in pool.replines:
            # repline timeline long enough that its last mapped period reaches
            # the end of the trust timeline
            rep_t = max(0, num_periods - rep.funding_delay + rep.collection_delay)
            raw = _project_repline(rep, scenario, rep_t)
            replines[rep.id] = _map_to_trust(rep, raw, num_periods)

        agg = {f: np.zeros(num_periods) for f in POOL_FIELDS}
        for arrays in replines.values():
            for f in REPLINE_FIELDS:
                agg[f] += arrays[f]
        agg["cum_net_loss"] = np.cumsum(agg["losses"])
        agg["ysoa"] = np.zeros(num_periods)  # Phase 2: YsocConfig

        from ..models.common import PoolBalanceBasis
        basis_beg = agg["beg_performing"] if pool.fee_basis == PoolBalanceBasis.PERFORMING else agg["beg_trust"]
        agg["servicing_fee"] = basis_beg * pool.servicing_fee_rate / 12.0
        agg["adjusted_pool"] = agg["end_trust"] - agg["ysoa"]

        return CollateralCashflows(
            num_periods=num_periods,
            original_balance=pool.original_balance,
            pool=agg,
            replines=replines,
        )
