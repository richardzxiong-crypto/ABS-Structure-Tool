import type { Deal, ExternalSource, FeeSpec, ReserveAccount, Trigger } from "../../api/client";

interface Props {
  deal: Deal;
  update: (fn: (draft: Deal) => void) => void;
}

const BASES = ["trust", "performing", "adjusted"] as const;

export default function DealSettings({ deal, update }: Props) {
  return (
    <div className="space-y-4">
      <DatesCard deal={deal} update={update} />
      <div className="grid grid-cols-2 gap-4">
        <FeesCard deal={deal} update={update} />
        <ReservesCard deal={deal} update={update} />
      </div>
      <YsocCard deal={deal} update={update} />
      <ExternalSourcesCard deal={deal} update={update} />
      <TriggersCard deal={deal} update={update} />
    </div>
  );
}

const TRIGGER_TYPES = ["cum_net_loss", "delinquency", "pool_factor", "oc_test", "ic_test"] as const;
const OPERATORS = ["<", "<=", ">", ">="] as const;

function TriggersCard({ deal, update }: Props) {
  return (
    <div className="card space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">
          Triggers (waterfall steps can be conditioned on pass / fail)
        </h2>
        <button className="btn"
          onClick={() =>
            update((d) => {
              d.triggers.push({
                type: "cum_net_loss", name: `trigger_${d.triggers.length + 1}`,
                curable: true, operator: "<=", schedule: [],
              });
            })
          }>
          + Add
        </button>
      </div>
      {deal.triggers.length === 0 && (
        <p className="text-xs text-slate-500">
          No triggers. Add one (e.g. a cumulative-net-loss or delinquency test) and reference
          it from a waterfall step's condition to model pro-rata → sequential switches or
          cash traps. Delinquency tests read the scenario's delinquency vector.
        </p>
      )}
      {deal.triggers.map((t: Trigger, i) => (
        <div key={i} className="flex flex-wrap items-end gap-2 rounded border border-slate-200 bg-slate-50 p-2">
          <div>
            <label className="label">Name</label>
            <input className="input w-32" value={t.name}
              onChange={(e) => update((d) => { d.triggers[i].name = e.target.value; })} />
          </div>
          <div>
            <label className="label">Type</label>
            <select className="input w-36" value={t.type}
              onChange={(e) =>
                update((d) => {
                  const type = e.target.value as Trigger["type"];
                  d.triggers[i] = type === "cum_net_loss"
                    ? { type, name: t.name, curable: t.curable, operator: "<=", schedule: [] }
                    : type === "delinquency"
                    ? { type, name: t.name, curable: t.curable, operator: "<=", threshold: 0.05,
                        basis: "trust", lookback: 3 }
                    : { type, name: t.name, curable: t.curable,
                        operator: type === "pool_factor" ? ">" : ">=",
                        threshold: 0, ...(type !== "ic_test" ? { basis: "trust" as const } : {}) };
                })
              }>
              {TRIGGER_TYPES.map((k) => <option key={k}>{k}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Passes when measured is</label>
            <select className="input w-20" value={t.operator ?? "<="}
              onChange={(e) => update((d) => { d.triggers[i].operator = e.target.value as Trigger["operator"]; })}>
              {OPERATORS.map((o) => <option key={o}>{o}</option>)}
            </select>
          </div>
          {t.type === "cum_net_loss" ? (
            <div>
              <label className="label">Schedule (period:threshold, comma-sep)</label>
              <input className="input w-64 font-mono text-xs"
                value={(t.schedule ?? []).map(([p, v]) => `${p}:${v}`).join(", ")}
                onChange={(e) =>
                  update((d) => {
                    d.triggers[i].schedule = e.target.value
                      .split(",").map((x) => x.trim()).filter(Boolean)
                      .map((pair) => {
                        const [p, v] = pair.split(":");
                        return [Number(p), Number(v)] as [number, number];
                      })
                      .filter(([p, v]) => !Number.isNaN(p) && !Number.isNaN(v));
                  })
                }
                placeholder="12:0.02, 24:0.045" />
            </div>
          ) : (
            <div>
              <label className="label">Threshold</label>
              <input className="input w-24" type="number" step="0.01" value={t.threshold ?? 0}
                onChange={(e) => update((d) => { d.triggers[i].threshold = Number(e.target.value); })} />
            </div>
          )}
          {t.type === "delinquency" && (
            <div>
              <label className="label">Avg. over periods</label>
              <input className="input w-20" type="number" min={1} value={t.lookback ?? 1}
                onChange={(e) => update((d) => { d.triggers[i].lookback = Math.max(1, Number(e.target.value)); })} />
            </div>
          )}
          {(t.type === "pool_factor" || t.type === "oc_test" || t.type === "delinquency") && (
            <div>
              <label className="label">Basis</label>
              <select className="input w-28" value={t.basis ?? "trust"}
                onChange={(e) => update((d) => { d.triggers[i].basis = e.target.value as Trigger["basis"]; })}>
                {BASES.map((b) => <option key={b}>{b}</option>)}
              </select>
            </div>
          )}
          <label className="flex items-center gap-1 pb-2 text-xs text-slate-600">
            <input type="checkbox" checked={t.curable}
              onChange={(e) => update((d) => { d.triggers[i].curable = e.target.checked; })} />
            curable
          </label>
          <button className="btn-ghost text-red-600"
            onClick={() => update((d) => { d.triggers.splice(i, 1); })}>✕</button>
        </div>
      ))}
    </div>
  );
}

function DatesCard({ deal, update }: Props) {
  const dates = deal.dates ?? null;
  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">Payment calendar</h2>
        {dates ? (
          <button className="btn-ghost text-red-600"
            onClick={() => update((d) => { d.dates = null; })}>
            Remove (flat 30/360 monthly)
          </button>
        ) : (
          <button className="btn"
            onClick={() =>
              update((d) => {
                d.dates = {
                  closing_date: new Date().toISOString().slice(0, 10),
                  first_payment_date: new Date().toISOString().slice(0, 10),
                  business_day_adjust: "none",
                };
              })
            }>
            + Add dates
          </button>
        )}
      </div>
      {dates ? (
        <div className="flex flex-wrap gap-3">
          <div>
            <label className="label">Closing date</label>
            <input className="input w-40" type="date" value={dates.closing_date}
              onChange={(e) => update((d) => { d.dates!.closing_date = e.target.value; })} />
          </div>
          <div>
            <label className="label">First payment date</label>
            <input className="input w-40" type="date" value={dates.first_payment_date}
              onChange={(e) => update((d) => { d.dates!.first_payment_date = e.target.value; })} />
          </div>
          <div>
            <label className="label">Business-day adjust (ACT classes)</label>
            <select className="input w-36" value={dates.business_day_adjust}
              onChange={(e) =>
                update((d) => { d.dates!.business_day_adjust = e.target.value as "none" | "following"; })
              }>
              <option>none</option>
              <option>following</option>
            </select>
          </div>
        </div>
      ) : (
        <p className="text-xs text-slate-500">
          No calendar: every accrual is a flat 1/12 and ACT day counts are rejected.
          Add dates for a short first period and ACT/360 money-market accrual.
        </p>
      )}
    </div>
  );
}

function FeesCard({ deal, update }: Props) {
  return (
    <div className="card space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">Fees (paid via pay_fees steps)</h2>
        <button className="btn"
          onClick={() =>
            update((d) => {
              d.fees.push({ name: `fee_${d.fees.length + 1}`, rate: 0, fixed: 0, basis: "trust" });
            })
          }>
          + Add
        </button>
      </div>
      {deal.fees.length === 0 && <p className="text-xs text-slate-500">No deal-level fees.</p>}
      {deal.fees.map((f: FeeSpec, i) => (
        <div key={i} className="flex flex-wrap items-end gap-2 rounded border border-slate-200 bg-slate-50 p-2">
          <div>
            <label className="label">Name</label>
            <input className="input w-28" value={f.name}
              onChange={(e) => update((d) => { d.fees[i].name = e.target.value; })} />
          </div>
          <div>
            <label className="label">Rate (annual)</label>
            <input className="input w-24" type="number" step="0.0005" value={f.rate}
              onChange={(e) => update((d) => { d.fees[i].rate = Number(e.target.value); })} />
          </div>
          <div>
            <label className="label">Fixed / period</label>
            <input className="input w-24" type="number" value={f.fixed}
              onChange={(e) => update((d) => { d.fees[i].fixed = Number(e.target.value); })} />
          </div>
          <div>
            <label className="label">Basis</label>
            <select className="input w-28" value={f.basis}
              onChange={(e) => update((d) => { d.fees[i].basis = e.target.value as FeeSpec["basis"]; })}>
              {BASES.map((b) => <option key={b}>{b}</option>)}
            </select>
          </div>
          <button className="btn-ghost text-red-600"
            onClick={() => update((d) => { d.fees.splice(i, 1); })}>✕</button>
        </div>
      ))}
    </div>
  );
}

function ReservesCard({ deal, update }: Props) {
  return (
    <div className="card space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">Reserve accounts</h2>
        <button className="btn"
          onClick={() =>
            update((d) => {
              d.reserve_accounts.push({
                name: `reserve_${d.reserve_accounts.length + 1}`,
                target_kind: "fixed", target_value: 0, floor: 0, initial_balance: 0,
              });
            })
          }>
          + Add
        </button>
      </div>
      {deal.reserve_accounts.length === 0 && (
        <p className="text-xs text-slate-500">
          No reserve accounts. Steps can draw via source <code>reserve:&lt;name&gt;</code>,
          top up via <code>fund_reserve</code>, and retire notes via <code>retire_bonds</code>.
        </p>
      )}
      {deal.reserve_accounts.map((r: ReserveAccount, i) => (
        <div key={i} className="flex flex-wrap items-end gap-2 rounded border border-slate-200 bg-slate-50 p-2">
          <div>
            <label className="label">Name</label>
            <input className="input w-28" value={r.name}
              onChange={(e) => update((d) => { d.reserve_accounts[i].name = e.target.value; })} />
          </div>
          <div>
            <label className="label">Target kind</label>
            <select className="input w-36" value={r.target_kind}
              onChange={(e) =>
                update((d) => {
                  d.reserve_accounts[i].target_kind = e.target.value as ReserveAccount["target_kind"];
                })
              }>
              <option>fixed</option>
              <option>pct_current_pool</option>
              <option>pct_original_pool</option>
            </select>
          </div>
          <div>
            <label className="label">Target value</label>
            <input className="input w-32" type="number" value={r.target_value}
              onChange={(e) => update((d) => { d.reserve_accounts[i].target_value = Number(e.target.value); })} />
          </div>
          <div>
            <label className="label">Initial balance</label>
            <input className="input w-32" type="number" value={r.initial_balance}
              onChange={(e) => update((d) => { d.reserve_accounts[i].initial_balance = Number(e.target.value); })} />
          </div>
          <button className="btn-ghost text-red-600"
            onClick={() => update((d) => { d.reserve_accounts.splice(i, 1); })}>✕</button>
        </div>
      ))}
    </div>
  );
}

function YsocCard({ deal, update }: Props) {
  const ysoc = deal.ysoc;
  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">
          Yield supplement overcollateralization (YSOC)
        </h2>
        {ysoc ? (
          <button className="btn-ghost text-red-600" onClick={() => update((d) => { d.ysoc = null; })}>
            Remove
          </button>
        ) : (
          <button className="btn"
            onClick={() => update((d) => { d.ysoc = { required_rate: 0.06, basis: "trust" }; })}>
            + Enable
          </button>
        )}
      </div>
      {ysoc ? (
        <div className="flex flex-wrap gap-3">
          <div>
            <label className="label">Required rate</label>
            <input className="input w-28" type="number" step="0.001" value={ysoc.required_rate}
              onChange={(e) => update((d) => { d.ysoc!.required_rate = Number(e.target.value); })} />
          </div>
          <div>
            <label className="label">Stepdown rate (opt.)</label>
            <input className="input w-28" type="number" step="0.001" value={ysoc.stepdown_rate ?? ""}
              onChange={(e) =>
                update((d) => {
                  d.ysoc!.stepdown_rate = e.target.value === "" ? null : Number(e.target.value);
                })
              } />
          </div>
          <div>
            <label className="label">Stepdown when class = 0</label>
            <select className="input w-28" value={ysoc.stepdown_when_class_zero ?? ""}
              onChange={(e) =>
                update((d) => { d.ysoc!.stepdown_when_class_zero = e.target.value || null; })
              }>
              <option value="">—</option>
              {deal.structure.classes.map((c) => <option key={c.id}>{c.id}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Closing YSOA override (opt.)</label>
            <input className="input w-36" type="number" value={ysoc.initial_amount ?? ""}
              placeholder="dynamic"
              onChange={(e) =>
                update((d) => {
                  d.ysoc!.initial_amount = e.target.value === "" ? null : Number(e.target.value);
                })
              } />
          </div>
          <div>
            <label className="label">Basis</label>
            <select className="input w-28" value={ysoc.basis}
              onChange={(e) => update((d) => { d.ysoc!.basis = e.target.value as typeof ysoc.basis; })}>
              {BASES.slice(0, 2).map((b) => <option key={b}>{b}</option>)}
            </select>
          </div>
        </div>
      ) : (
        <p className="text-xs text-slate-500">
          Disabled: the "adjusted" pool basis equals the trust balance. Enable to haircut
          low-APR collateral to its value at the required rate (PDAs, OC targets, and fees
          can then reference the adjusted basis).
        </p>
      )}
    </div>
  );
}

function ExternalSourcesCard({ deal, update }: Props) {
  const sources = deal.external_sources ?? [];
  const setSrc = (i: number, fn: (x: ExternalSource) => void) =>
    update((d) => { fn(d.external_sources[i]); });
  return (
    <div className="card space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">
          External cash sources (steps draw via <code>external:&lt;name&gt;</code>)
        </h2>
        <button className="btn"
          onClick={() =>
            update((d) => {
              d.external_sources = d.external_sources ?? [];
              d.external_sources.push({
                name: `source_${d.external_sources.length + 1}`, kind: "amount",
                amount: { type: "scalar", value: 0 }, start_period: 1, end_period: null,
              });
            })
          }>
          + Add
        </button>
      </div>
      {sources.length === 0 && (
        <p className="text-xs text-slate-500">
          None. Add a fixed per-period amount (sponsor top-up, prefunding release) or an
          interest-rate swap (trust pays fixed, receives index + spread on a class balance;
          net receipts are seeded into the bucket, net payments are paid by listing
          <code> swap:&lt;name&gt;</code> in a pay_fees step). Unused cash is retained unless a
          release_residual step sweeps the bucket.
        </p>
      )}
      {sources.map((x: ExternalSource, i) => (
        <div key={i} className="flex flex-wrap items-end gap-2 rounded border border-slate-200 bg-slate-50 p-2">
          <div>
            <label className="label">Name</label>
            <input className="input w-28" value={x.name}
              onChange={(e) => setSrc(i, (s) => { s.name = e.target.value; })} />
          </div>
          <div>
            <label className="label">Kind</label>
            <select className="input w-24" value={x.kind}
              onChange={(e) =>
                setSrc(i, (s) => {
                  s.kind = e.target.value as ExternalSource["kind"];
                  if (s.kind === "swap") {
                    s.notional_class = s.notional_class ?? deal.structure.classes[0]?.id ?? null;
                    s.index = s.index || "SOFR";
                    s.fixed_rate = s.fixed_rate ?? 0;
                    s.spread = s.spread ?? 0;
                  }
                })
              }>
              <option>amount</option>
              <option>swap</option>
            </select>
          </div>
          {x.kind === "amount" ? (
            <div>
              <label className="label">Amount / period</label>
              <input className="input w-28" type="number"
                value={x.amount.type === "scalar" ? x.amount.value : undefined}
                disabled={x.amount.type !== "scalar"}
                placeholder={x.amount.type !== "scalar" ? `(${x.amount.type})` : ""}
                onChange={(e) => setSrc(i, (s) => { s.amount = { type: "scalar", value: Number(e.target.value) }; })} />
            </div>
          ) : (
            <>
              <div>
                <label className="label">Notional = class balance</label>
                <select className="input w-24" value={x.notional_class ?? ""}
                  onChange={(e) => setSrc(i, (s) => { s.notional_class = e.target.value || null; })}>
                  <option value="">(schedule)</option>
                  {deal.structure.classes.map((c) => <option key={c.id}>{c.id}</option>)}
                </select>
              </div>
              {!x.notional_class && (
                <div>
                  <label className="label">Notional schedule (comma-sep)</label>
                  <input className="input w-40 font-mono text-xs" value={(x.notional_schedule ?? []).join(",")}
                    onChange={(e) =>
                      setSrc(i, (s) => {
                        s.notional_schedule = e.target.value.split(",").map((v) => Number(v.trim())).filter((v) => !Number.isNaN(v));
                      })
                    } />
                </div>
              )}
              <div>
                <label className="label">Pay fixed</label>
                <input className="input w-24" type="number" step="0.0005" value={x.fixed_rate ?? 0}
                  onChange={(e) => setSrc(i, (s) => { s.fixed_rate = Number(e.target.value); })} />
              </div>
              <div>
                <label className="label">Receive index</label>
                <input className="input w-24" value={x.index ?? ""}
                  onChange={(e) => setSrc(i, (s) => { s.index = e.target.value; })} />
              </div>
              <div>
                <label className="label">+ spread</label>
                <input className="input w-24" type="number" step="0.0005" value={x.spread ?? 0}
                  onChange={(e) => setSrc(i, (s) => { s.spread = Number(e.target.value); })} />
              </div>
              <div>
                <label className="label">Day count</label>
                <select className="input w-24" value={x.day_count ?? "30/360"}
                  onChange={(e) => setSrc(i, (s) => { s.day_count = e.target.value as ExternalSource["day_count"]; })}>
                  <option>30/360</option>
                  <option>ACT/360</option>
                  <option>ACT/365</option>
                </select>
              </div>
            </>
          )}
          <div>
            <label className="label">From period</label>
            <input className="input w-20" type="number" min={1} value={x.start_period}
              onChange={(e) => setSrc(i, (s) => { s.start_period = Number(e.target.value); })} />
          </div>
          <div>
            <label className="label">To period (opt.)</label>
            <input className="input w-20" type="number" min={1} value={x.end_period ?? ""}
              onChange={(e) => setSrc(i, (s) => { s.end_period = e.target.value === "" ? null : Number(e.target.value); })} />
          </div>
          <button className="btn-ghost text-red-600"
            onClick={() => update((d) => { d.external_sources.splice(i, 1); })}>✕</button>
        </div>
      ))}
    </div>
  );
}
