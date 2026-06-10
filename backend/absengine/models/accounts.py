from typing import Literal

from pydantic import BaseModel, Field

from .common import PoolBalanceBasis


class ReserveAccount(BaseModel):  # Phase 2
    name: str
    target_kind: Literal["pct_current_pool", "pct_original_pool", "fixed"] = "fixed"
    target_value: float = 0.0
    floor: float = 0.0
    initial_balance: float = 0.0


class FeeSpec(BaseModel):
    """A deal-level fee paid through the waterfall via a pay_fees step.

    due per period = rate/12 * beginning basis balance + fixed.
    (The pool's servicing_fee_rate is separate: netted off the top of
    interest collections before the waterfall.)
    """

    name: str
    rate: float = Field(default=0.0, ge=0, description="annual, on the basis balance")
    fixed: float = Field(default=0.0, ge=0, description="flat amount per period")
    basis: PoolBalanceBasis = PoolBalanceBasis.TRUST


class YsocConfig(BaseModel):  # Phase 2
    required_rate: float = Field(ge=0)
    method: Literal["dynamic", "static_schedule"] = "dynamic"
    static_scaling: Literal["none", "pool_factor"] = "none"
    basis: PoolBalanceBasis = PoolBalanceBasis.TRUST
