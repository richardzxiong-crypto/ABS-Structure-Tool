"""Target resolution + recursive allocation-tree evaluator.

A step's target list is a priority sequence (paid in listed order); each
target resolves to its tree node, whose payment mode governs internally.
Collapse rule: if consecutive listed classes are exactly the full class set of
a pro_rata / target_balance group, they collapse into that group and the tree
mode wins - listed order matters unless the allocation tree says pro-rata.

Group modes:
- sequential:     children in order, each to capacity;
- pro_rata:       water-filling by basis (current/original balance), overflow
                  redistributed to undersubscribed siblings;
- target_balance: the group takes at most `group_cap(node)` (supplied by the
                  caller - for principal steps that is current group balance
                  minus the period's target balance) and distributes it among
                  its children sequentially or pro rata per the spec. Without
                  a group_cap function (interest steps) it acts sequentially.
"""

from __future__ import annotations

from typing import Callable

from ..models.structure import AllocationNode, ClassNode, GroupNode, tree_class_ids

_EPS = 1e-9

CapacityFn = Callable[[str], float]  # class_id -> max payable for this action
BasisFn = Callable[[str], float]  # class_id -> pro-rata weight (current/original balance)
GroupCapFn = Callable[[GroupNode], "float | None"]  # group -> cap on what it may take


def _group_index(tree: GroupNode) -> dict[str, GroupNode]:
    out: dict[str, GroupNode] = {}

    def walk(node: AllocationNode) -> None:
        if isinstance(node, GroupNode):
            out[node.name] = node
            for c in node.children:
                walk(c)

    walk(tree)
    return out


def resolve_targets(targets: list[str], tree: GroupNode) -> list[AllocationNode]:
    groups = _group_index(tree)
    # full class sets of non-sequential groups, for the collapse rule
    collapse_sets: dict[frozenset[str], GroupNode] = {
        frozenset(tree_class_ids(g)): g
        for g in groups.values()
        if g.mode in ("pro_rata", "target_balance")
    }
    class_ids = set(tree_class_ids(tree))

    resolved: list[AllocationNode] = []
    i = 0
    while i < len(targets):
        t = targets[i]
        if t in groups:
            resolved.append(groups[t])
            i += 1
            continue
        if t not in class_ids:
            raise ValueError(f"unknown waterfall target {t!r}")
        # longest run of class ids starting here that exactly matches a
        # pro-rata group's full class set collapses into that group
        matched = False
        for j in range(len(targets), i + 1, -1):
            run = targets[i:j]
            if all(x in class_ids for x in run) and len(set(run)) == len(run):
                grp = collapse_sets.get(frozenset(run))
                if grp is not None:
                    resolved.append(grp)
                    i = j
                    matched = True
                    break
        if not matched:
            resolved.append(ClassNode(class_id=t))
            i += 1
    return resolved


def _cap_of(node: AllocationNode, group_cap: GroupCapFn | None) -> float | None:
    if group_cap is None or not isinstance(node, GroupNode) or node.mode != "target_balance":
        return None
    return group_cap(node)


def node_capacity(
    node: AllocationNode, capacity: CapacityFn, group_cap: GroupCapFn | None = None
) -> float:
    """Max cash the subtree can absorb: sum of leaf capacities, further capped
    by target-balance group caps at every level."""
    if isinstance(node, ClassNode):
        return capacity(node.class_id)
    total = sum(node_capacity(c, capacity, group_cap) for c in node.children)
    cap = _cap_of(node, group_cap)
    if cap is not None:
        total = min(total, max(cap, 0.0))
    return total


def _node_basis(
    node: AllocationNode, basis: BasisFn, capacity: CapacityFn, group_cap: GroupCapFn | None
) -> float:
    # saturated subtrees carry no weight so redistribution converges
    if node_capacity(node, capacity, group_cap) <= _EPS:
        return 0.0
    return sum(basis(cid) for cid in tree_class_ids(node))


def _merge(out: dict[str, float], sub: dict[str, float]) -> None:
    for k, v in sub.items():
        out[k] = out.get(k, 0.0) + v


def _allocate_sequential(
    amount: float, children: list[AllocationNode], capacity, basis, group_cap
) -> dict[str, float]:
    out: dict[str, float] = {}
    remaining = amount
    for child in children:
        if remaining <= _EPS:
            break
        give = min(remaining, node_capacity(child, capacity, group_cap))
        sub = allocate(give, child, capacity, basis, group_cap)
        _merge(out, sub)
        remaining -= sum(sub.values())
    return out


def _allocate_pro_rata(
    amount: float, children: list[AllocationNode], capacity, basis, group_cap
) -> dict[str, float]:
    # iterative water-filling: proportional shares capped at capacity,
    # overflow redistributed to undersubscribed siblings until exhausted
    out: dict[str, float] = {}
    caps = [node_capacity(c, capacity, group_cap) for c in children]
    remaining = min(amount, sum(caps))
    granted: dict[int, float] = {i: 0.0 for i in range(len(children))}
    while remaining > _EPS:
        active = [i for i in range(len(children)) if caps[i] - granted[i] > _EPS]
        if not active:
            break
        weights = {i: _node_basis(children[i], basis, capacity, group_cap) for i in active}
        total_w = sum(weights.values())
        progressed = False
        if total_w <= _EPS:
            shares = {i: remaining / len(active) for i in active}
        else:
            shares = {i: remaining * weights[i] / total_w for i in active}
        for i in active:
            room = caps[i] - granted[i]
            give = min(shares[i], room)
            if give > _EPS:
                granted[i] += give
                remaining -= give
                progressed = True
        if not progressed:
            break
    for i, child in enumerate(children):
        if granted[i] > _EPS:
            _merge(out, allocate(granted[i], child, capacity, basis, group_cap))
    return out


def allocate(
    amount: float,
    node: AllocationNode,
    capacity: CapacityFn,
    basis: BasisFn,
    group_cap: GroupCapFn | None = None,
) -> dict[str, float]:
    """Distribute `amount` through the subtree; never exceeds capacities or
    target-balance group caps. Returns {class_id: cash}."""
    if amount <= _EPS:
        return {}

    if isinstance(node, ClassNode):
        take = min(amount, capacity(node.class_id))
        return {node.class_id: take} if take > _EPS else {}

    if node.mode == "sequential":
        return _allocate_sequential(amount, node.children, capacity, basis, group_cap)

    if node.mode == "pro_rata":
        return _allocate_pro_rata(amount, node.children, capacity, basis, group_cap)

    if node.mode == "target_balance":
        cap = _cap_of(node, group_cap)
        take = amount if cap is None else min(amount, max(cap, 0.0))
        if take <= _EPS:
            return {}
        spec = node.target_balance_spec
        if cap is not None and spec is not None and spec.distribution == "pro_rata":
            return _allocate_pro_rata(take, node.children, capacity, basis, group_cap)
        return _allocate_sequential(take, node.children, capacity, basis, group_cap)

    raise ValueError(f"unknown allocation mode {node.mode!r}")


def allocate_by_node(
    amount: float,
    nodes: list[AllocationNode],
    capacity: CapacityFn,
    basis: BasisFn,
    group_cap: GroupCapFn | None = None,
) -> list[dict[str, float]]:
    """A step's resolved target list: sequential priority across entries.
    Returns one {class_id: cash} dict per node (a class may appear under
    several nodes - e.g. a scheduled class listed again after its companion -
    so per-node results keep the audit log exact)."""
    per_node: list[dict[str, float]] = []
    remaining = amount
    for node in nodes:
        sub = allocate(remaining, node, capacity, basis, group_cap) if remaining > _EPS else {}
        per_node.append(sub)
        remaining -= sum(sub.values())
    return per_node


def allocate_across(
    amount: float,
    nodes: list[AllocationNode],
    capacity: CapacityFn,
    basis: BasisFn,
    group_cap: GroupCapFn | None = None,
) -> dict[str, float]:
    out: dict[str, float] = {}
    for sub in allocate_by_node(amount, nodes, capacity, basis, group_cap):
        _merge(out, sub)
    return out
