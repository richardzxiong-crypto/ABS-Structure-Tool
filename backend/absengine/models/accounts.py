from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .common import DayCount, PoolBalanceBasis
from .scenario import RateSpec, ScalarRate


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


class ExternalSource(BaseModel):
    """Cash from outside the collateral pool - a swap/cap receipt, a
    prefunding release, a sponsor top-up. Each period in
    [start_period, end_period] the amount is seeded into the waterfall bucket
    `external:<name>`; steps draw from it like any other source. Whatever is
    left at period end is retained (add a `release_residual` step sourced
    from the bucket to sweep it to the residual).

    kind="amount": `amount` dollars per period (a RateSpec; a scenario can
      override it through `scenario.external_amounts[name]`).
    kind="swap": an interest-rate swap where the trust pays `fixed_rate` and
      receives `index + spread` on a notional that tracks `notional_class`'s
      beginning balance (or `notional_schedule`, per period, last value
      extended). net_t = notional_t x (index_t + spread - fixed_rate) x
      accrual (the class-style day-count fraction; 1/12 without deal dates).
      A positive net is the receipt seeded into the bucket; a negative net is
      the payment the trust owes, payable inside the waterfall by listing
      `swap:<name>` in a pay_fees step.
    """

    name: str
    kind: Literal["amount", "swap"] = "amount"
    amount: RateSpec = Field(default_factory=ScalarRate, description="dollars per period")
    start_period: int = Field(default=1, ge=1)
    end_period: int | None = Field(default=None, ge=1)
    # swap leg
    notional_class: str | None = None
    notional_schedule: list[float] = Field(default_factory=list)
    fixed_rate: float = Field(default=0.0, ge=0)
    index: str = ""
    spread: float = 0.0
    day_count: DayCount = DayCount.THIRTY_360

    @model_validator(mode="after")
    def _check(self):
        if self.end_period is not None and self.end_period < self.start_period:
            raise ValueError(f"external source {self.name!r}: end_period before start_period")
        if self.kind == "swap":
            if not self.index:
                raise ValueError(f"external source {self.name!r}: swap needs an index name")
            if self.notional_class is None and not self.notional_schedule:
                raise ValueError(
                    f"external source {self.name!r}: swap needs notional_class or notional_schedule"
                )
        return self
