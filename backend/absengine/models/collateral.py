from pydantic import BaseModel, Field

from .common import AmortType, PoolBalanceBasis


class Repline(BaseModel):
    """A representative line: a homogeneous slice of the pool modeled as one loan.

    Timing fields (both in whole periods, default 0):
    - collection_delay d: repline periods 1..1+d collections are combined into
      trust period 1; thereafter repline period k+d flows to trust period k.
    - funding_delay f: repline cash/balances show up f trust periods late
      (prefunding / subsequent purchases) - trust periods 1..f see nothing.
    """

    id: str
    balance: float = Field(gt=0)
    gross_rate: float = Field(ge=0, description="annual gross coupon, decimal (0.08 = 8%)")
    original_term: int = Field(gt=0)
    remaining_term: int = Field(gt=0)
    amort_type: AmortType = AmortType.LEVEL_PAY
    collection_delay: int = Field(default=0, ge=0)
    funding_delay: int = Field(default=0, ge=0)


class CollateralPool(BaseModel):
    asset_class: str = "amortizing_loan"
    replines: list[Repline] = Field(min_length=1)
    servicing_fee_rate: float = Field(
        default=0.0, ge=0,
        description="annual rate netted off the top of interest collections",
    )
    fee_basis: PoolBalanceBasis = Field(
        default=PoolBalanceBasis.TRUST,
        description="balance basis for the servicing fee and pool factor",
    )

    @property
    def original_balance(self) -> float:
        return sum(r.balance for r in self.replines)
