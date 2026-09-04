from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator

from .common import DayCount, PoolBalanceBasis


# ---------------------------------------------------------------- coupons

class FixedCoupon(BaseModel):
    type: Literal["fixed"] = "fixed"
    rate: float = Field(ge=0, description="annual coupon, decimal")


class FloatingCoupon(BaseModel):  # Phase 2
    type: Literal["floating"] = "floating"
    index: str
    margin: float = 0.0
    cap: float | None = None
    floor: float | None = None


CouponSpec = Annotated[Union[FixedCoupon, FloatingCoupon], Field(discriminator="type")]


class BondClass(BaseModel):
    id: str
    name: str = ""
    balance: float = Field(ge=0)
    coupon: CouponSpec
    day_count: DayCount = DayCount.THIRTY_360
    price: float | None = Field(default=None, description="per 100; enables yield metric")


# ---------------------------------------------------------------- allocation tree

class TargetBalanceSpec(BaseModel):
    """Target (scheduled) balance for a `target_balance` group.

    Principal steps pay the group only down to its target for the period:
    the group's capacity is max(0, current group balance - target_t); cash
    beyond that flows to the next target listed on the step (the companion
    classes). Inside the group, cash goes sequentially (child order) or pro
    rata per `distribution`. Interest/shortfall steps ignore the target (the
    group behaves sequentially for them).

    - schedule: per-period aggregate target balances (period 1 first); beyond
      the last entry the target is 0 (the scheduled classes pay off);
    - pct_of_pool: target_t = pct x the period's ending pool balance on
      `pool_basis`.
    """

    kind: Literal["schedule", "pct_of_pool"] = "schedule"
    schedule: list[float] = Field(default_factory=list, description="per-period target balances")
    pct: float = Field(default=0.0, ge=0)
    pool_basis: PoolBalanceBasis = PoolBalanceBasis.TRUST
    distribution: Literal["sequential", "pro_rata"] = "sequential"

    def target_for(self, period: int, pool_end: float) -> float:
        if self.kind == "pct_of_pool":
            return self.pct * pool_end
        if period - 1 < len(self.schedule):
            return max(0.0, self.schedule[period - 1])
        return 0.0


class ClassNode(BaseModel):
    type: Literal["class"] = "class"
    class_id: str


class GroupNode(BaseModel):
    """A named group with a payment mode. Children may be classes or further
    groups - the tree nests to arbitrary depth."""

    type: Literal["group"] = "group"
    name: str
    mode: Literal["sequential", "pro_rata", "target_balance"] = "sequential"
    children: list["AllocationNode"] = Field(min_length=1)
    pro_rata_basis: Literal["current", "original"] = "current"
    overflow: Literal["sequential", "pro_rata"] = "sequential"
    target_balance_spec: TargetBalanceSpec | None = None

    @model_validator(mode="after")
    def _check_target_balance(self):
        if self.mode == "target_balance" and self.target_balance_spec is None:
            raise ValueError(f"group {self.name!r}: target_balance mode needs target_balance_spec")
        if self.target_balance_spec is not None and any(
            x < 0 for x in self.target_balance_spec.schedule
        ):
            raise ValueError(f"group {self.name!r}: target balance schedule entries must be >= 0")
        return self


AllocationNode = Annotated[Union[ClassNode, GroupNode], Field(discriminator="type")]
GroupNode.model_rebuild()


def tree_class_ids(node: "ClassNode | GroupNode") -> list[str]:
    """Depth-first leaf order = seniority order for writedowns."""
    if isinstance(node, ClassNode):
        return [node.class_id]
    out: list[str] = []
    for child in node.children:
        out.extend(tree_class_ids(child))
    return out


def tree_group_names(node: "ClassNode | GroupNode") -> list[str]:
    if isinstance(node, ClassNode):
        return []
    out = [node.name]
    for child in node.children:
        out.extend(tree_group_names(child))
    return out


class CapitalStructure(BaseModel):
    classes: list[BondClass] = Field(min_length=1)
    allocation_tree: GroupNode

    @model_validator(mode="after")
    def _validate_tree(self):
        class_ids = [c.id for c in self.classes]
        if len(set(class_ids)) != len(class_ids):
            raise ValueError("duplicate bond class ids")
        leaves = tree_class_ids(self.allocation_tree)
        if sorted(leaves) != sorted(set(leaves)):
            raise ValueError("allocation tree references a class more than once")
        missing = set(class_ids) - set(leaves)
        if missing:
            raise ValueError(f"classes missing from allocation tree: {sorted(missing)}")
        unknown = set(leaves) - set(class_ids)
        if unknown:
            raise ValueError(f"allocation tree references unknown classes: {sorted(unknown)}")
        groups = tree_group_names(self.allocation_tree)
        if len(set(groups)) != len(groups):
            raise ValueError("duplicate group names in allocation tree")
        collisions = set(groups) & set(class_ids)
        if collisions:
            raise ValueError(f"group names collide with class ids: {sorted(collisions)}")
        return self

    def class_by_id(self, class_id: str) -> BondClass:
        for c in self.classes:
            if c.id == class_id:
                return c
        raise KeyError(class_id)
