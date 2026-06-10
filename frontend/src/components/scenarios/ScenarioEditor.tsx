import { useState } from "react";

import type { Deal, Scenario } from "../../api/client";

interface Props {
  deal: Deal;
  update: (fn: (draft: Deal) => void) => void;
}

export default function ScenarioEditor({ deal, update }: Props) {
  const [active, setActive] = useState(0);
  const [advanced, setAdvanced] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scen = deal.scenarios[active];
  if (!scen) return null;

  const patch = (fn: (s: Scenario) => void) =>
    update((d) => {
      fn(d.scenarios[active]);
    });

  const cdr = scen.loss.defaults.type === "cdr" ? scen.loss.defaults : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {deal.scenarios.map((s, i) => (
          <button key={s.name}
            className={`rounded px-3 py-1 text-sm ${i === active ? "bg-blue-600 text-white" : "bg-white text-slate-600 border border-slate-300"}`}
            onClick={() => { setActive(i); setAdvanced(null); }}>
            {s.name}
          </button>
        ))}
        <button className="btn-ghost"
          onClick={() =>
            update((d) => {
              const copy = structuredClone(d.scenarios[active]);
              copy.name = `${copy.name}-copy`;
              d.scenarios.push(copy);
            })
          }>
          + Duplicate
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="card space-y-3">
          <h2 className="text-sm font-semibold text-slate-700">Prepayment</h2>
          <div className="flex gap-3">
            <div>
              <label className="label">CPR (annual, decimal)</label>
              <input className="input w-32" type="number" step="0.01"
                value={scen.prepay.speed.type === "scalar" ? scen.prepay.speed.value : undefined}
                disabled={scen.prepay.speed.type !== "scalar"}
                placeholder={scen.prepay.speed.type !== "scalar" ? `(${scen.prepay.speed.type})` : ""}
                onChange={(e) => patch((s) => { s.prepay.speed = { type: "scalar", value: Number(e.target.value) }; })} />
            </div>
            <div>
              <label className="label">Speed type</label>
              <select className="input w-32" value={scen.prepay.speed_type}
                onChange={(e) => patch((s) => { s.prepay.speed_type = e.target.value as "voluntary" | "all_in"; })}>
                <option>voluntary</option>
                <option>all_in</option>
              </select>
            </div>
          </div>
        </div>

        <div className="card space-y-3">
          <h2 className="text-sm font-semibold text-slate-700">Losses</h2>
          <div className="flex flex-wrap gap-3">
            <div>
              <label className="label">CDR (annual)</label>
              <input className="input w-28" type="number" step="0.005"
                value={cdr && cdr.cdr.type === "scalar" ? cdr.cdr.value : undefined}
                disabled={!cdr || cdr.cdr.type !== "scalar"}
                placeholder={!cdr ? "(cum_loss)" : ""}
                onChange={(e) => patch((s) => { s.loss.defaults = { type: "cdr", cdr: { type: "scalar", value: Number(e.target.value) } }; })} />
            </div>
            <div>
              <label className="label">Severity</label>
              <input className="input w-24" type="number" step="0.05"
                value={scen.loss.severity.type === "scalar" ? scen.loss.severity.value : undefined}
                disabled={scen.loss.severity.type !== "scalar"}
                onChange={(e) => patch((s) => { s.loss.severity = { type: "scalar", value: Number(e.target.value) }; })} />
            </div>
            <div>
              <label className="label">Charge-off lag</label>
              <input className="input w-20" type="number"
                value={scen.loss.charge_off_lag}
                onChange={(e) => patch((s) => { s.loss.charge_off_lag = Number(e.target.value); })} />
            </div>
            <div>
              <label className="label">Recovery lag</label>
              <input className="input w-20" type="number"
                value={scen.loss.recovery_lag}
                onChange={(e) => patch((s) => { s.loss.recovery_lag = Number(e.target.value); })} />
            </div>
            <div>
              <label className="label">Recoveries to</label>
              <select className="input w-28" value={scen.recoveries_to}
                onChange={(e) => patch((s) => { s.recoveries_to = e.target.value as "principal" | "interest"; })}>
                <option>principal</option>
                <option>interest</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">
            Advanced (vectors, ramps, cum-loss timing) - raw JSON
          </h2>
          {advanced === null ? (
            <button className="btn-ghost" onClick={() => setAdvanced(JSON.stringify(scen, null, 2))}>
              Edit JSON
            </button>
          ) : (
            <div className="flex gap-2">
              <button className="btn-ghost" onClick={() => { setAdvanced(null); setError(null); }}>Cancel</button>
              <button className="btn-primary"
                onClick={() => {
                  try {
                    const parsed = JSON.parse(advanced);
                    update((d) => { d.scenarios[active] = parsed; });
                    setAdvanced(null);
                    setError(null);
                  } catch (e) {
                    setError(String(e));
                  }
                }}>
                Apply
              </button>
            </div>
          )}
        </div>
        {error && <div className="mb-2 text-sm text-red-600">{error}</div>}
        {advanced !== null && (
          <textarea className="input h-72 font-mono text-xs" value={advanced}
            onChange={(e) => setAdvanced(e.target.value)} />
        )}
      </div>
    </div>
  );
}
