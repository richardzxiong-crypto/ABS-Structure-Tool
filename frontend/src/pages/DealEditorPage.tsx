import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import ReplineGrid from "../components/collateral/ReplineGrid";
import DealSettings from "../components/deal/DealSettings";
import ScenarioEditor from "../components/scenarios/ScenarioEditor";
import BondClassGrid from "../components/structure/BondClassGrid";
import WaterfallEditor from "../components/waterfall/WaterfallEditor";
import { useDealEditor } from "../store/dealEditor";

const TABS = ["Deal", "Collateral", "Structure", "Waterfall", "Scenarios"] as const;

export default function DealEditorPage() {
  const { dealId = "" } = useParams();
  const navigate = useNavigate();
  const { deal, dirty, setDeal, update, markSaved } = useDealEditor();
  const [tab, setTab] = useState<(typeof TABS)[number]>("Collateral");
  const [scenario, setScenario] = useState("");
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({ queryKey: ["deal", dealId], queryFn: () => api.getDeal(dealId) });
  useEffect(() => {
    if (query.data) setDeal(query.data);
  }, [query.data, setDeal]);
  useEffect(() => {
    if (deal && !deal.scenarios.some((s) => s.name === scenario)) {
      setScenario(deal.scenarios[0]?.name ?? "");
    }
  }, [deal, scenario]);

  const save = useMutation({
    mutationFn: () => api.updateDeal(deal!),
    onSuccess: () => {
      markSaved();
      setError(null);
    },
    onError: (e: Error) => setError(e.message),
  });

  const run = useMutation({
    mutationFn: async () => {
      if (dirty) await api.updateDeal(deal!);
      markSaved();
      const v = await api.validateDeal(deal!);
      if (!v.valid || v.runnable === false) throw new Error(v.errors.join("; "));
    },
    onSuccess: () => navigate(`/deals/${dealId}/results/${scenario}`),
    onError: (e: Error) => setError(e.message),
  });

  if (query.isLoading || !deal) return <div className="text-slate-500">Loading…</div>;
  if (query.error) return <div className="text-red-600">{String(query.error)}</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">
            {deal.name || deal.id}
            {dirty && <span className="ml-2 text-sm font-normal text-amber-600">● unsaved</span>}
          </h1>
          <p className="text-sm text-slate-500">
            {deal.num_periods} periods · pool{" "}
            {deal.collateral.replines.reduce((s, r) => s + r.balance, 0).toLocaleString()}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select className="input w-auto" value={scenario} onChange={(e) => setScenario(e.target.value)}>
            {deal.scenarios.map((s) => (
              <option key={s.name}>{s.name}</option>
            ))}
          </select>
          <button className="btn" onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
            Save
          </button>
          <button className="btn-primary" onClick={() => run.mutate()} disabled={run.isPending}>
            {run.isPending ? "Running…" : "Run ▶"}
          </button>
        </div>
      </div>

      {error && (
        <div className="cursor-pointer rounded border border-red-300 bg-red-50 p-2 text-sm text-red-700"
          onClick={() => setError(null)}>
          {error}
        </div>
      )}

      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button key={t}
            className={`px-4 py-2 text-sm font-medium ${
              tab === t
                ? "border-b-2 border-blue-600 text-blue-700"
                : "text-slate-500 hover:text-slate-700"
            }`}
            onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      {tab === "Deal" && <DealSettings deal={deal} update={update} />}
      {tab === "Collateral" && <ReplineGrid deal={deal} update={update} />}
      {tab === "Structure" && <BondClassGrid deal={deal} update={update} />}
      {tab === "Waterfall" && <WaterfallEditor deal={deal} update={update} />}
      {tab === "Scenarios" && <ScenarioEditor deal={deal} update={update} />}
    </div>
  );
}
