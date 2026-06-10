from __future__ import annotations

import numpy as np
from scipy.optimize import brentq


def wal_years(prin_paid: np.ndarray) -> float | None:
    """Weighted-average life in years of principal actually received
    (monthly periods, payment at end of period t)."""
    total = prin_paid.sum()
    if total <= 0:
        return None
    t = np.arange(1, len(prin_paid) + 1)
    return float((prin_paid * t).sum() / total / 12.0)


def yield_from_price(price: float, original_balance: float, cashflows: np.ndarray) -> float | None:
    """Annual yield (monthly-compounded nominal) solving
    sum(cf_t / (1+y/12)^t) = price/100 * original_balance."""
    cost = price / 100.0 * original_balance
    if cost <= 0 or cashflows.sum() <= 0:
        return None
    t = np.arange(1, len(cashflows) + 1)

    def npv(monthly: float) -> float:
        return float((cashflows / (1.0 + monthly) ** t).sum() - cost)

    try:
        lo, hi = -0.08, 1.0
        if npv(lo) * npv(hi) > 0:
            return None
        monthly = brentq(npv, lo, hi, xtol=1e-12)
    except ValueError:
        return None
    return float(monthly * 12.0)


def principal_window(prin_paid: np.ndarray) -> tuple[int, int] | None:
    """(first, last) 1-based periods with principal received."""
    idx = np.nonzero(prin_paid > 1e-9)[0]
    if len(idx) == 0:
        return None
    return int(idx[0] + 1), int(idx[-1] + 1)
