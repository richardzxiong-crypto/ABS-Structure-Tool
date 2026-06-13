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
    speed_unit: Literal["cpr", "abs"] = Field(
        default="cpr",
        description="cpr: annual rate, survival-converted to SMM; abs: Absolute "
        "Prepayment Speed - monthly prepay as a fraction of original balance, "
        "converted per repline as SMM_m = ABS/(1 - ABS*(m-1)) with m = loan age "
        "in months, capped at 1",
    )
    prepay_base: Literal["net_of_defaults", "gross_of_defaults"] = Field(
        default="net_of_defaults",
        description="net_of_defaults: SMM applies to (performing - sched), so "
        "current-period defaults never prepay; gross_of_defaults (Intex-style): "
        "SMM applies to (beginning balance - sched), capped so the performing "
        "balance cannot go negative",
    )


class CDRDefaults(BaseModel):
    """Per-period annualized default rate applied to beginning performing balance."""

    type: Literal["cdr"] = "cdr"
    cdr: RateSpec = Field(default_factory=ScalarRate)


class CumLossDefaults(BaseModel):
    """Cumulative net loss (% of original balance) distributed by a timing curve.

    method:
    - aggregate_MDR: per-period default dollars are fit directly to the
      cum-loss target (cum_net_loss x timing x original balance, capped at
      the available balance), so realized cumulative loss equals the input
      regardless of prepay speed - the loss is "fit in".
    - original_MDR: the timing curve is converted to an MDR *rate* path fixed
      on a zero-prepay reference amortization, then applied to the actual
      balance - faster actual runoff leaves realized loss below the input
      (a small gap).
    """

    type: Literal["cum_loss"] = "cum_loss"
    cum_net_loss: float = Field(ge=0, description="decimal fraction of original balance")
    timing: list[float] = Field(min_length=1, description="loss distribution; normalized to sum to 1")
    timing_unit: Literal["period", "annual"] = Field(
        default="period",
        description="annual: each timing entry is a year's share, spread evenly "
        "across its months",
    )
    timing_applies_to: Literal["defaults", "losses"] = Field(
        default="defaults",
        description="losses (Intex-style): the timing curve positions loss "
        "recognition (charge-offs); defaults occur charge_off_lag earlier. "
        "Annual buckets spread evenly over each year's feasible charge-off "
        "months (the first charge_off_lag months of year 1 carry no mass)",
    )
    method: Literal["aggregate_MDR", "original_MDR"] = "aggregate_MDR"
    allocation: Literal["repline", "pool"] = Field(
        default="repline",
        description="repline: each repline carries its own share of the target "
        "dollars (a matured repline's share is lost); pool (Intex-style): the "
        "pool-level target dollars are allocated each period across surviving "
        "replines pro rata by performing balance, so the pool hits the target "
        "as long as any balance remains (aggregate_MDR). Pool allocation "
        "requires uniform collection/funding delays across replines.",
    )

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
    recovery_lag: int = Field(default=0, ge=0, description="periods to recovery cash")
    recovery_lag_from: Literal["charge_off", "default"] = Field(
        default="charge_off",
        description="reference point for recovery_lag: charge_off (market default "
        "here) or default (Intex-style; recovery may arrive with the charge-off)",
    )
    suppress_defaults_near_maturity: bool = Field(
        default=False,
        description="Intex-style: no new defaults once a repline's remaining "
        "scheduled term <= charge_off_lag (a default must be able to charge "
        "off before the loan's scheduled payoff)",
    )


class Scenario(BaseModel):
    name: str = "base"
    prepay: PrepayAssumption = Field(default_factory=PrepayAssumption)
    loss: LossAssumption = Field(default_factory=LossAssumption)
    recoveries_to: Literal["principal", "interest"] = "principal"
    index_curves: dict[str, RateSpec] = Field(default_factory=dict, description="Phase 2: floating-rate indices")
