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
  coupon: { type: "fixed" | "floating"; rate?: number; index?: string; margin?: number };
  day_count: string;
  price: number | null;
}

export interface AllocationNode {
  type: "class" | "group";
  class_id?: string;
  name?: string;
  mode?: "sequential" | "pro_rata" | "target_balance";
  children?: AllocationNode[];
  pro_rata_basis?: "current" | "original";
}

export interface WaterfallStep {
  type: string;
  id: string;
  label: string;
  source: string;
  fees?: string[];
  targets?: string[];
  amount_rule?: string;
  target_oc?: { kind: string; value: number };
  pool_basis?: string;
  to?: string;
  [key: string]: unknown;
}

export interface Scenario {
  name: string;
  prepay: { speed: RateSpec; speed_type: "voluntary" | "all_in" };
  loss: {
    defaults:
      | { type: "cdr"; cdr: RateSpec }
      | { type: "cum_loss"; cum_net_loss: number; timing: number[]; method: string };
    severity: RateSpec;
    charge_off_lag: number;
    recovery_lag: number;
  };
  recoveries_to: "principal" | "interest";
  index_curves?: Record<string, RateSpec>;
}

export interface Deal {
  schema_version: number;
  id: string;
  name: string;
  description: string;
  num_periods: number;
  collateral: {
    asset_class: string;
    replines: Repline[];
    servicing_fee_rate: number;
    fee_basis: string;
  };
  structure: { classes: BondClass[]; allocation_tree: AllocationNode };
  fees: { name: string; rate: number; fixed: number; basis: string }[];
  reserve_accounts: unknown[];
  ysoc: unknown | null;
  waterfall: { mode: "split" | "combined"; waterfalls: { name: string; steps: WaterfallStep[] }[] };
  triggers: unknown[];
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
};
