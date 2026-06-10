from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------- RateSpec

class ScalarRate(BaseModel):
    type: Literal["scalar"] = "scalar"
    value: float = 0.0


class VectorRate(BaseModel):
    """Explicit per-period values; the last value extends to the horizon."""

    type: Literal["vector"] = "vector"
    values: list[float] = Field(min_length=1)


class RampRate(BaseModel):
    """Linear from `start` to `end` over `periods` periods, then `end` thereafter."""

    type: Literal["ramp"] = "ramp"
    start: float
    end: float
    periods: int = Field(gt=0)


RateSpec = Annotated[Union[ScalarRate, VectorRate, RampRate], Field(discriminator="type")]


# ---------------------------------------------------------------- prepay / loss

class PrepayAssumption(BaseModel):
    speed: RateSpec = Field(default_factory=ScalarRate, description="annual CPR, decimal")
    speed_type: Literal["voluntary", "all_in"] = Field(
        default="voluntary",
        description="all_in: speed includes defaults; voluntary SMM backed out as "
        "1-(1-allin_SMM)/(1-MDR), floored at 0",
    )


class CDRDefaults(BaseModel):
    """Per-period annualized default rate applied to beginning performing balance."""

    type: Literal["cdr"] = "cdr"
    cdr: RateSpec = Field(default_factory=ScalarRate)


class CumLossDefaults(BaseModel):
    """Cumulative net loss (% of original balance) distributed by a timing curve.

    method:
    - aggregate_MDR: the timing curve is converted to an MDR path on a
      zero-prepay reference amortization, then that *rate* path is applied to
      the actual (aggregate) balance - faster actual runoff lowers realized loss.
    - original_MDR: per-period default dollars are fixed off the original
      balance (timing curve taken literally), capped at available balance.
    """

    type: Literal["cum_loss"] = "cum_loss"
    cum_net_loss: float = Field(ge=0, description="decimal fraction of original balance")
    timing: list[float] = Field(min_length=1, description="per-period loss distribution; normalized to sum to 1")
    method: Literal["aggregate_MDR", "original_MDR"] = "aggregate_MDR"

    @model_validator(mode="after")
    def _check_timing(self):
        if any(x < 0 for x in self.timing):
            raise ValueError("timing entries must be >= 0")
        if sum(self.timing) <= 0 and self.cum_net_loss > 0:
            raise ValueError("timing must have positive mass")
        return self


DefaultSpec = Annotated[Union[CDRDefaults, CumLossDefaults], Field(discriminator="type")]


class LossAssumption(BaseModel):
    defaults: DefaultSpec = Field(default_factory=CDRDefaults)
    severity: RateSpec = Field(
        default_factory=lambda: ScalarRate(value=1.0),
        description="loss severity on defaulted balance, locked at default period",
    )
    charge_off_lag: int = Field(default=0, ge=0, description="periods from default to charge-off")
    recovery_lag: int = Field(default=0, ge=0, description="periods from charge-off to recovery cash")


class Scenario(BaseModel):
    name: str = "base"
    prepay: PrepayAssumption = Field(default_factory=PrepayAssumption)
    loss: LossAssumption = Field(default_factory=LossAssumption)
    recoveries_to: Literal["principal", "interest"] = "principal"
    index_curves: dict[str, RateSpec] = Field(default_factory=dict, description="Phase 2: floating-rate indices")
