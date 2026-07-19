import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, type MatrixResult } from "../api/client";

const pct = (x: number | null | undefined, digits = 2) =>
  x == null ? "—" : `${(x * 100).toFixed(digits)}%`;
const num = (x: number | null | undefined, digits = 2) =>
  x == null ? "—" : x.toLocaleString(undefined, { maximumFractionDigits: digits });

export default function AnalyticsPage() {
  const { dealId = "", scenario = "" } = useParams();

  const deal = useQuery({ queryKey: ["deal", dealId], queryFn: () => api.getDeal(dealId) });
  const scen = scenario || deal.data?.scenarios[0]?.name || "base";

  const breakeven = useQuery({
    queryKey: ["breakeven", dealId, scen],
    queryFn: () => api.breakeven(dealId, scen),
    enabled: !!deal.data,
    staleTime: Infinity,
  });
  const matrix = useQuery({
    queryKey: ["matrix", dealId, scen],
    queryFn: () => api.matrix(dealId, scen),
    enabled: !!deal.data,
    staleTime: Infinity,
  });
  const priceYield = useQuery({
    queryKey: ["priceYield", dealId, scen],
    queryFn: () => api.priceYield(dealId, scen),
    enabled: !!deal.data,
    staleTime: Infinity,
  });

  if (deal.isLoading) return <div className="text-slate-500">Loading…</div>;
  if (deal.error) return <div className="text-red-600">{String(deal.error)}</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">
          {dealId} · analytics <span className="text-slate-500">({scen})</span>
        </h1>
        <div className="flex items-center gap-2">
          <select className="input w-auto" value={scen}
            onChange={(e) => { window.location.href = `/deals/${dealId}/analytics/${e.target.value}`; }}>
            {deal.data!.scenarios.map((s) => <option key={s.name}>{s.name}</option>)}
          </select>
          <Link to={`/deals/${dealId}`} className="btn">← Back to editor</Link>
        </div>
      </div>

      <div className="card">
        <h2 className="mb-2 text-sm font-semibold text-slate-700">
          Loss breakeven per class
          {breakeven.data &&
            ` (dial: ${breakeven.data.dial === "cnl_level" ? "cumulative net loss level" : "CDR multiplier"}, base ${
              breakeven.data.dial === "cnl_level" ? pct(breakeven.data.base) : `${breakeven.data.base}x`
            })`}
        </h2>
        {breakeven.isLoading && <div className="text-sm text-slate-500">Solving (bisection over full deal runs)…</div>}
        {breakeven.error && <div className="text-sm text-red-600">{String(breakeven.error)}</div>}
        {breakeven.data && (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-500">
                <th className="py-1">Class</th>
                <th>First $ of writedown (principal breakeven)</th>
                <th>First missed timely interest</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(breakeven.data.classes).map(([cid, ev]) => {
                const fmt = (x: number | null) =>
                  x == null
                    ? "survives cap"
                    : breakeven.data!.dial === "cnl_level"
                      ? `${(x * 100).toFixed(2)}% CNL`
                      : `${x.toFixed(2)}x base CDR`;
                return (
                  <tr key={cid} className="border-b border-slate-100">
                    <td className="py-1 font-medium">{cid}</td>
                    <td className={ev.writedown != null ? "" : "text-emerald-700"}>{fmt(ev.writedown)}</td>
                    <td className={ev.interest_shortfall != null ? "" : "text-emerald-700"}>
                      {fmt(ev.interest_shortfall)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2 className="mb-2 text-sm font-semibold text-slate-700">
          Sensitivity matrix (rows: prepay ×, columns: loss ×)
        </h2>
        {matrix.isLoading && <div className="text-sm text-slate-500">Running grid…</div>}
        {matrix.error && <div className="text-sm text-red-600">{String(matrix.error)}</div>}
        {matrix.data && <MatrixView mx={matrix.data} />}
      </div>

      <div className="card">
        <h2 className="mb-2 text-sm font-semibold text-slate-700">
          Price / yield (base scenario cashflows)
        </h2>
        {priceYield.isLoading && <div className="text-sm text-slate-500">Computing…</div>}
        {priceYield.error && <div className="text-sm text-red-600">{String(priceYield.error)}</div>}
        {priceYield.data && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-500">
                  <th className="py-1">Class</th>
                  <th>WAL</th>
                  {priceYield.data.prices.map((p) => <th key={p}>{p.toFixed(2)}</th>)}
                </tr>
              </thead>
              <tbody>
                {Object.entries(priceYield.data.classes).map(([cid, row]) => (
                  <tr key={cid} className="border-b border-slate-100">
                    <td className="py-1 font-medium">{cid}</td>
                    <td>{num(row.wal_years)}y</td>
                    {priceYield.data!.prices.map((p) => (
                      <td key={p}>{pct(row.yields[String(p)], 3)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function MatrixView({ mx }: { mx: MatrixResult }) {
  const [cid, setCid] = useState(mx.class_ids[0]);
  const [metric, setMetric] = useState<"wal_years" | "yield" | "writedown">("wal_years");

  const cell = (i: number, j: number) => {
    const c = mx.cells[i][j].classes[cid];
    if (metric === "wal_years") return num(c.wal_years);
    if (metric === "yield") return pct(c.yield, 2);
    return c.writedown > 0 ? num(c.writedown, 0) : "—";
  };
  const broken = (i: number, j: number) => mx.cells[i][j].classes[cid].writedown > 0;

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <select className="input w-28" value={cid} onChange={(e) => setCid(e.target.value)}>
          {mx.class_ids.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select className="input w-36" value={metric}
          onChange={(e) => setMetric(e.target.value as typeof metric)}>
          <option value="wal_years">WAL (years)</option>
          <option value="yield">Yield</option>
          <option value="writedown">Writedown ($)</option>
        </select>
      </div>
      <table className="text-sm">
        <thead>
          <tr className="text-xs uppercase text-slate-500">
            <th className="px-2 py-1 text-left">prepay \ loss</th>
            {mx.loss_mults.map((m) => <th key={m} className="px-3">{m}x</th>)}
          </tr>
        </thead>
        <tbody>
          {mx.prepay_mults.map((p, i) => (
            <tr key={p}>
              <td className="px-2 py-1 text-xs font-medium text-slate-500">{p}x</td>
              {mx.loss_mults.map((_, j) => (
                <td key={j}
                  className={`px-3 py-1 text-right tabular-nums ${broken(i, j) ? "bg-red-50 text-red-700" : ""}`}>
                  {cell(i, j)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-slate-500">
        Red cells: the selected class takes a writedown. Pool CNL at base loss:{" "}
        {pct(mx.cells[0]?.[mx.loss_mults.indexOf(1.0)]?.pool_cnl_pct ?? null)}
      </p>
    </div>
  );
}
