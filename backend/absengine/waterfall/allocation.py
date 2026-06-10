"""Target resolution + recursive allocation-tree evaluator.

A step's target list is a priority sequence (paid in listed order); each
target resolves to its tree node, whose payment mode governs internally.
Collapse rule: if consecutive listed classes are exactly the full class set of
a pro_rata / target_balance group, they collapse into that group and the tree
mode wins - listed order matters unless the allocation tree says pro-rata.
"""

from __future__ import annotations

from typing import Callable

from ..models.structure import AllocationNode, ClassNode, GroupNode, tree_class_ids

_EPS = 1e-9

CapacityFn = Callable[[str], float]  # class_id -> max payable for this action
BasisFn = Callable[[str], float]  # class_id -> pro-rata weight (current/original balance)


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


def node_capacity(node: AllocationNode, capacity: CapacityFn) -> float:
    return sum(capacity(cid) for cid in tree_class_ids(node))


def _node_basis(node: AllocationNode, basis: BasisFn, capacity: CapacityFn) -> float:
    # saturated subtrees carry no weight so redistribution converges
    if node_capacity(node, capacity) <= _EPS:
        return 0.0
    return sum(basis(cid) for cid in tree_class_ids(node))


def allocate(
    amount: float,
    node: AllocationNode,
    capacity: CapacityFn,
    basis: BasisFn,
) -> dict[str, float]:
    """Distribute `amount` through the subtree; never exceeds capacities.
    Returns {class_id: cash}."""
    out: dict[str, float] = {}
    if amount <= _EPS:
        return out

    if isinstance(node, ClassNode):
        take = min(amount, capacity(node.class_id))
        if take > _EPS:
            out[node.class_id] = take
        return out

    if node.mode == "sequential":
        remaining = amount
        for child in node.children:
            if remaining <= _EPS:
                break
            give = min(remaining, node_capacity(child, capacity))
            sub = allocate(give, child, capacity, basis)
            for k, v in sub.items():
                out[k] = out.get(k, 0.0) + v
            remaining -= sum(sub.values())
        return out

    if node.mode == "pro_rata":
        # iterative water-filling: proportional shares capped at capacity,
        # overflow redistributed to undersubscribed siblings until exhausted
        remaining = min(amount, node_capacity(node, capacity))
        granted: dict[int, float] = {i: 0.0 for i in range(len(node.children))}
        while remaining > _EPS:
            active = [
                i
                for i, child in enumerate(node.children)
                if node_capacity(child, capacity) - granted[i] > _EPS
            ]
            if not active:
                break
            weights = {i: _node_basis(node.children[i], basis, capacity) for i in active}
            total_w = sum(weights.values())
            progressed = False
            if total_w <= _EPS:
                shares = {i: remaining / len(active) for i in active}
            else:
                shares = {i: remaining * weights[i] / total_w for i in active}
            for i in active:
                room = node_capacity(node.children[i], capacity) - granted[i]
                give = min(shares[i], room)
                if give > _EPS:
                    granted[i] += give
                    remaining -= give
                    progressed = True
            if not progressed:
                break
        for i, child in enumerate(node.children):
            if granted[i] > _EPS:
                sub = allocate(granted[i], child, capacity, basis)
                for k, v in sub.items():
                    out[k] = out.get(k, 0.0) + v
        return out

    raise NotImplementedError(f"allocation mode {node.mode!r} (Phase 2)")


def allocate_across(
    amount: float,
    nodes: list[AllocationNode],
    capacity: CapacityFn,
    basis: BasisFn,
) -> dict[str, float]:
    """A step's resolved target list: sequential priority across entries."""
    out: dict[str, float] = {}
    remaining = amount
    for node in nodes:
        if remaining <= _EPS:
            break
        sub = allocate(remaining, node, capacity, basis)
        for k, v in sub.items():
            out[k] = out.get(k, 0.0) + v
        remaining -= sum(sub.values())
    return out
