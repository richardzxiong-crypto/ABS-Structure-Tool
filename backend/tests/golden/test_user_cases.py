"""Auto-discovered user golden cases: deal.json + expected_* files per case.

See cases/README.md for the format. Only the rows/columns the user provides
are compared, at the case's configured tolerance.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from absengine.models.deal import Deal
from absengine.runner import run_deal

CASES_DIR = Path(__file__).parent / "cases"
_case_dirs = (
    sorted(d for d in CASES_DIR.iterdir() if d.is_dir() and (d / "deal.json").exists())
    if CASES_DIR.exists()
    else []
)


def _expected_files(case_dir: Path) -> dict[str, dict[str, Path]]:
    """{scenario: {table: path}} from expected_<scenario>__<table>.* files."""
    out: dict[str, dict[str, Path]] = {}
    for p in case_dir.glob("expected_*"):
        body = p.stem[len("expected_"):]
        if "__" not in body:
            raise ValueError(f"{p.name}: expected file must be named expected_<scenario>__<table>")
        scenario, table = body.rsplit("__", 1)
        out.setdefault(scenario, {})[table] = p
    return out


def _compare_table(
    actual: pd.DataFrame, expected: pd.DataFrame, keys: list[str], tol: float, label: str
) -> None:
    for k in keys:
        assert k in expected.columns, f"{label}: expected CSV needs a {k!r} column"
    value_cols = [c for c in expected.columns if c not in keys]
    unknown = set(value_cols) - set(actual.columns)
    assert not unknown, f"{label}: unknown columns {sorted(unknown)}; engine has {sorted(actual.columns)}"

    merged = expected.merge(actual, on=keys, how="left", suffixes=("_exp", "_act"))
    for col in value_cols:
        exp = merged[f"{col}_exp"].to_numpy(dtype=float)
        act = merged[f"{col}_act"].to_numpy(dtype=float)
        missing = np.isnan(act) & ~np.isnan(exp)
        assert not missing.any(), (
            f"{label}.{col}: {missing.sum()} expected rows not found in engine output "
            f"(keys: {merged.loc[missing, keys].to_dict('records')[:5]})"
        )
        bad = ~np.isclose(act, exp, atol=tol, rtol=0.0, equal_nan=True)
        if bad.any():
            detail = merged.loc[bad, keys + [f"{col}_exp", f"{col}_act"]].head(8).to_string(index=False)
            diff = np.nanmax(np.abs(act[bad] - exp[bad]))
            pytest.fail(
                f"{label}.{col}: {bad.sum()} mismatches (max abs diff {diff:.6g}, tol {tol:g}):\n{detail}"
            )


def _compare_metrics(actual, expected, tol: float, path: str = "metrics") -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected a dict"
        for k, v in expected.items():
            assert k in actual, f"{path}.{k}: not in engine metrics ({sorted(actual)})"
            _compare_metrics(actual[k], v, tol, f"{path}.{k}")
    elif isinstance(expected, (list, tuple)):
        actual_list = list(actual) if actual is not None else None
        assert actual_list is not None and len(actual_list) == len(expected), f"{path}: {actual!r} != {expected!r}"
        for i, (a, e) in enumerate(zip(actual_list, expected)):
            _compare_metrics(a, e, tol, f"{path}[{i}]")
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        assert actual is not None, f"{path}: engine returned None, expected {expected}"
        assert actual == pytest.approx(expected, abs=tol), f"{path}: {actual} != {expected} (tol {tol:g})"
    else:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"


@pytest.mark.parametrize("case_dir", _case_dirs, ids=lambda d: d.name)
def test_user_golden_case(case_dir: Path):
    deal = Deal.model_validate(json.loads((case_dir / "deal.json").read_text()))
    cfg_path = case_dir / "config.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    tol = float(cfg.get("abs_tol", 1e-6))

    expected = _expected_files(case_dir)
    assert expected, f"{case_dir.name}: no expected_* files found"

    for scenario, tables in sorted(expected.items()):
        res = run_deal(deal, scenario)
        label = f"{case_dir.name}/{scenario}"
        if "collateral" in tables:
            _compare_table(res.collateral, pd.read_csv(tables["collateral"]),
                           keys=["period"], tol=tol, label=f"{label}/collateral")
        if "bonds" in tables:
            exp = pd.read_csv(tables["bonds"])
            exp["class_id"] = exp["class_id"].astype(str)
            _compare_table(res.bonds, exp, keys=["period", "class_id"],
                           tol=tol, label=f"{label}/bonds")
        if "metrics" in tables:
            # normalize tuples/numpy types through JSON for comparison
            actual_metrics = json.loads(json.dumps(res.metrics, default=float))
            _compare_metrics(actual_metrics, json.loads(tables["metrics"].read_text()), tol)
