from pydantic import BaseModel, Field, model_validator

from .accounts import FeeSpec, ReserveAccount, YsocConfig
from .collateral import CollateralPool
from .scenario import Scenario
from .structure import CapitalStructure, tree_class_ids, tree_group_names
from .triggers import AnyTrigger
from .waterfall import (
    PayFeesStep,
    PayInterestShortfallStep,
    PayInterestStep,
    PayPrincipalStep,
    WaterfallSpec,
)

_BUILTIN_SOURCES = {"interest_collections", "principal_collections", "total_collections"}


class Deal(BaseModel):
    schema_version: int = 1
    id: str
    name: str = ""
    description: str = ""
    num_periods: int = Field(gt=0)
    collateral: CollateralPool
    structure: CapitalStructure
    fees: list[FeeSpec] = Field(default_factory=list)
    reserve_accounts: list[ReserveAccount] = Field(default_factory=list)
    ysoc: YsocConfig | None = None
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
                    elif not src.startswith("external:"):
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
                    unknown = set(step.fees) - fee_names
                    if unknown:
                        raise ValueError(f"step {step.id!r}: unknown fees {sorted(unknown)}")
                if isinstance(step, (PayInterestStep, PayInterestShortfallStep, PayPrincipalStep)):
                    unknown = set(step.targets) - valid_targets
                    if unknown:
                        raise ValueError(f"step {step.id!r}: unknown targets {sorted(unknown)}")
                cond = step.condition
                if cond is not None and cond.trigger not in trigger_names:
                    raise ValueError(f"step {step.id!r}: unknown trigger {cond.trigger!r}")
        return self

    def scenario_by_name(self, name: str) -> Scenario:
        for s in self.scenarios:
            if s.name == name:
                return s
        raise KeyError(f"scenario {name!r} not found in deal {self.id!r}")


def tree_seniority_order(deal: Deal) -> list[str]:
    """Depth-first leaf order of the allocation tree = seniority for writedowns."""
    return tree_class_ids(deal.structure.allocation_tree)
