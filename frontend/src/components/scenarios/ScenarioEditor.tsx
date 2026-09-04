import { useState } from "react";

import type { CumLossDefaults, Deal, RateSpec, Scenario } from "../../api/client";

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
  const cl = scen.loss.defaults.type === "cum_loss" ? (scen.loss.defaults as CumLossDefaults) : null;

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
          <div className="flex flex-wrap gap-3">
            <div>
              <label className="label">
                Speed ({scen.prepay.speed_unit === "abs" ? "ABS, monthly" : "CPR, annual"})
              </label>
              <input className="input w-28" type="number" step="0.005"
                value={scen.prepay.speed.type === "scalar" ? scen.prepay.speed.value : undefined}
                disabled={scen.prepay.speed.type !== "scalar"}
                placeholder={scen.prepay.speed.type !== "scalar" ? `(${scen.prepay.speed.type})` : ""}
                onChange={(e) => patch((s) => { s.prepay.speed = { type: "scalar", value: Number(e.target.value) }; })} />
            </div>
            <div>
              <label className="label">Unit</label>
              <select className="input w-24" value={scen.prepay.speed_unit ?? "cpr"}
                onChange={(e) => patch((s) => { s.prepay.speed_unit = e.target.value as "cpr" | "abs"; })}>
                <option>cpr</option>
                <option>abs</option>
              </select>
            </div>
            <div>
              <label className="label">Speed type</label>
              <select className="input w-28" value={scen.prepay.speed_type}
                onChange={(e) => patch((s) => { s.prepay.speed_type = e.target.value as "voluntary" | "all_in"; })}>
                <option>voluntary</option>
                <option>all_in</option>
              </select>
            </div>
            <div>
              <label className="label">Prepay base</label>
              <select className="input w-40" value={scen.prepay.prepay_base ?? "net_of_defaults"}
                onChange={(e) =>
                  patch((s) => {
                    s.prepay.prepay_base = e.target.value as "net_of_defaults" | "gross_of_defaults";
                  })
                }>
                <option>net_of_defaults</option>
                <option value="gross_of_defaults">gross_of_defaults (Intex)</option>
              </select>
            </div>
          </div>
        </div>

        <div className="card space-y-3">
          <h2 className="text-sm font-semibold text-slate-700">Losses</h2>
          <div className="flex flex-wrap gap-3">
            <div>
              <label className="label">Default model</label>
              <select className="input w-28" value={scen.loss.defaults.type}
                onChange={(e) =>
                  patch((s) => {
                    s.loss.defaults =
                      e.target.value === "cdr"
                        ? { type: "cdr", cdr: { type: "scalar", value: 0.02 } }
                        : {
                            type: "cum_loss", cum_net_loss: 0.02, timing: [40, 35, 20, 5],
                            timing_unit: "annual", timing_applies_to: "defaults",
                            method: "aggregate_MDR", allocation: "repline",
                          };
                  })
                }>
                <option>cdr</option>
                <option>cum_loss</option>
              </select>
            </div>
            {cdr && (
              <div>
                <label className="label">CDR (annual)</label>
                <input className="input w-24" type="number" step="0.005"
                  value={cdr.cdr.type === "scalar" ? cdr.cdr.value : undefined}
                  disabled={cdr.cdr.type !== "scalar"}
                  onChange={(e) => patch((s) => { s.loss.defaults = { type: "cdr", cdr: { type: "scalar", value: Number(e.target.value) } }; })} />
              </div>
            )}
            {cl && (
              <>
                <div>
                  <label className="label">Cum net loss</label>
                  <input className="input w-24" type="number" step="0.0025" value={cl.cum_net_loss}
                    onChange={(e) => patch((s) => { (s.loss.defaults as CumLossDefaults).cum_net_loss = Number(e.target.value); })} />
                </div>
                <div>
                  <label className="label">Timing (comma-sep)</label>
                  <input className="input w-36" value={cl.timing.join(",")}
                    onChange={(e) =>
                      patch((s) => {
                        (s.loss.defaults as CumLossDefaults).timing = e.target.value
                          .split(",").map((x) => Number(x.trim())).filter((x) => !Number.isNaN(x));
                      })
                    } />
                </div>
                <div>
                  <label className="label">Timing unit</label>
                  <select className="input w-24" value={cl.timing_unit ?? "period"}
                    onChange={(e) => patch((s) => { (s.loss.defaults as CumLossDefaults).timing_unit = e.target.value as "period" | "annual"; })}>
                    <option>period</option>
                    <option>annual</option>
                  </select>
                </div>
                <div>
                  <label className="label">Timing positions</label>
                  <select className="input w-28" value={cl.timing_applies_to ?? "defaults"}
                    onChange={(e) => patch((s) => { (s.loss.defaults as CumLossDefaults).timing_applies_to = e.target.value as "defaults" | "losses"; })}>
                    <option>defaults</option>
                    <option value="losses">losses (Intex)</option>
                  </select>
                </div>
                <div>
                  <label className="label">Method</label>
                  <select className="input w-40" value={cl.method}
                    onChange={(e) => patch((s) => { (s.loss.defaults as CumLossDefaults).method = e.target.value as CumLossDefaults["method"]; })}>
                    <option value="aggregate_MDR">aggregate_MDR (fit loss)</option>
                    <option value="original_MDR">original_MDR (rate path)</option>
                  </select>
                </div>
                <div>
                  <label className="label">Allocation</label>
                  <select className="input w-28" value={cl.allocation ?? "repline"}
                    onChange={(e) => patch((s) => { (s.loss.defaults as CumLossDefaults).allocation = e.target.value as "repline" | "pool"; })}>
                    <option>repline</option>
                    <option value="pool">pool (Intex)</option>
                  </select>
                </div>
              </>
            )}
            <div>
              <label className="label">Severity</label>
              <input className="input w-20" type="number" step="0.05"
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
              <label className="label">Recovery lag from</label>
              <select className="input w-32" value={scen.loss.recovery_lag_from ?? "charge_off"}
                onChange={(e) => patch((s) => { s.loss.recovery_lag_from = e.target.value as "charge_off" | "default"; })}>
                <option>charge_off</option>
                <option value="default">default (Intex)</option>
              </select>
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
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <input type="checkbox" checked={scen.loss.suppress_defaults_near_maturity ?? false}
              onChange={(e) => patch((s) => { s.loss.suppress_defaults_near_maturity = e.target.checked; })} />
            suppress defaults within charge-off lag of maturity (Intex)
          </label>
        </div>
      </div>

      <div className="card space-y-3">
        <h2 className="text-sm font-semibold text-slate-700">Delinquency</h2>
        <div className="flex flex-wrap gap-3">
          <div>
            <label className="label">Delinquent share of performing balance</label>
            <input className="input w-28" type="number" step="0.005" min={0} max={1}
              value={scen.delinquency?.type === "scalar" ? scen.delinquency.value : undefined}
              disabled={scen.delinquency !== undefined && scen.delinquency.type !== "scalar"}
              placeholder={scen.delinquency && scen.delinquency.type !== "scalar" ? `(${scen.delinquency.type})` : "0"}
              onChange={(e) => patch((s) => { s.delinquency = { type: "scalar", value: Number(e.target.value) }; })} />
          </div>
          <div>
            <label className="label">Cash effect</label>
            <select className="input w-56" value={scen.delinquency_cash_effect ?? "none"}
              onChange={(e) => patch((s) => { s.delinquency_cash_effect = e.target.value as "none" | "withhold"; })}>
              <option value="none">none (triggers only)</option>
              <option value="withhold">withhold (no interest / sched from delinquent share)</option>
            </select>
          </div>
        </div>
        <p className="text-xs text-slate-500">
          A level (e.g. 0.03 = 3% of the pool 60+ days delinquent), not an annual rate. Use the
          JSON editor below for a vector. Delinquency triggers average this ratio over their
          lookback window.
        </p>
      </div>

      <IndexCurvesCard deal={deal} scen={scen} patch={patch} />

      <div className="card">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">
            Advanced (vectors, ramps) - raw JSON
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

function IndexCurvesCard({
  deal,
  scen,
  patch,
}: {
  deal: Deal;
  scen: Scenario;
  patch: (fn: (s: Scenario) => void) => void;
}) {
  const floatingIndices = [
    ...new Set(
      deal.structure.classes
        .filter((c) => c.coupon.type === "floating")
        .map((c) => c.coupon.index ?? "")
        .filter(Boolean),
    ),
  ];
  const swapIndices = (deal.external_sources ?? [])
    .filter((x) => x.kind === "swap")
    .map((x) => x.index ?? "")
    .filter(Boolean);
  const curves = scen.index_curves ?? {};
  const names = [...new Set([...Object.keys(curves), ...floatingIndices, ...swapIndices])];
  if (names.length === 0) return null;

  const describe = (r: RateSpec | undefined) =>
    !r ? "missing" : r.type === "scalar" ? `scalar ${r.value}` : r.type === "vector" ? `vector · ${r.values?.length ?? 0} pts` : `ramp ${r.start}→${r.end}`;

  return (
    <div className="card space-y-2">
      <h2 className="text-sm font-semibold text-slate-700">
        Index curves (floating coupons: rate = index + margin)
      </h2>
      {names.map((name) => {
        const curve = curves[name];
        return (
          <div key={name} className="flex flex-wrap items-end gap-2 rounded border border-slate-200 bg-slate-50 p-2">
            <div className="w-36 text-sm font-medium text-slate-700">{name}</div>
            <div className="text-xs text-slate-500">{describe(curve)}</div>
            <div>
              <label className="label">Values (decimal, comma-sep; single value = flat)</label>
              <input className="input w-96 font-mono text-xs"
                defaultValue={
                  curve?.type === "vector" ? (curve.values ?? []).map((v) => +v.toFixed(6)).join(",")
                  : curve?.type === "scalar" ? String(curve.value)
                  : ""
                }
                onBlur={(e) => {
                  const vals = e.target.value.split(",").map((x) => Number(x.trim())).filter((x) => !Number.isNaN(x));
                  if (vals.length === 0) return;
                  patch((s) => {
                    s.index_curves = s.index_curves ?? {};
                    s.index_curves[name] =
                      vals.length === 1 ? { type: "scalar", value: vals[0] } : { type: "vector", values: vals };
                  });
                }} />
            </div>
            {!curve && (
              <span className="text-xs text-red-600">required by a floating class or swap in this scenario</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
