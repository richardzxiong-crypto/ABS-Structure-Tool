import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";

export default function DealLibraryPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const deals = useQuery({ queryKey: ["deals"], queryFn: api.listDeals });
  const templates = useQuery({ queryKey: ["templates"], queryFn: api.listTemplates });
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["deals"] });

  const createFromTemplate = useMutation({
    mutationFn: async (template: string) => {
      const id = prompt("New deal id (letters, digits, -, _):", `${template}-${Date.now() % 10000}`);
      if (!id) return null;
      const deal = await api.getTemplate(template);
      await api.createDeal({ ...deal, id, name: id });
      return id;
    },
    onSuccess: (id) => {
      invalidate();
      if (id) navigate(`/deals/${id}`);
    },
    onError: (e: Error) => setError(e.message),
  });

  const cloneDeal = useMutation({
    mutationFn: async (id: string) => {
      const newId = prompt("Clone as id:", `${id}-copy`);
      if (!newId) return;
      await api.cloneDeal(id, newId);
    },
    onSuccess: invalidate,
    onError: (e: Error) => setError(e.message),
  });

  const deleteDeal = useMutation({
    mutationFn: async (id: string) => {
      if (confirm(`Delete deal ${id}?`)) await api.deleteDeal(id);
    },
    onSuccess: invalidate,
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Deal Library</h1>
        <div className="flex gap-2">
          {templates.data?.map((t) => (
            <button key={t.template} className="btn-primary" title={t.description}
              onClick={() => createFromTemplate.mutate(t.template)}>
              New from {t.template}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded border border-red-300 bg-red-50 p-2 text-sm text-red-700"
          onClick={() => setError(null)}>
          {error}
        </div>
      )}

      <div className="card p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-500">
              <th className="px-4 py-2">Id</th>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">Periods</th>
              <th className="px-4 py-2">Classes</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {deals.data?.map((d) => (
              <tr key={d.id} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="px-4 py-2 font-mono text-blue-700">
                  <button onClick={() => navigate(`/deals/${d.id}`)}>{d.id}</button>
                </td>
                <td className="px-4 py-2">{d.name}</td>
                <td className="px-4 py-2">{d.num_periods}</td>
                <td className="px-4 py-2">{d.num_classes}</td>
                <td className="px-4 py-2 text-right">
                  <button className="btn-ghost" onClick={() => cloneDeal.mutate(d.id)}>Clone</button>
                  <button className="btn-ghost text-red-600" onClick={() => deleteDeal.mutate(d.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {deals.data?.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                  No deals yet - create one from a template.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
