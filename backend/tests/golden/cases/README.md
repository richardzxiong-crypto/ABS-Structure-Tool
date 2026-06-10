# User golden cases

Drop a case here to pin the engine against your own gold-standard numbers
(Excel, Intex, etc.). Each case is a folder:

```
cases/
  my-case/
    deal.json                              # full deal (same schema as the API / deal library)
    config.json                            # optional: {"abs_tol": 0.01}  (default 1e-6)
    expected_<scenario>__collateral.csv    # any subset of periods and columns
    expected_<scenario>__bonds.csv         # any subset of (period, class_id) rows and columns
    expected_<scenario>__metrics.json      # any subset of the metrics dict
```

- `<scenario>` must match a scenario name in `deal.json` (one run per scenario found).
- **Partial expectations are fine** - only the rows and columns you provide are
  compared. A collateral CSV needs a `period` column; a bonds CSV needs
  `period` and `class_id`. Anything else you include must match an engine
  output column.
- Column names: see `docs/MODEL_CONVENTIONS.md` for definitions, and run
  `python scripts/dump_results.py <deal.json> <scenario>` to dump the engine's
  actual output in exactly this format (useful as a column reference and to
  diff against your spreadsheet).
- Tolerance: set `abs_tol` in `config.json` to whatever your source's
  precision supports (e.g. `0.01` for currency rounded to cents).

`pytest tests/golden/test_user_cases.py` (or just `make test`) picks cases up
automatically.

`example-2tranche/` shows the format; its numbers are cross-checked against an
independent hand model in `test_waterfall_golden.py`.
