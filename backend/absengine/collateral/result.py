from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..models.common import PoolBalanceBasis

# Per-repline fields (on the trust timeline after delay mapping).
# ysoa_primary / ysoa_stepdown are end-of-period YSOA contributions at the two
# strike rates (zero unless the deal has a YsocConfig); the waterfall selects
# between them per period (stepdown state is bond-dependent).
REPLINE_FIELDS = [
    "beg_performing", "end_performing",
    "beg_trust", "end_trust",
    "pending_chargeoff",
    "defaults", "chargeoffs", "losses", "recoveries",
    "interest", "sched_prin", "prepay_prin",
    "ysoa_primary", "ysoa_stepdown",
]
# Pool aggregate adds servicing_fee, cum_net_loss, ysoa, adjusted_pool.
POOL_FIELDS = REPLINE_FIELDS + ["servicing_fee", "cum_net_loss", "ysoa", "adjusted_pool"]


@dataclass
class CollateralCashflows:
    num_periods: int
    original_balance: float
    pool: dict[str, np.ndarray]
    replines: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)
    # YSOA at the closing date (pre-period-1 state), both strikes
    ysoa0_primary: float = 0.0
    ysoa0_stepdown: float = 0.0

    def basis_beg(self, basis: PoolBalanceBasis) -> np.ndarray:
        if basis == PoolBalanceBasis.PERFORMING:
            return self.pool["beg_performing"]
        if basis == PoolBalanceBasis.ADJUSTED:
            return self.pool["beg_trust"] - self.pool["ysoa"]
        return self.pool["beg_trust"]

    def basis_end(self, basis: PoolBalanceBasis) -> np.ndarray:
        if basis == PoolBalanceBasis.PERFORMING:
            return self.pool["end_performing"]
        if basis == PoolBalanceBasis.ADJUSTED:
            return self.pool["adjusted_pool"]
        return self.pool["end_trust"]

    def interest_collections(self) -> np.ndarray:
        """Gross interest net of the top-of-stack servicing fee (floored at 0)."""
        return np.maximum(self.pool["interest"] - self.pool["servicing_fee"], 0.0)

    def principal_collections(self, recoveries_to: str = "principal") -> np.ndarray:
        prin = self.pool["sched_prin"] + self.pool["prepay_prin"]
        if recoveries_to == "principal":
            prin = prin + self.pool["recoveries"]
        return prin

    def to_frame(self) -> pd.DataFrame:
        df = pd.DataFrame({k: self.pool[k] for k in POOL_FIELDS})
        df.insert(0, "period", np.arange(1, self.num_periods + 1))
        return df
