"""Trigger config models. Evaluation lands in Phase 2; the models exist now so
deal JSON schema doesn't churn."""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from .common import PoolBalanceBasis

Operator = Literal["<", "<=", ">", ">="]


class TriggerBase(BaseModel):
    name: str
    curable: bool = True


class CumNetLossTrigger(TriggerBase):
    type: Literal["cum_net_loss"] = "cum_net_loss"
    operator: Operator = "<="
    schedule: list[tuple[int, float]] = Field(
        default_factory=list, description="(period, threshold as % of original) steps"
    )


class DelinquencyTrigger(TriggerBase):
    type: Literal["delinquency"] = "delinquency"
    operator: Operator = "<="
    threshold: float = 0.0


class PoolFactorTrigger(TriggerBase):
    type: Literal["pool_factor"] = "pool_factor"
    operator: Operator = ">"
    threshold: float = 0.0
    basis: PoolBalanceBasis = PoolBalanceBasis.TRUST


class OCTestTrigger(TriggerBase):
    type: Literal["oc_test"] = "oc_test"
    operator: Operator = ">="
    threshold: float = 0.0
    basis: PoolBalanceBasis = PoolBalanceBasis.TRUST


class ICTestTrigger(TriggerBase):
    type: Literal["ic_test"] = "ic_test"
    operator: Operator = ">="
    threshold: float = 0.0


AnyTrigger = Annotated[
    Union[CumNetLossTrigger, DelinquencyTrigger, PoolFactorTrigger, OCTestTrigger, ICTestTrigger],
    Field(discriminator="type"),
]
