# sfast-2026-1 — SFS Auto Receivables Securitization Trust 2026-1

Golden case extracted from the uploaded Intex CF workbook
(`../SFAST2026-1 deal config.xlsx`) by `scripts/extract_sfast_case.py`
(rerunning the script regenerates `deal.json` and the expected CSVs).

$1.5bn prime auto deal: 21 replines ($1,634,210,207.42), classes
A1/A2A/A2B/A3/A4/B/C + certificates, 1% servicing fee, $1,425/mo trustee
fee, $3.9mm non-declining reserve (0.25% of initial adjusted pool), YSOC
(strike 6.30%, stepdown 5.80% once A2B retires, closing amount hard-coded
at $71,708,995.93), First/Second/Third/Regular Allocations of Principal
against the adjusted pool, target OC = max(6.75% current, 1.00% initial
adjusted), reserve-to-retire enabled. A1 is ACT/360; A2B floats at
SOFR_NYF_30D + 0.46% ACT/360 (index path taken from the workbook); others
30/360. Closing 2026-02-26, first payment 2026-03-20, following-business-day
adjustment on ACT classes.

Scenarios (both tie to < $0.001 on every collateral/bond column, every
period):

- **scen1**: 1.40% ABS voluntary prepay, 2.25% CDR, 50% severity,
  charge-off lag 3, recovery lag 3 from default.
- **scen2**: 1.40% ABS, 2.25% CNL with 40/35/20/5 annual loss-recognition
  timing, same severity/lags.

Intex conventions this case pinned (all opt-in flags, see
`docs/MODEL_CONVENTIONS.md`): `prepay_base=gross_of_defaults`,
`recovery_lag_from=default`, `suppress_defaults_near_maturity`,
`timing_applies_to=losses`, `allocation=pool`, YSOA on the trust balance,
stepdown strike applied in PDA formulas only (reported adjusted-balance
column stays at the primary strike).

Known source-model artifacts (intentionally not replicated):

- The workbook's "aggregate MDR" run realizes the input CNL exactly as
  fixed dollars (no prepay interaction), i.e. it behaves as this engine's
  `original_MDR` + pool allocation; the deal config uses that.
- One period after the notes retire (p65 in both scenarios), the workbook
  shows a second $3,906,253.03 reserve withdrawal from an already-empty
  account, paying the certificateholder the reserve twice. The engine
  releases the reserve once, at note retirement (p64, which ties exactly);
  the certificate strip is excluded from the expected files for that reason.
