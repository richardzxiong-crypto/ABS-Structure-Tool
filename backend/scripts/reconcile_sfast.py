"""Diff engine output vs the sfast-2026-1 expected CSVs, column by column.

Usage: python scripts/reconcile_sfast.py [scen1|scen2] [--periods N]
Prints worst absolute diffs per column and the first few offending periods.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from absengine.models.deal import Deal
from absengine.runner import run_deal

CASE = Path(__file__).resolve().parents[1] / "tests" / "golden" / "cases" / "sfast-2026-1"


def diff_table(actual: pd.DataFrame, expected: pd.DataFrame, keys: list[str], label: str) -> None:
    merged = expected.merge(actual, on=keys, how="left", suffixes=("_exp", "_act"))
    print(f"\n=== {label} ===")
    for col in [c for c in expected.columns if c not in keys]:
        d = (merged[f"{col}_act"] - merged[f"{col}_exp"]).abs()
        worst = d.nlargest(3)
        flag = "OK   " if d.max() < 0.01 else "DIFF "
        print(f"{flag}{col:<16} max|d|={d.max():>14.6f}  ", end="")
        if d.max() >= 0.01:
            rows = merged.loc[worst.index, keys + [f"{col}_exp", f"{col}_act"]]
            print(" worst:", rows.to_dict("records"))
        else:
            print()


def main() -> None:
    scen = sys.argv[1] if len(sys.argv) > 1 else "scen1"
    deal = Deal.model_validate(json.loads((CASE / "deal.json").read_text()))
    res = run_deal(deal, scen)

    exp_c = pd.read_csv(CASE / f"expected_{scen}__collateral.csv")
    diff_table(res.collateral, exp_c, ["period"], f"{scen} collateral")

    exp_b = pd.read_csv(CASE / f"expected_{scen}__bonds.csv")
    exp_b["class_id"] = exp_b["class_id"].astype(str)
    diff_table(res.bonds, exp_b, ["period", "class_id"], f"{scen} bonds")


if __name__ == "__main__":
    main()
