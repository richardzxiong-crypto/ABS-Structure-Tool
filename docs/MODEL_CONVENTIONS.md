# Model conventions

Use these definitions when building a gold-standard model (Excel, Intex, …)
to compare against the engine. Every choice below is pinned by a test in
`backend/tests`. Flags marked *(Intex-style)* were reverse-engineered against
an Intex CF run (the `sfast-2026-1` golden case) and tie to sub-cent precision.

## Timing & units

- Monthly periods; period 1 is the first collection period; all cash arrives
  at period end.
- All rates are **annual decimals** (`0.08` = 8%). CPR/CDR convert to monthly
  via survival: `SMM = 1-(1-CPR)^(1/12)`, `MDR = 1-(1-CDR)^(1/12)`.
- Loan interest accrues at `rate/12` per period; bond interest too unless the
  deal has a payment calendar (below).

## Payment calendar & bond day counts (`deal.dates`)

- Without `deal.dates`: every bond accrual is a flat `rate/12`; ACT day
  counts are rejected.
- With `deal.dates {closing_date, first_payment_date}`: bond accrual period t
  runs payment date t-1 → t (monthly anniversaries of the first payment
  date); period 1 accrues from the **closing date** (typically short - e.g.
  24/360 for a 30/360 class, actual days for ACT/360).
- `business_day_adjust: "following"`: ACT-day-count classes accrue between
  payment dates rolled to the next US business day (weekends + US federal
  holidays); **30/360 classes always accrue on unadjusted dates** (exactly
  rate/12 per full period). Collateral periods are whole months regardless.
- Floating coupons: `rate_t = index_t + margin` (cap/floor applied), where
  `index_t` comes from the scenario's `index_curves[<index name>]` vector for
  period t.

## Collateral, per repline per period (in this order)

1. **Defaults** `D = beg_performing × MDR` (CDR spec), or from the cum-loss
   timing curve:
   - target default dollars `D*_t = cum_net_loss × timing_t × original_balance / severity_t`;
   - `timing_unit: "annual"`: each timing entry is a year's share, spread
     evenly across its months;
   - `timing_applies_to: "losses"` *(Intex-style)*: the curve positions
     **loss recognition (charge-offs)**, and defaults occur `charge_off_lag`
     earlier - with annual buckets, year 1's share spreads over its
     **feasible** charge-off months only (months `charge_off_lag+1`..12);
   - `aggregate_MDR`: `D_t = min(D*_t, balance)` - dollar defaults fit
     directly to the cum-loss target, so realized cumulative loss equals the
     input regardless of prepay speed (the loss is "fit in");
   - `original_MDR`: `D*` is first converted to a *rate* path fixed on a
     zero-prepay reference amortization (scheduled principal + defaults
     only), then that rate is applied to the actual balance - so faster
     actual prepayments leave realized loss below the input cum loss (a gap);
   - `allocation: "pool"` *(Intex-style)*: the pool-level target dollars are
     allocated each period across surviving replines pro rata by performing
     balance (capped, overflow redistributed) - a matured repline's share
     moves to the survivors so the pool realizes the full target. Default
     `"repline"` keeps each repline's own share (lost if it matures).
   - `suppress_defaults_near_maturity` *(Intex-style)*: no new defaults once
     a repline's remaining scheduled term ≤ `charge_off_lag`.
2. **Interest** accrues on the post-default performing balance.
3. **Scheduled principal**: level payment recomputed each period over the
   remaining term on the current performing balance.
4. **Voluntary prepay**, capped so performing can't go negative:
   - `prepay_base: "net_of_defaults"` (default): `base = performing − sched`;
   - `prepay_base: "gross_of_defaults"` *(Intex-style)*: `base = beginning
     balance − sched(beginning balance)` - current-period defaults stay in
     the rate base;
   - `voluntary` speed: `prepay = base × SMM`;
   - `all_in` speed: `vol_SMM = 1 − (1−allin_SMM)/(1−MDR)` floored at 0
     (so `(1−MDR)(1−vol_SMM) = 1−allin_SMM`).
   - `speed_unit: "abs"`: speed is an Absolute Prepayment Speed (monthly, %
     of original balance); per repline `SMM_m = ABS/(1 − ABS×(m−1))` with
     `m` = loan age in months (`original_term − remaining_term + period`),
     capped at 100%.
5. **Charge-off** exactly `charge_off_lag` periods after default (lag 0 =
   same period). Loss recognized **at charge-off** = defaulted amount ×
   severity, with severity **locked at the default period**.
6. **Recovery cash** = defaulted amount × (1 − severity), arriving
   `recovery_lag` periods after charge-off, or after **default** when
   `recovery_lag_from: "default"` *(Intex-style: with equal lags the recovery
   arrives in the same period as the charge-off)*. Routed to principal
   collections by default (`recoveries_to` on the scenario).
- **Performing balance** excludes defaults immediately (no interest, no
  sched); **trust balance** = performing + defaulted-not-yet-charged-off.
- Flows scheduled beyond `num_periods` are truncated - size the horizon to
  cover runoff + lags.

## YSOC (`deal.ysoc`)

- Dynamic per period: `YSOA_t = Σ over replines of max(0, balance_t −
  PV(remaining level payments @ required_rate))`, recomputed off actual
  end-of-period balances; the balance basis is `trust` by default (the
  pending-charge-off bucket scales the contribution - Intex convention) or
  `performing`.
- `initial_amount`: hard-coded closing YSOA (e.g. the prospectus number,
  computed loan-by-loan); period 1's **adjusted pool balance** = beginning
  basis balance − initial_amount. Later periods: ending basis balance −
  YSOA_t.
- `stepdown_rate` + `stepdown_when_class_zero`: once the named class starts a
  period at zero balance, **PDA formulas** (priority/regular, OC targets)
  switch to the stepdown-strike YSOA. The *reported* `ysoa`/`adjusted_pool`
  columns stay at the primary strike (dealer-report convention).
- The `adjusted` pool basis (= basis balance − YSOA) is selectable wherever a
  pool balance is referenced: PDA rules, OC targets, fees.

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
    using the period's **ending** pool balance on the step's basis;
  - `priority_pda` = `max(0, Σ step-target class balances − pool balance)`.
    Cumulative tiers (First/Second/Third Allocations of Principal) are
    consecutive `priority_pda` steps with growing target sets
    (`[A]`, `[A,B]`, `[A,B,C]`) - balances update between steps, so
    "minus prior allocations" is automatic;
  - `turbo` = everything left in the source bucket.
- `target_oc` supports a floor: `target = max(kind/value, floor_kind/
  floor_value)`, e.g. greater of 6.75% of the current (adjusted) pool and
  1.00% of the initial (adjusted) pool.
- **Reserve accounts**: seeded as a `reserve:<name>` bucket each period and
  carried over. "Pay X from collections, then from the reserve" = two
  consecutive steps with the same action, the second sourced
  `reserve:<name>` (every action is due-driven and remembers what was paid
  this period, so the pair composes without double-paying). `fund_reserve`
  tops the bucket back to target. `retire_bonds` (optional
  "reserve-to-retire"): if source + reserve cover the total bond balance
  after the interest/fee clauses, retire every class in seniority order
  (source cash first) and release the leftover reserve into the source
  bucket (the account closes once the notes are gone).
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
