# ABS Structuring Tool

An Intex DealMaker-style structuring tool for asset-backed securities:
model a collateral pool by replines, define the capital structure and a
freely-configurable waterfall, run prepay/loss scenarios, and analyze the
resulting bond cashflows.

## Stack

- **`backend/absengine`** — pure-Python domain engine (Pydantic v2 models,
  numpy collateral projections, plain-Python waterfall interpreter). No web
  framework imports; runnable from pytest or a script.
- **`backend/app`** — FastAPI layer translating HTTP ↔ domain.
- **`frontend/`** — React + TypeScript (Vite, Tailwind, AG Grid, Recharts).
- **`deals/`** — the file-based deal library (`templates/`, one folder per
  deal with `deal.json` + version snapshots).

## Quick start

```bash
make setup   # uv venv + backend deps, npm install
make test    # backend test suite (golden + invariants + unit + API)
make dev     # FastAPI on :8000, Vite on :5173
```

Open http://localhost:5173, create a deal from the `auto_seq_2tranche`
template (or open the example deal), edit replines / structure / waterfall /
scenarios, and hit **Run**.

## Engine concepts (Phase 1)

**Collateral** — level-pay amortizing replines with:
- defaults via CDR vectors or cumulative-loss + timing curves
  (`aggregate_MDR` / `original_MDR` conventions),
- all-in vs voluntary prepay speeds (prepay base excludes defaulted balance),
- a default → charge-off (lag) → recovery (lag) pipeline with distinct
  **performing** and **trust** balances,
- per-repline `collection_delay` / `funding_delay` trust-timeline mapping.

**Structure** — bond classes plus a recursive **allocation tree**: named
groups with payment modes (`sequential`, `pro_rata`; `target_balance` in
Phase 2) nesting to arbitrary depth.

**Waterfall** — ordered steps, each `source → action → targets`:
sources are named cash buckets; actions are registered handlers
(`pay_fees`, `pay_interest`, `pay_interest_shortfall`, `pay_principal` with
`collections`/`regular_pda` amount rules, `release_residual`); targets are
classes or tree groups (listed order matters unless the tree says pro-rata).
Every draw is logged to a flow audit table shown in the UI.

**Extensibility** — config models + registries (`STEP_REGISTRY`,
`TRIGGER_REGISTRY`, `ASSET_REGISTRY`): adding a step type or asset class is
one module with a `@REGISTRY.register(...)` decorator.

Phase 2+ (modeled, validation-gated): floating coupons, reserve accounts,
external sources, triggers + step conditions, `target_balance` mode,
`priority_pda`/`turbo`, YSOC, breakeven/matrix analytics.

## Tests

`backend/tests` contains golden tests (engine output vs independent
hand-computed models at 1e-6), invariant tests (cash conservation, no
negative balances, roll-forward ties) run across scenario types, unit tests,
and API round-trip tests.

### Verifying against your own gold standard

Drop a deal + expected numbers into `backend/tests/golden/cases/<name>/`
(format in `cases/README.md`; partial rows/columns fine, tolerance
configurable) and `make test` compares the engine against them.
`docs/MODEL_CONVENTIONS.md` defines every timing/rate convention so your
spreadsheet computes the same quantities, and
`python scripts/dump_results.py <deal.json> <scenario>` dumps engine output
in the same CSV format for diffing.
