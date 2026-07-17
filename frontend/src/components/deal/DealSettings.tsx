import type { Deal, FeeSpec, ReserveAccount } from "../../api/client";

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
