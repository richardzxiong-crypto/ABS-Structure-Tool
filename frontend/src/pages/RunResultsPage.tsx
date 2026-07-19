import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import BalanceChart from "../components/charts/BalanceChart";
import CashflowTable from "../components/results/CashflowTable";

const fmt = (x: number | null | undefined, digits = 2) =>
  x == null ? "—" : x.toLocaleString(undefined, { maximumFractionDigits: digits });

export default function RunResultsPage() {
  const { dealId = "", scenario = "base" } = useParams();
  const run = useQuery({
    queryKey: ["run", dealId, scenario],
    queryFn: () => api.runDeal(dealId, scenario),
  });

  if (run.isLoading) return <div className="text-slate-500">Running {dealId} / {scenario}…</div>;
  if (run.error) return <div className="text-red-600">{String(run.error)}</div>;
  const res = run.data!;
  const classIds = Object.keys(res.metrics.bonds);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">
          {dealId} · <span className="text-slate-500">{res.scenario_name}</span>
        </h1>
        <div className="flex gap-2">
          <Link to={`/deals/${dealId}/analytics/${scenario}`} className="btn">Analytics →</Link>
          <Link to={`/deals/${dealId}`} className="btn">← Back to editor</Link>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {classIds.map((cid) => {
          const m = res.metrics.bonds[cid];
          return (
            <div key={cid} className="card">
              <div className="text-xs font-semibold uppercase text-slate-500">Class {cid}</div>
              <div className="mt-1 text-sm text-slate-700">
                <div>WAL: <b>{fmt(m.wal_years, 3)}y</b></div>
                <div>
                  Window:{" "}
                  <b>{m.principal_window ? `${m.principal_window[0]}–${m.principal_window[1]}` : "—"}</b>
                </div>
                <div>Yield: <b>{m.yield != null ? `${(m.yield * 100).toFixed(3)}%` : "—"}</b></div>
                <div className={m.total_writedown > 0 ? "text-red-600" : ""}>
                  Writedown: <b>{fmt(m.total_writedown)}</b>
                </div>
              </div>
            </div>
          );
        })}
        <div className="card">
          <div className="text-xs font-semibold uppercase text-slate-500">Pool</div>
          <div className="mt-1 text-sm text-slate-700">
            <div>Cum net loss: <b>{(res.metrics.pool.cum_net_loss_pct * 100).toFixed(3)}%</b></div>
            <div>Residual: <b>{fmt(res.metrics.pool.total_residual)}</b></div>
          </div>
        </div>
      </div>

      <div className="card">
        <h2 className="mb-2 text-sm font-semibold text-slate-700">Balances</h2>
        <BalanceChart result={res} />
      </div>

      <div className="card">
        <h2 className="mb-2 text-sm font-semibold text-slate-700">Collateral cashflows</h2>
        <CashflowTable columns={res.collateral} />
      </div>

      <div className="card">
        <h2 className="mb-2 text-sm font-semibold text-slate-700">Bond cashflows</h2>
        <CashflowTable columns={res.bonds} />
      </div>

      {Object.keys(res.accounts ?? {}).length > 0 && (
        <div className="card">
          <h2 className="mb-2 text-sm font-semibold text-slate-700">Reserve account balances</h2>
          <CashflowTable columns={res.accounts} />
        </div>
      )}

      <div className="card">
        <h2 className="mb-2 text-sm font-semibold text-slate-700">
          Waterfall flow log (every draw: step → target, due vs paid)
        </h2>
        <CashflowTable columns={res.flows} pageSize={15} />
      </div>
    </div>
  );
}
