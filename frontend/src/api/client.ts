// Hand-written types mirroring the backend Pydantic models (Phase 1).
// Follow-up: generate from /openapi.json via openapi-typescript.

export interface RateSpec {
  type: "scalar" | "vector" | "ramp";
  value?: number;
  values?: number[];
  start?: number;
  end?: number;
  periods?: number;
}

export interface Repline {
  id: string;
  balance: number;
  gross_rate: number;
  original_term: number;
  remaining_term: number;
  amort_type: string;
  collection_delay: number;
  funding_delay: number;
}

export interface BondClass {
  id: string;
  name: string;
  balance: number;
  coupon: {
    type: "fixed" | "floating";
    rate?: number;
    index?: string;
    margin?: number;
    cap?: number | null;
    floor?: number | null;
  };
  day_count: "30/360" | "ACT/360" | "ACT/365";
  price: number | null;
}

export interface DealDates {
  closing_date: string; // ISO yyyy-mm-dd
  first_payment_date: string;
  business_day_adjust: "none" | "following";
}

export interface FeeSpec {
  name: string;
  rate: number;
  fixed: number;
  basis: PoolBasis;
}

export interface ReserveAccount {
  name: string;
  target_kind: "pct_current_pool" | "pct_original_pool" | "fixed";
  target_value: number;
  floor: number;
  initial_balance: number;
}

export interface YsocConfig {
  required_rate: number;
  stepdown_rate?: number | null;
  stepdown_when_class_zero?: string | null;
  initial_amount?: number | null;
  method?: "dynamic";
  basis: PoolBasis;
}

export type PoolBasis = "trust" | "performing" | "adjusted";

export interface ExternalSource {
  name: string;
  kind: "amount" | "swap";
  amount: RateSpec;
  start_period: number;
  end_period?: number | null;
  notional_class?: string | null;
  notional_schedule?: number[];
  fixed_rate?: number;
  index?: string;
  spread?: number;
  day_count?: "30/360" | "ACT/360" | "ACT/365";
}

export interface Trigger {
  type: "cum_net_loss" | "delinquency" | "pool_factor" | "oc_test" | "ic_test";
  name: string;
  curable: boolean;
  operator?: "<" | "<=" | ">" | ">=";
  threshold?: number;
  schedule?: [number, number][];
  basis?: PoolBasis;
  lookback?: number;
}

export interface StepCondition {
  trigger: string;
  when: "pass" | "fail";
}

export interface AllocationNode {
  type: "class" | "group";
  class_id?: string;
  name?: string;
  mode?: "sequential" | "pro_rata" | "target_balance";
  children?: AllocationNode[];
  pro_rata_basis?: "current" | "original";
}

export interface TargetOCSpec {
  kind: "fixed" | "pct_current_pool" | "pct_original_pool";
  value: number;
  floor_kind?: "none" | "fixed" | "pct_original_pool";
  floor_value?: number;
}

export interface WaterfallStep {
  type: string;
  id: string;
  label: string;
  source: string;
  fees?: string[];
  targets?: string[];
  amount_rule?: string;
  target_oc?: TargetOCSpec;
  pool_basis?: PoolBasis;
  account?: string; // fund_reserve
  reserve?: string; // retire_bonds
  release_reserve_remainder?: boolean;
  to?: string;
  condition?: StepCondition | null;
  [key: string]: unknown;
}

export interface CumLossDefaults {
  type: "cum_loss";
  cum_net_loss: number;
  timing: number[];
  timing_unit?: "period" | "annual";
  timing_applies_to?: "defaults" | "losses";
  method: "aggregate_MDR" | "original_MDR";
  allocation?: "repline" | "pool";
}

export interface Scenario {
  name: string;
  prepay: {
    speed: RateSpec;
    speed_type: "voluntary" | "all_in";
    speed_unit?: "cpr" | "abs";
    prepay_base?: "net_of_defaults" | "gross_of_defaults";
  };
  loss: {
    defaults: { type: "cdr"; cdr: RateSpec } | CumLossDefaults;
    severity: RateSpec;
    charge_off_lag: number;
    recovery_lag: number;
    recovery_lag_from?: "charge_off" | "default";
    suppress_defaults_near_maturity?: boolean;
  };
  recoveries_to: "principal" | "interest";
  index_curves?: Record<string, RateSpec>;
  external_amounts?: Record<string, RateSpec>;
  delinquency?: RateSpec;
  delinquency_cash_effect?: "none" | "withhold";
}

export interface Deal {
  schema_version: number;
  id: string;
  name: string;
  description: string;
  num_periods: number;
  dates?: DealDates | null;
  collateral: {
    asset_class: string;
    replines: Repline[];
    servicing_fee_rate: number;
    fee_basis: string;
  };
  structure: { classes: BondClass[]; allocation_tree: AllocationNode };
  fees: FeeSpec[];
  reserve_accounts: ReserveAccount[];
  ysoc: YsocConfig | null;
  external_sources: ExternalSource[];
  waterfall: { mode: "split" | "combined"; waterfalls: { name: string; steps: WaterfallStep[] }[] };
  triggers: Trigger[];
  scenarios: Scenario[];
}

export interface DealSummary {
  id: string;
  name: string;
  description: string;
  num_periods: number;
  num_classes: number;
}

export interface RunResult {
  deal_id: string;
  scenario_name: string;
  num_periods: number;
  collateral: Record<string, number[]>;
  bonds: Record<string, (number | string)[]>;
  flows: Record<string, (number | string)[]>;
  residual: number[];
  fees_paid: number[];
  retained: number[];
  accounts: Record<string, (number | string)[]>;
  triggers: Record<string, (number | string | null)[]>;
  externals: Record<string, (number | string)[]>;
  metrics: {
    bonds: Record<
      string,
      {
        wal_years: number | null;
        principal_window: [number, number] | null;
        total_writedown: number;
        yield: number | null;
      }
    >;
    pool: { cum_net_loss: number; cum_net_loss_pct: number; total_residual: number };
  };
}

async function http<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* keep statusText */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

export const api = {
  listDeals: () => http<DealSummary[]>("/api/deals"),
  getDeal: (id: string) => http<Deal>(`/api/deals/${id}`),
  createDeal: (deal: Deal) => http<{ id: string }>("/api/deals", { method: "POST", body: JSON.stringify(deal) }),
  updateDeal: (deal: Deal) =>
    http<{ id: string }>(`/api/deals/${deal.id}`, { method: "PUT", body: JSON.stringify(deal) }),
  deleteDeal: (id: string) => http<{ deleted: string }>(`/api/deals/${id}`, { method: "DELETE" }),
  cloneDeal: (id: string, newId: string) =>
    http<{ id: string }>(`/api/deals/${id}/clone`, { method: "POST", body: JSON.stringify({ new_id: newId }) }),
  listTemplates: () => http<{ template: string; name: string; description: string }[]>("/api/templates"),
  getTemplate: (t: string) => http<Deal>(`/api/templates/${t}`),
  validateDeal: (deal: Deal) =>
    http<{ valid: boolean; runnable?: boolean; errors: string[] }>("/api/deals/validate", {
      method: "POST",
      body: JSON.stringify(deal),
    }),
  runDeal: (id: string, scenario: string) =>
    http<RunResult>(`/api/deals/${id}/run`, { method: "POST", body: JSON.stringify({ scenario }) }),
  breakeven: (id: string, scenario: string) =>
    http<BreakevenResult>(`/api/deals/${id}/analytics/breakeven`, {
      method: "POST",
      body: JSON.stringify({ scenario }),
    }),
  matrix: (id: string, scenario: string, prepay_mults?: number[], loss_mults?: number[]) =>
    http<MatrixResult>(`/api/deals/${id}/analytics/matrix`, {
      method: "POST",
      body: JSON.stringify({ scenario, prepay_mults, loss_mults }),
    }),
  priceYield: (id: string, scenario: string, prices?: number[]) =>
    http<PriceYieldResult>(`/api/deals/${id}/analytics/price-yield`, {
      method: "POST",
      body: JSON.stringify({ scenario, prices }),
    }),
};

export interface BreakevenResult {
  dial: "cnl_level" | "cdr_multiplier";
  base: number;
  cap: number;
  runs: number;
  classes: Record<string, { writedown: number | null; interest_shortfall: number | null }>;
}

export interface MatrixCell {
  prepay_mult: number;
  loss_mult: number;
  pool_cnl_pct: number;
  classes: Record<string, { wal_years: number | null; yield: number | null; writedown: number }>;
}

export interface MatrixResult {
  scenario: string;
  prepay_mults: number[];
  loss_mults: number[];
  class_ids: string[];
  cells: MatrixCell[][];
}

export interface PriceYieldResult {
  scenario: string;
  prices: number[];
  classes: Record<string, { wal_years: number | null; yields: Record<string, number | null> }>;
}
