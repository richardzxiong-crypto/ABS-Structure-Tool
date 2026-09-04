import type { Deal, TargetOCSpec, WaterfallStep } from "../../api/client";

interface Props {
  deal: Deal;
  update: (fn: (draft: Deal) => void) => void;
}

const STEP_TYPES = [
  "pay_fees",
  "pay_interest",
  "pay_interest_shortfall",
  "pay_principal",
  "fund_reserve",
  "retire_bonds",
  "release_residual",
];
const AMOUNT_RULES = ["collections", "regular_pda", "priority_pda", "turbo"];
const BASES = ["trust", "performing", "adjusted"];
const OC_KINDS = ["fixed", "pct_current_pool", "pct_original_pool"];
const FLOOR_KINDS = ["none", "fixed", "pct_original_pool"];

function sourcesFor(deal: Deal): string[] {
  const builtin =
    deal.waterfall.mode === "combined"
      ? ["total_collections"]
      : ["interest_collections", "principal_collections"];
  return [
    ...builtin,
    ...deal.reserve_accounts.map((r) => `reserve:${r.name}`),
    ...(deal.external_sources ?? []).map((x) => `external:${x.name}`),
  ];
}

export default function WaterfallEditor({ deal, update }: Props) {
  const sources = sourcesFor(deal);
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <label className="label mb-0">Collections mode</label>
        <select className="input w-32" value={deal.waterfall.mode}
          onChange={(e) =>
            update((d) => { d.waterfall.mode = e.target.value as "split" | "combined"; })
          }>
          <option>split</option>
          <option>combined</option>
        </select>
        <span className="text-xs text-slate-500">
          split: interest / principal buckets · combined: one total_collections account
        </span>
      </div>

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
                    source: sources[0],
                    targets: [d.structure.classes[0]?.id ?? ""],
                  });
                })
              }>
              + Add step
            </button>
          </div>

          <div className="space-y-2">
            {wf.steps.map((step, si) => (
              <StepRow key={step.id} step={step} deal={deal} sources={sources}
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
        allocation tree overrides listed order within that group). Pair a collections step
        with a reserve-sourced twin to draw the reserve for the same clause.
      </p>
    </div>
  );
}

function defaultsForType(type: string, step: WaterfallStep, deal: Deal): WaterfallStep {
  const next: WaterfallStep = { type, id: step.id, label: step.label, source: step.source };
  if (type === "pay_fees") next.fees = deal.fees.map((f) => f.name);
  else if (type === "pay_principal") {
    next.targets = step.targets ?? [deal.structure.classes[0]?.id ?? ""];
    next.amount_rule = "collections";
    next.target_oc = { kind: "fixed", value: 0, floor_kind: "none", floor_value: 0 };
    next.pool_basis = "trust";
  } else if (type === "fund_reserve") next.account = deal.reserve_accounts[0]?.name ?? "";
  else if (type === "retire_bonds") {
    next.reserve = deal.reserve_accounts[0]?.name ?? "";
    next.release_reserve_remainder = true;
  } else if (type === "release_residual") next.to = "residual";
  else next.targets = step.targets ?? [];
  return next;
}

function StepRow({
  step,
  deal,
  sources,
  onChange,
  onMove,
  onRemove,
}: {
  step: WaterfallStep;
  deal: Deal;
  sources: string[];
  onChange: (s: WaterfallStep) => void;
  onMove: (dir: -1 | 1) => void;
  onRemove: () => void;
}) {
  const set = (patch: Partial<WaterfallStep>) => onChange({ ...step, ...patch });
  const setOC = (patch: Partial<TargetOCSpec>) =>
    set({
      target_oc: {
        kind: "fixed", value: 0, floor_kind: "none", floor_value: 0,
        ...step.target_oc, ...patch,
      },
    });
  const isPda = step.amount_rule === "regular_pda" || step.amount_rule === "priority_pda";

  return (
    <div className="flex flex-wrap items-end gap-2 rounded border border-slate-200 bg-slate-50 p-2">
      <div className="flex flex-col gap-1">
        <button className="btn-ghost py-0 leading-none" onClick={() => onMove(-1)}>▲</button>
        <button className="btn-ghost py-0 leading-none" onClick={() => onMove(1)}>▼</button>
      </div>
      <div>
        <label className="label">Action</label>
        <select className="input w-44" value={step.type}
          onChange={(e) => onChange(defaultsForType(e.target.value, step, deal))}>
          {STEP_TYPES.map((t) => <option key={t}>{t}</option>)}
        </select>
      </div>
      <div>
        <label className="label">Source</label>
        <select className="input w-48" value={step.source} onChange={(e) => set({ source: e.target.value })}>
          {sources.map((s) => <option key={s}>{s}</option>)}
          {!sources.includes(step.source) && <option>{step.source}</option>}
        </select>
      </div>

      {step.type === "pay_fees" && (
        <div>
          <label className="label">
            Fees (comma-sep{(deal.external_sources ?? []).some((x) => x.kind === "swap") ? "; swap:<name> = net swap payment" : ""})
          </label>
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
            <select className="input w-32" value={step.amount_rule}
              onChange={(e) => set({ amount_rule: e.target.value })}>
              {AMOUNT_RULES.map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
          {isPda && (
            <div>
              <label className="label">Pool basis</label>
              <select className="input w-28" value={step.pool_basis ?? "trust"}
                onChange={(e) => set({ pool_basis: e.target.value as WaterfallStep["pool_basis"] })}>
                {BASES.map((b) => <option key={b}>{b}</option>)}
              </select>
            </div>
          )}
          {step.amount_rule === "regular_pda" && (
            <>
              <div>
                <label className="label">Target OC</label>
                <div className="flex gap-1">
                  <select className="input w-36" value={step.target_oc?.kind ?? "fixed"}
                    onChange={(e) => setOC({ kind: e.target.value as TargetOCSpec["kind"] })}>
                    {OC_KINDS.map((k) => <option key={k}>{k}</option>)}
                  </select>
                  <input className="input w-24" type="number" step="0.0025"
                    value={step.target_oc?.value ?? 0}
                    onChange={(e) => setOC({ value: Number(e.target.value) })} />
                </div>
              </div>
              <div>
                <label className="label">OC floor (greater-of)</label>
                <div className="flex gap-1">
                  <select className="input w-36" value={step.target_oc?.floor_kind ?? "none"}
                    onChange={(e) => setOC({ floor_kind: e.target.value as TargetOCSpec["floor_kind"] })}>
                    {FLOOR_KINDS.map((k) => <option key={k}>{k}</option>)}
                  </select>
                  {(step.target_oc?.floor_kind ?? "none") !== "none" && (
                    <input className="input w-24" type="number" step="0.0025"
                      value={step.target_oc?.floor_value ?? 0}
                      onChange={(e) => setOC({ floor_value: Number(e.target.value) })} />
                  )}
                </div>
              </div>
            </>
          )}
        </>
      )}

      {step.type === "fund_reserve" && (
        <div>
          <label className="label">Account</label>
          <select className="input w-32" value={step.account ?? ""}
            onChange={(e) => set({ account: e.target.value })}>
            {deal.reserve_accounts.map((r) => <option key={r.name}>{r.name}</option>)}
          </select>
        </div>
      )}

      {step.type === "retire_bonds" && (
        <>
          <div>
            <label className="label">Reserve</label>
            <select className="input w-32" value={step.reserve ?? ""}
              onChange={(e) => set({ reserve: e.target.value })}>
              {deal.reserve_accounts.map((r) => <option key={r.name}>{r.name}</option>)}
            </select>
          </div>
          <label className="flex items-center gap-1 pb-2 text-xs text-slate-600">
            <input type="checkbox" checked={step.release_reserve_remainder ?? true}
              onChange={(e) => set({ release_reserve_remainder: e.target.checked })} />
            release remainder
          </label>
        </>
      )}

      {step.type === "release_residual" && (
        <div>
          <label className="label">To</label>
          <input className="input w-28" value={step.to ?? "residual"}
            onChange={(e) => set({ to: e.target.value })} />
        </div>
      )}

      {deal.triggers.length > 0 && (
        <div>
          <label className="label">Condition</label>
          <select className="input w-44"
            value={step.condition ? `${step.condition.trigger}|${step.condition.when}` : ""}
            onChange={(e) => {
              const v = e.target.value;
              if (!v) set({ condition: null });
              else {
                const [trigger, when] = v.split("|");
                set({ condition: { trigger, when: when as "pass" | "fail" } });
              }
            }}>
            <option value="">always</option>
            {deal.triggers.flatMap((t) => [
              <option key={`${t.name}|pass`} value={`${t.name}|pass`}>if {t.name} passes</option>,
              <option key={`${t.name}|fail`} value={`${t.name}|fail`}>if {t.name} fails</option>,
            ])}
          </select>
        </div>
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
