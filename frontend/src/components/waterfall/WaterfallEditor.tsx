import type { Deal, WaterfallStep } from "../../api/client";

interface Props {
  deal: Deal;
  update: (fn: (draft: Deal) => void) => void;
}

const SOURCES = ["interest_collections", "principal_collections", "total_collections"];
const STEP_TYPES = ["pay_fees", "pay_interest", "pay_interest_shortfall", "pay_principal", "release_residual"];
const AMOUNT_RULES = ["collections", "regular_pda", "priority_pda", "turbo"];

export default function WaterfallEditor({ deal, update }: Props) {
  return (
    <div className="space-y-6">
      {deal.waterfall.waterfalls.map((wf, wi) => (
        <div key={wf.name} className="card">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">
              {wf.name} waterfall
            </h2>
            <button
              className="btn"
              onClick={() =>
                update((d) => {
                  d.waterfall.waterfalls[wi].steps.push({
                    type: "pay_interest",
                    id: `step_${Date.now() % 100000}`,
                    label: "",
                    source: "interest_collections",
                    targets: [d.structure.classes[0]?.id ?? ""],
                  });
                })
              }>
              + Add step
            </button>
          </div>

          <div className="space-y-2">
            {wf.steps.map((step, si) => (
              <StepRow key={step.id} step={step} deal={deal}
                onChange={(next) =>
                  update((d) => {
                    d.waterfall.waterfalls[wi].steps[si] = next;
                  })
                }
                onMove={(dir) =>
                  update((d) => {
                    const steps = d.waterfall.waterfalls[wi].steps;
                    const j = si + dir;
                    if (j < 0 || j >= steps.length) return;
                    [steps[si], steps[j]] = [steps[j], steps[si]];
                  })
                }
                onRemove={() =>
                  update((d) => {
                    d.waterfall.waterfalls[wi].steps.splice(si, 1);
                  })
                }
              />
            ))}
          </div>
        </div>
      ))}
      <p className="text-xs text-slate-500">
        Each step: source → action → targets (priority order; a pro-rata group in the
        allocation tree overrides listed order within that group).
      </p>
    </div>
  );
}

function StepRow({
  step,
  deal,
  onChange,
  onMove,
  onRemove,
}: {
  step: WaterfallStep;
  deal: Deal;
  onChange: (s: WaterfallStep) => void;
  onMove: (dir: -1 | 1) => void;
  onRemove: () => void;
}) {
  const set = (patch: Partial<WaterfallStep>) => onChange({ ...step, ...patch });

  return (
    <div className="flex flex-wrap items-end gap-2 rounded border border-slate-200 bg-slate-50 p-2">
      <div className="flex flex-col gap-1">
        <button className="btn-ghost py-0 leading-none" onClick={() => onMove(-1)}>▲</button>
        <button className="btn-ghost py-0 leading-none" onClick={() => onMove(1)}>▼</button>
      </div>
      <div>
        <label className="label">Action</label>
        <select className="input w-44" value={step.type}
          onChange={(e) => {
            const type = e.target.value;
            const next: WaterfallStep = { type, id: step.id, label: step.label, source: step.source };
            if (type === "pay_fees") next.fees = deal.fees.map((f) => f.name);
            else if (type === "pay_principal") {
              next.targets = step.targets ?? [deal.structure.classes[0]?.id ?? ""];
              next.amount_rule = "collections";
              next.target_oc = { kind: "fixed", value: 0 };
              next.pool_basis = "trust";
            } else if (type !== "release_residual") next.targets = step.targets ?? [];
            onChange(next);
          }}>
          {STEP_TYPES.map((t) => <option key={t}>{t}</option>)}
        </select>
      </div>
      <div>
        <label className="label">Source</label>
        <select className="input w-48" value={step.source} onChange={(e) => set({ source: e.target.value })}>
          {SOURCES.map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      {step.type === "pay_fees" && (
        <div>
          <label className="label">Fees (comma-sep)</label>
          <input className="input w-40" value={(step.fees ?? []).join(",")}
            onChange={(e) => set({ fees: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
        </div>
      )}
      {(step.type === "pay_interest" || step.type === "pay_interest_shortfall" || step.type === "pay_principal") && (
        <div>
          <label className="label">Targets (priority order)</label>
          <input className="input w-48" value={(step.targets ?? []).join(",")}
            onChange={(e) => set({ targets: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
        </div>
      )}
      {step.type === "pay_principal" && (
        <>
          <div>
            <label className="label">Amount rule</label>
            <select className="input w-36" value={step.amount_rule}
              onChange={(e) => set({ amount_rule: e.target.value })}>
              {AMOUNT_RULES.map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
          {step.amount_rule === "regular_pda" && (
            <div>
              <label className="label">Target OC</label>
              <input className="input w-28" type="number"
                value={step.target_oc?.value ?? 0}
                onChange={(e) =>
                  set({ target_oc: { kind: step.target_oc?.kind ?? "fixed", value: Number(e.target.value) } })
                } />
            </div>
          )}
        </>
      )}
      <div className="grow">
        <label className="label">Label</label>
        <input className="input" value={step.label}
          onChange={(e) => set({ label: e.target.value })} placeholder={step.id} />
      </div>
      <button className="btn-ghost text-red-600" onClick={onRemove}>✕</button>
    </div>
  );
}
