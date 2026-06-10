"""Expand RateSpec configs to per-period numpy vectors + rate conversions."""

from __future__ import annotations

import numpy as np

from ..models.scenario import RampRate, ScalarRate, VectorRate


def expand(spec, num_periods: int) -> np.ndarray:
    """Per-period vector of length num_periods, indexed by period-1."""
    if isinstance(spec, ScalarRate):
        return np.full(num_periods, float(spec.value))
    if isinstance(spec, VectorRate):
        vals = np.asarray(spec.values, dtype=float)
        if len(vals) >= num_periods:
            return vals[:num_periods].copy()
        return np.concatenate([vals, np.full(num_periods - len(vals), vals[-1])])
    if isinstance(spec, RampRate):
        ramp = np.linspace(spec.start, spec.end, spec.periods)
        if spec.periods >= num_periods:
            return ramp[:num_periods].copy()
        return np.concatenate([ramp, np.full(num_periods - spec.periods, float(spec.end))])
    raise TypeError(f"unknown RateSpec: {type(spec)}")


def annual_to_monthly(annual: np.ndarray) -> np.ndarray:
    """CPR->SMM / CDR->MDR survival conversion: 1-(1-r)^(1/12)."""
    annual = np.clip(annual, 0.0, 1.0)
    return 1.0 - (1.0 - annual) ** (1.0 / 12.0)
