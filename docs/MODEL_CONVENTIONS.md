# Model conventions

Use these definitions when building a gold-standard model (Excel, Intex, …)
to compare against the engine. Every choice below is pinned by a test in
`backend/tests`.

## Timing & units

- Monthly periods; period 1 is the first collection period; all cash arrives
  at period end. No payment-date calendar in Phase 1.
- All rates are **annual decimals** (`0.08` = 8%). CPR/CDR convert to monthly
  via survival: `SMM = 1-(1-CPR)^(1/12)`, `MDR = 1-(1-CDR)^(1/12)`.
- Bond and loan interest accrue at `rate/12` per period (30/360 monthly).

## Collateral, per repline per period (in this order)

1. **Defaults** `D = beg_performing × MDR` (CDR spec), or from the cum-loss
   timing curve:
   - target default dollars `D*_t = cum_net_loss × timing_t × original_balance / severity_t`;
   - `original_MDR`: `D_t = min(D*_t, balance)` - dollar defaults fixed
     regardless of prepayments;
   - `aggregate_MDR`: `D*` is first converted to a *rate* path on a
     zero-prepay reference amortization (scheduled principal + defaults
     only), then that rate is applied to the actual balance - so faster
     actual prepayments reduce realized losses below the input cum loss.
2. **Interest** accrues on the post-default performing balance.
3. **Scheduled principal**: level payment recomputed each period over the
   remaining term on the current performing balance.
4. **Voluntary prepay** on `base = performing − defaults − sched`:
   - `voluntary` speed: `prepay = base × SMM`;
   - `all_in` speed: `vol_SMM = 1 − (1−allin_SMM)/(1−MDR)` floored at 0
     (so `(1−MDR)(1−vol_SMM) = 1−allin_SMM`). The defaulted portion never prepays.
5. **Charge-off** exactly `charge_off_lag` periods after default (lag 0 =
   same period). Loss recognized **at charge-off** = defaulted amount ×
   severity, with severity **locked at the default period**.
6. **Recovery cash** = defaulted amount × (1 − severity), arriving
   `recovery_lag` periods **after charge-off**. Routed to principal
   collections by default (`recoveries_to` on the scenario).
- **Performing balance** excludes defaults immediately (no interest, no
  sched); **trust balance** = performing + defaulted-not-yet-charged-off.
- Flows scheduled beyond `num_periods` are truncated - size the horizon to
  cover runoff + lags.

## Delays (per repline)

Repline period `t` maps to trust period `max(1, t − collection_delay) + funding_delay`.
Collection delay 1: repline periods 1-2 cash combine into trust period 1.
Funding delay 1: everything shifts one trust period later (trust period 1 empty).

## Pool-level

- Servicing fee = `servicing_fee_rate/12 × beginning basis balance`
  (trust by default), netted **off the top** of interest collections before
  the waterfall (floored at zero).
- Deal-level `FeeSpec`s are different: paid inside the waterfall via
  `pay_fees`, due = `rate/12 × beginning basis balance + fixed`.

## Waterfall

- Buckets seeded per period: `interest_collections` (net of servicing fee),
  `principal_collections` (sched + prepay + recoveries), or a single
  `total_collections` in combined mode. Steps draw in order and can never
  overdraw.
- `pay_interest` pays the current accrual; unpaid current interest rolls to a
  shortfall ledger at period end (no compounding in Phase 1);
  `pay_interest_shortfall` pays the carried ledger.
- `pay_principal` amount rules:
  - `collections` = the period's principal collections;
  - `regular_pda` = `max(0, total bond balance − (pool balance − target_OC))`
    using the period's **ending** pool balance on the step's basis.
- Targets are paid in listed order; if consecutive listed classes are exactly
  the full class set of a pro-rata group in the allocation tree, the group's
  pro-rata mode wins. Pro-rata shares are by beginning-of-period balances
  (`current`) or original balances (`original`), with overflow redistributed
  to undersubscribed siblings.
- Final period: any remaining bond balance becomes a writedown, applied in
  reverse seniority (depth-first allocation-tree leaf order).

## Metrics

- WAL (years) = `Σ(prin_t × t) / Σ(prin_t) / 12` over principal actually
  received (writedowns excluded).
- Yield solves `Σ cf_t/(1+y/12)^t = price/100 × original_balance` over paid
  interest + shortfall + principal; reported as nominal annual (monthly × 12).
