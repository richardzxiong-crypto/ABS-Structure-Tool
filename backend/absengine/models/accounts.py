from typing import Literal

from pydantic import BaseModel, Field

from .common import PoolBalanceBasis


class ReserveAccount(BaseModel):
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


class YsocConfig(BaseModel):
    """Yield supplement overcollateralization.

    YSOA_t = sum over replines with gross_rate < required rate of
    max(0, balance_t - PV(remaining level payments @ required rate)),
    recomputed each period off the actual (post-default, post-prepay)
    performing balances. The "adjusted" pool basis = basis balance - YSOA_t.

    - initial_amount: hard-coded closing YSOA (e.g. the prospectus number,
      computed loan-by-loan); period 1's adjusted balance = beginning basis
      balance - initial_amount. All later periods are dynamic.
    - stepdown_rate kicks in once `stepdown_when_class_zero` is fully paid
      (checked on its beginning-of-period balance).
    """

    required_rate: float = Field(ge=0)
    stepdown_rate: float | None = Field(default=None, ge=0)
    stepdown_when_class_zero: str | None = None
    initial_amount: float | None = None
    method: Literal["dynamic"] = "dynamic"
    basis: PoolBalanceBasis = Field(
        default=PoolBalanceBasis.TRUST,
        description="which pool balance the YSOA is netted against",
    )
