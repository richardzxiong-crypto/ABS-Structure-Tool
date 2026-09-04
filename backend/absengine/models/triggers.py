"""Trigger config models. The interpreter evaluates them at determination and
owns the cure/latch state machine; handlers live in absengine.triggers."""

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
    """measured = delinquent balance / beginning basis balance, averaged over
    the last `lookback` collection periods (fewer at the start of the deal -
    the usual "average of the three preceding collection periods" language
    is lookback=3)."""

    type: Literal["delinquency"] = "delinquency"
    operator: Operator = "<="
    threshold: float = 0.0
    basis: PoolBalanceBasis = PoolBalanceBasis.TRUST
    lookback: int = Field(default=1, ge=1)


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
