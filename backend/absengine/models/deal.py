from datetime import date
from typing import Literal

from dateutil.relativedelta import relativedelta
from pydantic import BaseModel, Field, model_validator

from .accounts import ExternalSource, FeeSpec, ReserveAccount, YsocConfig
from .collateral import CollateralPool
from .scenario import Scenario
from .structure import CapitalStructure, tree_class_ids, tree_group_names
from .triggers import AnyTrigger
from .waterfall import (
    FundReserveStep,
    PayFeesStep,
    PayInterestShortfallStep,
    PayInterestStep,
    PayPrincipalStep,
    RetireBondsStep,
    WaterfallSpec,
)

_BUILTIN_SOURCES = {"interest_collections", "principal_collections", "total_collections"}


class DealDates(BaseModel):
    """Payment-date calendar. Bond accrual period t is
    [payment_date(t-1), payment_date(t)], with payment_date(0) = closing_date -
    so period 1 is typically short. Without DealDates every accrual is a flat
    1/12 (30/360 monthly) and ACT day counts are rejected.

    business_day_adjust="following" rolls payment dates to the next US
    business day for ACT day-count accrual (money-market convention);
    30/360 classes always accrue on the unadjusted dates.
    """

    closing_date: date
    first_payment_date: date
    business_day_adjust: Literal["none", "following"] = "none"

    def payment_date(self, period: int) -> date:
        """period 0 = closing date; period t = first payment + (t-1) months."""
        if period <= 0:
            return self.closing_date
        return self.first_payment_date + relativedelta(months=period - 1)

    def adjusted_payment_date(self, period: int) -> date:
        from ..dates.calendar import adjust_following

        d = self.payment_date(period)
        if period > 0 and self.business_day_adjust == "following":
            return adjust_following(d)
        return d


class Deal(BaseModel):
    schema_version: int = 1
    id: str
    name: str = ""
    description: str = ""
    num_periods: int = Field(gt=0)
    dates: DealDates | None = None
    collateral: CollateralPool
    structure: CapitalStructure
    fees: list[FeeSpec] = Field(default_factory=list)
    reserve_accounts: list[ReserveAccount] = Field(default_factory=list)
    ysoc: YsocConfig | None = None
    external_sources: list[ExternalSource] = Field(default_factory=list)
    waterfall: WaterfallSpec
    triggers: list[AnyTrigger] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=lambda: [Scenario()])

    @model_validator(mode="after")
    def _cross_validate(self):
        class_ids = {c.id for c in self.structure.classes}
        group_names = set(tree_group_names(self.structure.allocation_tree))
        fee_names = {f.name for f in self.fees}
        reserve_names = {r.name for r in self.reserve_accounts}
        trigger_names = {t.name for t in self.triggers}
        valid_targets = class_ids | group_names
        externals = {x.name: x for x in self.external_sources}
        if len(externals) != len(self.external_sources):
            raise ValueError("duplicate external source names")
        for x in self.external_sources:
            if x.kind == "swap" and x.notional_class is not None and x.notional_class not in class_ids:
                raise ValueError(
                    f"external source {x.name!r}: unknown notional class {x.notional_class!r}"
                )
        swap_fees = {f"swap:{name}" for name, x in externals.items() if x.kind == "swap"}

        step_ids: set[str] = set()
        for wf in self.waterfall.waterfalls:
            for step in wf.steps:
                if step.id in step_ids:
                    raise ValueError(f"duplicate waterfall step id {step.id!r}")
                step_ids.add(step.id)

                src = step.source
                if src not in _BUILTIN_SOURCES:
                    if src.startswith("reserve:"):
                        if src.split(":", 1)[1] not in reserve_names:
                            raise ValueError(f"step {step.id!r}: unknown reserve source {src!r}")
                    elif src.startswith("external:"):
                        if src.split(":", 1)[1] not in externals:
                            raise ValueError(f"step {step.id!r}: unknown external source {src!r}")
                    else:
                        raise ValueError(f"step {step.id!r}: unknown source {src!r}")
                if self.waterfall.mode == "combined" and src in (
                    "interest_collections",
                    "principal_collections",
                ):
                    raise ValueError(
                        f"step {step.id!r}: split-bucket source {src!r} in combined-mode waterfall"
                    )
                if self.waterfall.mode == "split" and src == "total_collections":
                    raise ValueError(
                        f"step {step.id!r}: total_collections source in split-mode waterfall"
                    )

                if isinstance(step, PayFeesStep):
                    unknown = set(step.fees) - fee_names - swap_fees
                    if unknown:
                        raise ValueError(
                            f"step {step.id!r}: unknown fees {sorted(unknown)} "
                            f"(fees are FeeSpec names or swap:<external source>)"
                        )
                if isinstance(step, (PayInterestStep, PayInterestShortfallStep, PayPrincipalStep)):
                    unknown = set(step.targets) - valid_targets
                    if unknown:
                        raise ValueError(f"step {step.id!r}: unknown targets {sorted(unknown)}")
                if isinstance(step, FundReserveStep) and step.account not in reserve_names:
                    raise ValueError(f"step {step.id!r}: unknown reserve account {step.account!r}")
                if isinstance(step, RetireBondsStep) and step.reserve not in reserve_names:
                    raise ValueError(f"step {step.id!r}: unknown reserve account {step.reserve!r}")
                cond = step.condition
                if cond is not None and cond.trigger not in trigger_names:
                    raise ValueError(f"step {step.id!r}: unknown trigger {cond.trigger!r}")

        if self.ysoc is not None and self.ysoc.stepdown_when_class_zero is not None:
            if self.ysoc.stepdown_when_class_zero not in class_ids:
                raise ValueError(
                    f"ysoc.stepdown_when_class_zero: unknown class "
                    f"{self.ysoc.stepdown_when_class_zero!r}"
                )
        return self

    def scenario_by_name(self, name: str) -> Scenario:
        for s in self.scenarios:
            if s.name == name:
                return s
        raise KeyError(f"scenario {name!r} not found in deal {self.id!r}")


def tree_seniority_order(deal: Deal) -> list[str]:
    """Depth-first leaf order of the allocation tree = seniority for writedowns."""
    return tree_class_ids(deal.structure.allocation_tree)
