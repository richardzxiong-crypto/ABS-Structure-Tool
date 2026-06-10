import pytest

from absengine.models.structure import ClassNode, GroupNode
from absengine.waterfall.allocation import allocate, allocate_across, resolve_targets


def cls(cid):
    return ClassNode(class_id=cid)


TREE = GroupNode(
    name="root",
    mode="sequential",
    children=[
        GroupNode(name="Group A", mode="pro_rata", children=[
            cls("A1"),
            GroupNode(name="Group A2", mode="sequential", children=[cls("A2a"), cls("A2b")]),
            cls("A3"),
        ]),
        cls("B1"),
    ],
)


def test_sequential_fills_in_order():
    node = GroupNode(name="g", mode="sequential", children=[cls("X"), cls("Y")])
    cap = {"X": 10.0, "Y": 50.0}
    out = allocate(30.0, node, cap.get, cap.get)
    assert out == {"X": 10.0, "Y": 20.0}


def test_pro_rata_splits_by_basis():
    node = GroupNode(name="g", mode="pro_rata", children=[cls("X"), cls("Y")])
    cap = {"X": 100.0, "Y": 100.0}
    basis = {"X": 75.0, "Y": 25.0}
    out = allocate(40.0, node, cap.get, basis.get)
    assert out["X"] == pytest.approx(30.0)
    assert out["Y"] == pytest.approx(10.0)


def test_pro_rata_overflow_redistributes():
    """X's share exceeds its capacity -> overflow goes to Y."""
    node = GroupNode(name="g", mode="pro_rata", children=[cls("X"), cls("Y")])
    cap = {"X": 10.0, "Y": 100.0}
    basis = {"X": 100.0, "Y": 100.0}  # e.g. pro_rata_basis=original
    out = allocate(60.0, node, cap.get, basis.get)
    assert out["X"] == pytest.approx(10.0)
    assert out["Y"] == pytest.approx(50.0)


def test_nested_three_levels():
    cap = {"A1": 40.0, "A2a": 10.0, "A2b": 10.0, "A3": 20.0, "B1": 20.0}
    out = allocate(80.0, TREE, cap.get, cap.get)
    # root sequential: Group A capacity 80 takes everything
    assert out["A1"] == pytest.approx(40.0)
    assert out["A2a"] == pytest.approx(10.0)
    assert out["A2b"] == pytest.approx(10.0)
    assert out["A3"] == pytest.approx(20.0)
    assert "B1" not in out
    # partial amount: pro-rata by balance, A2's slice sequential into A2a first
    out = allocate(8.0, TREE, cap.get, cap.get)
    assert out["A1"] == pytest.approx(4.0)
    assert out["A2a"] == pytest.approx(2.0)
    assert "A2b" not in out
    assert out["A3"] == pytest.approx(2.0)


def test_resolve_group_name():
    resolved = resolve_targets(["Group A", "B1"], TREE)
    assert isinstance(resolved[0], GroupNode) and resolved[0].name == "Group A"
    assert isinstance(resolved[1], ClassNode)


def test_resolve_collapses_full_pro_rata_set():
    resolved = resolve_targets(["A1", "A2a", "A2b", "A3", "B1"], TREE)
    assert len(resolved) == 2
    assert isinstance(resolved[0], GroupNode) and resolved[0].name == "Group A"


def test_resolve_partial_set_stays_sequential():
    resolved = resolve_targets(["A1", "A3"], TREE)
    assert all(isinstance(n, ClassNode) for n in resolved)


def test_resolve_unknown_target_raises():
    with pytest.raises(ValueError, match="unknown waterfall target"):
        resolve_targets(["nope"], TREE)


def test_allocate_across_priority_order():
    cap = {"A1": 40.0, "A2a": 10.0, "A2b": 10.0, "A3": 20.0, "B1": 20.0}
    resolved = resolve_targets(["B1", "Group A"], TREE)
    out = allocate_across(30.0, resolved, cap.get, cap.get)
    assert out["B1"] == pytest.approx(20.0)  # listed first -> paid first
    assert sum(out.values()) == pytest.approx(30.0)
