"""Dump engine results for a deal+scenario in the golden-case file format.

Usage:
    python scripts/dump_results.py <deal.json> <scenario> [outdir]

Writes actual_<scenario>__{collateral,bonds,flows}.csv and
actual_<scenario>__metrics.json to outdir (default: alongside deal.json).
Rename actual_ -> expected_ (after checking the numbers!) to pin them, or
diff them against your own spreadsheet.
"""

import json
import sys
from pathlib import Path

from absengine.models.deal import Deal
from absengine.runner import run_deal


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    deal_path = Path(sys.argv[1])
    scenario = sys.argv[2]
    outdir = Path(sys.argv[3]) if len(sys.argv) > 3 else deal_path.parent
    outdir.mkdir(parents=True, exist_ok=True)

    deal = Deal.model_validate(json.loads(deal_path.read_text()))
    res = run_deal(deal, scenario)

    res.collateral.to_csv(outdir / f"actual_{scenario}__collateral.csv", index=False)
    res.bonds.to_csv(outdir / f"actual_{scenario}__bonds.csv", index=False)
    res.flows.to_csv(outdir / f"actual_{scenario}__flows.csv", index=False)
    metrics = json.loads(json.dumps(res.metrics, default=float))
    (outdir / f"actual_{scenario}__metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"wrote actual_{scenario}__* to {outdir}")


if __name__ == "__main__":
    main()
