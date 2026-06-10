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
    kind: Literal["fixed", "pct_current_pool", "pct_original_pool"] = "fixed"
    value: float = 0.0


class PayPrincipalStep(WaterfallStepBase):
    """amount_rule:
    - collections:   distribute the period's principal collections
    - regular_pda:   max(0, total bond balance - (pool balance - target_OC))
    - priority_pda:  max(0, sum of target-class balances - pool balance)  (Phase 2)
    - turbo:         all remaining cash in the source bucket               (Phase 2)
    """

    type: Literal["pay_principal"] = "pay_principal"
    targets: list[TargetRef] = Field(min_length=1)
    amount_rule: Literal["collections", "regular_pda", "priority_pda", "turbo"] = "collections"
    target_oc: TargetOCSpec = Field(default_factory=TargetOCSpec)
    pool_basis: PoolBalanceBasis = PoolBalanceBasis.TRUST


class FundReserveStep(WaterfallStepBase):  # Phase 2
    type: Literal["fund_reserve"] = "fund_reserve"
    account: str


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
