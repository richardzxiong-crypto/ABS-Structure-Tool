"""Waterfall step configs. Every step answers three questions, matching how
indentures read: SOURCE (where the money comes from), ACTION (what it pays),
TARGETS (which classes/groups, in priority order)."""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from .common import PoolBalanceBasis

# Valid source forms: "interest_collections" | "principal_collections" |
# "total_collections" | "reserve:<name>" (Phase 2) | "external:<name>" (Phase 2)
SourceRef = str
TargetRef = str  # bond class id, or group name from the allocation tree


class StepCondition(BaseModel):  # Phase 2
    trigger: str
    when: Literal["pass", "fail"] = "fail"


class WaterfallStepBase(BaseModel):
    id: str
    label: str = ""
    source: SourceRef
    condition: StepCondition | None = None  # Phase 2


class PayFeesStep(WaterfallStepBase):
    type: Literal["pay_fees"] = "pay_fees"
    fees: list[str] = Field(min_length=1, description="FeeSpec names, paid in order")


class PayInterestStep(WaterfallStepBase):
    type: Literal["pay_interest"] = "pay_interest"
    targets: list[TargetRef] = Field(min_length=1)


class PayInterestShortfallStep(WaterfallStepBase):
    type: Literal["pay_interest_shortfall"] = "pay_interest_shortfall"
    targets: list[TargetRef] = Field(min_length=1)


class TargetOCSpec(BaseModel):
    """target OC = max(main amount, floor amount).

    main:  kind/value (e.g. pct_current_pool 0.0675 on the step's pool basis)
    floor: floor_kind/floor_value (e.g. pct_original_pool 0.01 - typical
           "greater of x% of current and y% of initial" language). The
           original-pool floor uses the period-1 beginning basis balance,
           so on the adjusted basis it is net of the initial YSOA.
    """

    kind: Literal["fixed", "pct_current_pool", "pct_original_pool"] = "fixed"
    value: float = 0.0
    floor_kind: Literal["none", "fixed", "pct_original_pool"] = "none"
    floor_value: float = 0.0


class PayPrincipalStep(WaterfallStepBase):
    """amount_rule:
    - collections:   distribute the period's principal collections
    - regular_pda:   max(0, total bond balance - (pool balance - target_OC))
    - priority_pda:  max(0, sum of target-class balances - pool balance);
                     cumulative tiers (First/Second/Third Allocations) fall out
                     of consecutive steps with growing target sets, since
                     balances update between steps
    - turbo:         all remaining cash in the source bucket
    """

    type: Literal["pay_principal"] = "pay_principal"
    targets: list[TargetRef] = Field(min_length=1)
    amount_rule: Literal["collections", "regular_pda", "priority_pda", "turbo"] = "collections"
    target_oc: TargetOCSpec = Field(default_factory=TargetOCSpec)
    pool_basis: PoolBalanceBasis = PoolBalanceBasis.TRUST


class FundReserveStep(WaterfallStepBase):
    type: Literal["fund_reserve"] = "fund_reserve"
    account: str


class RetireBondsStep(WaterfallStepBase):
    """Optional "reserve to retire bonds": if source bucket + reserve balance
    covers the total remaining bond balance, retire all classes (in allocation
    tree seniority order), drawing the source first, then the reserve.
    Otherwise a no-op. Place after all interest/fee clauses."""

    type: Literal["retire_bonds"] = "retire_bonds"
    reserve: str
    release_reserve_remainder: bool = Field(
        default=True,
        description="once the notes are retired the reserve account closes: "
        "any remaining balance is released into the source bucket (flowing to "
        "the residual through the remaining steps)",
    )


class ReleaseResidualStep(WaterfallStepBase):
    type: Literal["release_residual"] = "release_residual"
    to: str = "residual"


AnyStep = Annotated[
    Union[
        PayFeesStep,
        PayInterestStep,
        PayInterestShortfallStep,
        PayPrincipalStep,
        FundReserveStep,
        RetireBondsStep,
        ReleaseResidualStep,
    ],
    Field(discriminator="type"),
]


class Waterfall(BaseModel):
    name: str
    steps: list[AnyStep] = Field(default_factory=list)


class WaterfallSpec(BaseModel):
    mode: Literal["split", "combined"] = Field(
        default="split",
        description="split: interest_collections/principal_collections buckets; "
        "combined: a single total_collections bucket",
    )
    waterfalls: list[Waterfall] = Field(min_length=1)
