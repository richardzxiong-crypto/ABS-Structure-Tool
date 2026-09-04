from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


def _df_to_columns(df: pd.DataFrame) -> dict[str, list]:
    """Column-oriented lists with NaN -> None (JSON has no NaN)."""
    return {
        col: [None if isinstance(v, float) and np.isnan(v) else v for v in df[col].tolist()]
        for col in df.columns
    }


@dataclass
class DealRunResult:
    deal_id: str
    scenario_name: str
    num_periods: int
    collateral: pd.DataFrame  # pool aggregate, one row per period
    bonds: pd.DataFrame  # one row per (period, class)
    flows: pd.DataFrame  # FlowRecord audit log
    residual: np.ndarray
    fees_paid: np.ndarray
    retained: np.ndarray
    seeded: np.ndarray
    accounts: pd.DataFrame | None = None  # reserve balances, one row per (period, account)
    triggers: pd.DataFrame | None = None  # one row per (period, trigger)
    externals: pd.DataFrame | None = None  # one row per (period, external source)
    metrics: dict = field(default_factory=dict)

    def to_json_dict(self) -> dict:
        """Column-oriented arrays at the API boundary."""
        return {
            "deal_id": self.deal_id,
            "scenario_name": self.scenario_name,
            "num_periods": self.num_periods,
            "collateral": _df_to_columns(self.collateral),
            "bonds": _df_to_columns(self.bonds),
            "flows": _df_to_columns(self.flows),
            "residual": self.residual.tolist(),
            "fees_paid": self.fees_paid.tolist(),
            "retained": self.retained.tolist(),
            "accounts": _df_to_columns(self.accounts) if self.accounts is not None else {},
            "triggers": _df_to_columns(self.triggers) if self.triggers is not None else {},
            "externals": _df_to_columns(self.externals) if self.externals is not None else {},
            "metrics": self.metrics,
        }
