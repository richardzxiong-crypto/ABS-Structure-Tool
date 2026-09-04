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

**One-click (non-technical):** after cloning, double-click `run.command`
(macOS) or `run.bat` (Windows), or run `./run.sh` (Linux/macOS terminal).
It installs/refreshes everything, starts both servers, and opens the app in
your browser — safe to re-run after every `git pull`. Prerequisites: Python
3.11+ and Node 18+ on your PATH.

**Developer workflow:**

```bash
make setup   # uv venv + backend deps, npm install
make test    # backend test suite (golden + invariants + unit + API)
make dev     # FastAPI on :8000, Vite on :5173
```

Open http://localhost:5173, open the `sfast-2026-1` deal (the golden-verified
SFAST 2026-1 auto deal) or create one from the `auto_seq_2tranche` template,
edit deal settings (dates / fees / reserve / YSOC), replines, structure,
waterfall, and scenarios, and hit **Run**.

## Engine concepts

**Collateral** — level-pay amortizing replines with:
- defaults via CDR vectors or cumulative-loss + timing curves
  (`aggregate_MDR` / `original_MDR`; per-period or annual timing; default or
  loss-recognition timing; repline or pool-level dollar allocation),
- all-in vs voluntary prepay speeds in CPR or ABS units, configurable prepay
  base conventions,
- a default → charge-off (lag) → recovery (lag) pipeline with distinct
  **performing** and **trust** balances,
- dynamic YSOC (per-repline PV haircut at a required rate, with stepdown
  strike and hard-coded closing amount) feeding an **adjusted** pool basis,
- per-repline `collection_delay` / `funding_delay` trust-timeline mapping.

**Structure** — bond classes (fixed or floating coupons; 30/360 and ACT day
counts on a business-day-adjusted payment calendar) plus a recursive
**allocation tree**: named groups with payment modes (`sequential`,
`pro_rata`, `target_balance` - scheduled/PAC classes paid down to a
per-period schedule or a pct-of-pool target, excess to companions) nesting
to arbitrary depth.

**Waterfall** — ordered steps, each `source → action → targets`:
sources are named cash buckets including `reserve:<name>` accounts and
`external:<name>` sources (fixed per-period amounts or interest-rate swap
receipts on a class balance; net swap payments are due as `swap:<name>` in
a `pay_fees` step); actions
are registered handlers (`pay_fees`, `pay_interest`,
`pay_interest_shortfall`, `pay_principal` with `collections`/`regular_pda`/
`priority_pda`/`turbo` amount rules, `fund_reserve`, `retire_bonds`,
`release_residual`); targets are classes or tree groups (listed order
matters unless the tree says pro-rata). Priority-PDA tiers
(First/Second/Third Allocations) and target-OC floors are first-class.
Every draw is logged to a flow audit table shown in the UI.

**Extensibility** — config models + registries (`STEP_REGISTRY`,
`TRIGGER_REGISTRY`, `ASSET_REGISTRY`): adding a step type or asset class is
one module with a `@REGISTRY.register(...)` decorator.

**Triggers** — cum-net-loss / pool-factor / OC / IC tests with a
curable-vs-latching state machine, evaluated at determination; any waterfall
step can be conditioned on pass/fail (pro-rata → sequential switches, cash
traps).

**Analytics** — per-class loss breakevens (principal + timely-interest, CNL
or CDR dial), prepay × loss sensitivity matrices, price/yield tables.

Planned (modeled, validation-gated): delinquency triggers.

The `sfast-2026-1` golden case pins the engine against a full Intex CF run
of a $1.5bn prime auto deal (7 classes, YSOC, reserve account, tiered PDAs,
floating A2B) — both scenarios tie to sub-cent precision per period per
class.

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
