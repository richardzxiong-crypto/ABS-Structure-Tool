"""Level-pay amortizing loan projection ("amortizing_loan" asset class).

Per-repline pipeline each period (on the repline's own timeline):
  defaults -> interest on performing -> scheduled principal -> voluntary prepay
  -> charge-off after charge_off_lag -> recovery cash recovery_lag later.
Defaulted balance stops performing immediately but stays in trust balance
until charged off. Repline cashflows are then mapped onto the trust timeline
via collection_delay / funding_delay.
"""

from __future__ import annotations

import numpy as np

from ..models.accounts import YsocConfig
from ..models.collateral import CollateralPool, Repline
from ..models.scenario import CDRDefaults, CumLossDefaults, Scenario
from ..scenarios.expand import annual_to_monthly, expand
from .base import ASSET_REGISTRY
from .result import POOL_FIELDS, REPLINE_FIELDS, CollateralCashflows

_EPS = 1e-12


def _default_timing(spec: CumLossDefaults, n: int, co_lag: int) -> np.ndarray:
    """Per-period *default* timing weights (normalized to sum <= 1).

    timing_applies_to="losses": the curve positions loss recognition
    (charge-offs); the default weight at period t is the loss weight at
    t + co_lag. Annual buckets spread evenly over each year's feasible
    charge-off months (the first co_lag months of year 1 carry no mass).
    """
    raw = np.asarray(spec.timing, dtype=float)
    total = raw.sum()
    if total > 0:
        raw = raw / total

    if spec.timing_applies_to == "losses":
        horizon = max(n + co_lag, len(raw) * 12 if spec.timing_unit == "annual" else len(raw))
        loss_w = np.zeros(horizon)
        if spec.timing_unit == "annual":
            for y, share in enumerate(raw):
                months = [m for m in range(y * 12, (y + 1) * 12) if m >= co_lag]
                if share > 0 and not months:
                    raise ValueError(
                        f"loss timing year {y + 1} has no feasible charge-off months "
                        f"(charge_off_lag {co_lag})"
                    )
                for m in months:
                    loss_w[m] = share / len(months)
        else:
            m = min(len(raw), horizon)
            loss_w[:m] = raw[:m]
            if loss_w[:co_lag].sum() > 0:
                raise ValueError(
                    f"loss timing puts mass in the first {co_lag} periods, which "
                    f"cannot be reached with charge_off_lag {co_lag}"
                )
        return loss_w[co_lag:co_lag + n]

    if spec.timing_unit == "annual":
        raw = np.repeat(raw / 12.0, 12)
    timing = np.zeros(n)
    m = min(len(raw), n)
    timing[:m] = raw[:m]
    return timing


def _target_dollar_defaults(
    spec: CumLossDefaults, sev: np.ndarray, b0: float, n: int, co_lag: int
) -> np.ndarray:
    """Per-period default dollars implied by cum-loss + timing distribution."""
    timing = _default_timing(spec, n, co_lag)
    target_loss = spec.cum_net_loss * timing * b0
    d_star = np.zeros(n)
    for t in range(n):
        if target_loss[t] > 0:
            if sev[t] <= 0:
                raise ValueError("cum_loss defaults require severity > 0 in loss periods")
            d_star[t] = target_loss[t] / sev[t]
    return d_star


def _smm_path(rep: Repline, scenario: Scenario, n: int) -> np.ndarray:
    """Voluntary/all-in SMM vector for one repline."""
    speed = expand(scenario.prepay.speed, n)
    if scenario.prepay.speed_unit == "abs":
        # ABS = monthly prepay as a fraction of original balance;
        # SMM_m = ABS / (1 - ABS*(m-1)), m = loan age in months (1-based)
        age0 = rep.original_term - rep.remaining_term  # payments already made
        m = age0 + np.arange(1, n + 1)
        denom = 1.0 - speed * (m - 1)
        smm = np.where(denom > speed, speed / denom, 1.0)
        return np.clip(smm, 0.0, 1.0)
    return annual_to_monthly(speed)


def _dq_path(scenario: Scenario, n: int) -> np.ndarray:
    """Delinquent share of the performing balance per period (a level in
    [0, 1], not an annual rate)."""
    return np.clip(expand(scenario.delinquency, n), 0.0, 1.0)


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


def ysoa_contribution(balance: float, monthly_rate: float, n_rem: int, required_rate: float) -> float:
    """max(0, balance - PV of remaining level payments at the required rate)."""
    if balance <= _EPS or n_rem <= 0 or required_rate <= 0:
        return 0.0
    k = required_rate / 12.0
    if monthly_rate <= 0:
        pmt = balance / n_rem
    else:
        pmt = balance * monthly_rate / (1.0 - (1.0 + monthly_rate) ** (-n_rem))
    pv = pmt * (1.0 - (1.0 + k) ** (-n_rem)) / k
    return max(0.0, balance - pv)


def _reference_mdr_path(
    d_star: np.ndarray, rep: Repline, n: int, scenario: Scenario
) -> np.ndarray:
    """Convert target default dollars to an MDR *rate* path fixed on a
    zero-prepay reference amortization. Applying that rate to the actual
    balance is the original_MDR convention: when the pool prepays faster than
    the reference, realized loss falls below the input cum loss (a gap)."""
    mdr = np.zeros(n)
    p = rep.balance
    r = rep.gross_rate / 12.0
    n_rem = rep.remaining_term
    suppress = scenario.loss.suppress_defaults_near_maturity
    co_lag = scenario.loss.charge_off_lag
    for t in range(n):
        if p <= _EPS or n_rem <= 0:
            break
        d = min(d_star[t], p)
        if suppress and n_rem <= co_lag:
            d = 0.0
        mdr[t] = d / p
        p -= d
        sched = _level_pay_sched(p, r, n_rem)
        p -= sched
        n_rem -= 1
    return mdr


def _evolve_period(
    scenario: Scenario, beg: float, r: float, n_rem: int, d: float, smm_t: float,
    dq_t: float = 0.0,
) -> tuple[float, float, float, float]:
    """One period of the repline pipeline given the default amount d and the
    delinquent share dq_t. Returns (interest, sched, prepay, end_performing)."""
    mdr_t = d / beg if beg > 0 else 0.0
    p = beg - d

    # delinquency: with the "withhold" cash effect the delinquent share pays
    # neither interest nor its scheduled principal this period (the missed
    # sched stays in the balance and re-amortizes; missed interest is lost -
    # no servicer advancing). "none" = measurement only.
    paying = 1.0 - dq_t if scenario.delinquency_cash_effect == "withhold" else 1.0

    # interest accrues on the post-default performing balance only
    interest = p * r * paying

    # scheduled principal (level pay, recomputed on remaining term). The level
    # payment is linear in balance, so the post-default sched equals the
    # beginning-balance sched scaled by (1 - MDR).
    sched_full = _level_pay_sched(beg, r, n_rem) * paying
    sched = sched_full * (p / beg) if beg > 0 else 0.0

    # voluntary prepay - the rate base is (performing - sched), or
    # (beginning - beginning-balance sched) under gross_of_defaults
    # (Intex-style); either way the cap is the remaining performing
    # balance (it can never go negative)
    cap = p - sched
    if scenario.prepay.speed_type == "all_in":
        vol = 1.0 - (1.0 - smm_t) / (1.0 - mdr_t) if mdr_t < 1.0 else 0.0
        vol = min(max(vol, 0.0), 1.0)
    else:
        vol = smm_t
    base = beg - sched_full if scenario.prepay.prepay_base == "gross_of_defaults" else cap
    prepay = min(max(base, 0.0) * vol, cap)

    return interest, sched, prepay, p - sched - prepay


def _waterfill(targets_room: dict[str, float], amount: float) -> dict[str, float]:
    """Split amount pro rata by room, capped at room, overflow redistributed."""
    alloc = {i: 0.0 for i in targets_room}
    remaining = max(amount, 0.0)
    pool_ids = {i for i, room in targets_room.items() if room > _EPS}
    while remaining > _EPS and pool_ids:
        weight = sum(targets_room[i] - alloc[i] for i in pool_ids)
        if weight <= _EPS:
            break
        spread = remaining
        remaining = 0.0
        for i in list(pool_ids):
            room = targets_room[i] - alloc[i]
            share = spread * room / weight
            take = min(share, room)
            alloc[i] += take
            remaining += share - take
            if targets_room[i] - alloc[i] <= _EPS:
                pool_ids.discard(i)
    return alloc


def _pool_default_dollars(
    replines: list[Repline], scenario: Scenario, rep_t: int
) -> dict[str, np.ndarray]:
    """CumLossDefaults with allocation="pool": evolve all replines jointly,
    allocating the pool-level target default dollars each period across
    eligible replines pro rata by beginning performing balance (capped at the
    balance, overflow redistributed). A matured repline's share moves to the
    survivors, so the pool realizes the full target."""
    spec = scenario.loss.defaults
    assert isinstance(spec, CumLossDefaults)
    co_lag = scenario.loss.charge_off_lag
    suppress = scenario.loss.suppress_defaults_near_maturity
    sev = np.clip(expand(scenario.loss.severity, rep_t), 0.0, 1.0)
    total_b0 = sum(rep.balance for rep in replines)
    d_star = _target_dollar_defaults(spec, sev, total_b0, rep_t, co_lag)
    smms = {rep.id: _smm_path(rep, scenario, rep_t) for rep in replines}
    dq = _dq_path(scenario, rep_t)

    def run(vol_on: bool, pool_target_fn) -> tuple[dict[str, np.ndarray], np.ndarray]:
        """Joint evolution; pool_target_fn(t, total_beg) -> pool default $.
        Returns (per-repline default dollars, total beginning balance path)."""
        p = {rep.id: rep.balance for rep in replines}
        n_rem = {rep.id: rep.remaining_term for rep in replines}
        out = {rep.id: np.zeros(rep_t) for rep in replines}
        total_beg = np.zeros(rep_t)
        for t in range(rep_t):
            total_beg[t] = sum(p.values())
            room = {
                rep.id: p[rep.id]
                for rep in replines
                if p[rep.id] > _EPS
                and n_rem[rep.id] > 0
                and not (suppress and n_rem[rep.id] <= co_lag)
            }
            d_alloc = _waterfill(room, pool_target_fn(t, total_beg[t]))
            for rep in replines:
                i = rep.id
                beg = p[i]
                if beg <= _EPS:
                    continue
                d = d_alloc.get(i, 0.0)
                out[i][t] = d
                smm_t = smms[i][t] if vol_on else 0.0
                _, _, _, end = _evolve_period(scenario, beg, rep.gross_rate / 12.0,
                                              max(n_rem[i], 1), d, smm_t,
                                              dq[t] if vol_on else 0.0)
                p[i] = end
                n_rem[i] -= 1
        return out, total_beg

    if spec.method == "original_MDR":
        # rate path fixed on the joint zero-prepay reference, applied to the
        # actual (faster-amortizing) balances -> realized loss can fall short
        _, ref_beg = run(vol_on=False, pool_target_fn=lambda t, total: float(d_star[t]))
        mdr_ref = np.where(ref_beg > _EPS, np.minimum(d_star, ref_beg) / np.maximum(ref_beg, _EPS), 0.0)
        out, _ = run(vol_on=True, pool_target_fn=lambda t, total: float(mdr_ref[t]) * total)
        return out

    out, _ = run(vol_on=True, pool_target_fn=lambda t, total: float(d_star[t]))
    return out


def _project_repline(
    rep: Repline,
    scenario: Scenario,
    rep_t: int,
    ysoc: YsocConfig | None = None,
    default_dollars: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    a = {f: np.zeros(rep_t) for f in REPLINE_FIELDS}
    if rep_t == 0:
        return a

    smm = _smm_path(rep, scenario, rep_t)
    dq = _dq_path(scenario, rep_t)
    sev = np.clip(expand(scenario.loss.severity, rep_t), 0.0, 1.0)
    if default_dollars is not None:  # pool-allocated (already suppression-aware)
        mdr_path = None
        d_star = default_dollars
        suppress = False
    else:
        suppress = scenario.loss.suppress_defaults_near_maturity
        spec = scenario.loss.defaults
        if isinstance(spec, CDRDefaults):
            mdr_path = annual_to_monthly(expand(spec.cdr, rep_t))
            d_star = None
        elif isinstance(spec, CumLossDefaults):
            d_star = _target_dollar_defaults(spec, sev, rep.balance, rep_t, scenario.loss.charge_off_lag)
            mdr_path = _reference_mdr_path(d_star, rep, rep_t, scenario) if spec.method == "original_MDR" else None
        else:
            raise TypeError(f"unknown DefaultSpec {type(spec)}")

    p = rep.balance
    r = rep.gross_rate / 12.0
    n_rem = rep.remaining_term

    for t in range(rep_t):
        beg = p
        a["beg_performing"][t] = beg
        if beg <= _EPS:
            a["end_performing"][t] = beg
            continue
        # balance still outstanding past the scheduled maturity (withheld
        # delinquent sched) is due immediately - a balloon that keeps trying
        n_eff = max(n_rem, 1)

        # 1. defaults (move to pending charge-off; stop performing immediately)
        if mdr_path is not None:
            d = beg * mdr_path[t]  # original_MDR: rate fixed off the reference schedule
        else:
            d = min(d_star[t], beg)  # aggregate_MDR: dollars fit to the cum-loss target
        d = min(d, beg)
        if (suppress and n_rem <= scenario.loss.charge_off_lag) or n_rem <= 0:
            d = 0.0

        # 2.-4. interest, scheduled principal, voluntary prepay
        interest, sched, prepay, p = _evolve_period(scenario, beg, r, n_eff, d, smm[t], dq[t])
        n_rem -= 1

        a["delinquent_balance"][t] = (beg - d) * dq[t]
        a["interest"][t] = interest
        a["defaults"][t] = d
        a["sched_prin"][t] = sched
        a["prepay_prin"][t] = prepay
        a["end_performing"][t] = p

    # 5./6. charge-offs, losses, recoveries via lag shifts (FIFO with fixed
    # lags == index arithmetic). Flows past the horizon are truncated; deals
    # should set num_periods to cover runoff + lags.
    co_lag = scenario.loss.charge_off_lag
    rec_lag = scenario.loss.recovery_lag
    rec_offset = rec_lag if scenario.loss.recovery_lag_from == "default" else co_lag + rec_lag
    for t in range(rep_t):
        td = t - co_lag  # default period feeding this period's charge-off
        if td >= 0:
            a["chargeoffs"][t] = a["defaults"][td]
            a["losses"][t] = a["defaults"][td] * sev[td]  # severity locked at default
        tr = t - rec_offset
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

    # YSOA contributions at end of each period, on the configured balance
    # basis (trust includes the pending-charge-off bucket - Intex convention)
    if ysoc is not None:
        from ..models.common import PoolBalanceBasis

        r = rep.gross_rate / 12.0
        use_trust = ysoc.basis != PoolBalanceBasis.PERFORMING
        for t in range(rep_t):
            bal = a["end_trust"][t] if use_trust else a["end_performing"][t]
            n_after = max(rep.remaining_term - (t + 1), 0)
            a["ysoa_primary"][t] = ysoa_contribution(bal, r, n_after, ysoc.required_rate)
            if ysoc.stepdown_rate is not None:
                a["ysoa_stepdown"][t] = ysoa_contribution(bal, r, n_after, ysoc.stepdown_rate)
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
        out["delinquent_balance"][i] = raw["delinquent_balance"][j]
        out["ysoa_primary"][i] = raw["ysoa_primary"][j]
        out["ysoa_stepdown"][i] = raw["ysoa_stepdown"][j]
    return out


@ASSET_REGISTRY.register("amortizing_loan", config_model=CollateralPool)
class AmortizingLoanModel:
    def project(
        self,
        pool: CollateralPool,
        scenario: Scenario,
        num_periods: int,
        ysoc: YsocConfig | None = None,
    ) -> CollateralCashflows:
        spec = scenario.loss.defaults
        pool_defaults: dict[str, np.ndarray] | None = None
        if isinstance(spec, CumLossDefaults) and spec.allocation == "pool":
            delays = {(r.collection_delay, r.funding_delay) for r in pool.replines}
            if len(delays) > 1:
                raise ValueError(
                    "cum_loss allocation='pool' requires uniform collection/funding "
                    "delays across replines (their timelines must align)"
                )
            d0, f0 = next(iter(delays))
            pool_defaults = _pool_default_dollars(
                pool.replines, scenario, max(0, num_periods - f0 + d0))

        replines: dict[str, dict[str, np.ndarray]] = {}
        ysoa0_primary = 0.0
        ysoa0_stepdown = 0.0
        for rep in pool.replines:
            # repline timeline long enough that its last mapped period reaches
            # the end of the trust timeline
            rep_t = max(0, num_periods - rep.funding_delay + rep.collection_delay)
            raw = _project_repline(
                rep, scenario, rep_t, ysoc,
                default_dollars=pool_defaults[rep.id] if pool_defaults else None)
            replines[rep.id] = _map_to_trust(rep, raw, num_periods)
            if ysoc is not None:
                r = rep.gross_rate / 12.0
                ysoa0_primary += ysoa_contribution(
                    rep.balance, r, rep.remaining_term, ysoc.required_rate)
                if ysoc.stepdown_rate is not None:
                    ysoa0_stepdown += ysoa_contribution(
                        rep.balance, r, rep.remaining_term, ysoc.stepdown_rate)

        agg = {f: np.zeros(num_periods) for f in POOL_FIELDS}
        for arrays in replines.values():
            for f in REPLINE_FIELDS:
                agg[f] += arrays[f]
        agg["cum_net_loss"] = np.cumsum(agg["losses"])
        agg["ysoa"] = agg["ysoa_primary"].copy()

        from ..models.common import PoolBalanceBasis
        basis_beg = agg["beg_performing"] if pool.fee_basis == PoolBalanceBasis.PERFORMING else agg["beg_trust"]
        agg["servicing_fee"] = basis_beg * pool.servicing_fee_rate / 12.0
        ysoc_basis_end = (
            agg["end_performing"]
            if ysoc is not None and ysoc.basis == PoolBalanceBasis.PERFORMING
            else agg["end_trust"]
        )
        agg["adjusted_pool"] = ysoc_basis_end - agg["ysoa"]

        return CollateralCashflows(
            num_periods=num_periods,
            original_balance=pool.original_balance,
            pool=agg,
            replines=replines,
            ysoa0_primary=ysoa0_primary,
            ysoa0_stepdown=ysoa0_stepdown,
        )
