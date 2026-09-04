import { useState } from "react";

import type { AllocationNode, Deal, PoolBasis, TargetBalanceSpec } from "../../api/client";

interface Props {
  deal: Deal;
  update: (fn: (draft: Deal) => void) => void;
}

type Path = number[];

const MODES = ["sequential", "pro_rata", "target_balance"] as const;
const BASES: PoolBasis[] = ["trust", "performing", "adjusted"];

function nodeAt(root: AllocationNode, path: Path): AllocationNode {
  let n = root;
  for (const i of path) n = n.children![i];
  return n;
}

function leafIds(node: AllocationNode): string[] {
  if (node.type === "class") return [node.class_id ?? ""];
  return (node.children ?? []).flatMap(leafIds);
}

function groupNames(node: AllocationNode): string[] {
  if (node.type === "class") return [];
  return [node.name ?? "", ...(node.children ?? []).flatMap(groupNames)];
}

function defaultSpec(): TargetBalanceSpec {
  return { kind: "schedule", schedule: [], pct: 0, pool_basis: "trust", distribution: "sequential" };
}

/** Recursive editor for the allocation tree: groups with payment modes
 * nesting to any depth, classes as leaves. Every class must appear exactly
 * once; unassigned classes are listed so they can be dropped into a group. */
export default function AllocationTreeEditor({ deal, update }: Props) {
  const [json, setJson] = useState<string | null>(null);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const tree = deal.structure.allocation_tree;
  const assigned = new Set(leafIds(tree));
  const unassigned = deal.structure.classes.map((c) => c.id).filter((id) => !assigned.has(id));
  const unknown = [...assigned].filter((id) => !deal.structure.classes.some((c) => c.id === id));
  const dupGroups = groupNames(tree).filter((n, i, all) => all.indexOf(n) !== i);

  const patchNode = (path: Path, fn: (n: AllocationNode) => void) =>
    update((d) => { fn(nodeAt(d.structure.allocation_tree, path)); });

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">
          Allocation tree (payment mode per group; nests to any depth)
        </h2>
        {json === null ? (
          <button className="btn-ghost" onClick={() => setJson(JSON.stringify(tree, null, 2))}>
            Edit JSON
          </button>
        ) : (
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={() => { setJson(null); setJsonError(null); }}>Cancel</button>
            <button className="btn-primary"
              onClick={() => {
                try {
                  const parsed = JSON.parse(json);
                  update((d) => { d.structure.allocation_tree = parsed; });
                  setJson(null);
                  setJsonError(null);
                } catch (e) {
                  setJsonError(String(e));
                }
              }}>
              Apply
            </button>
          </div>
        )}
      </div>
      {jsonError && <div className="text-sm text-red-600">{jsonError}</div>}

      {json !== null ? (
        <textarea className="input h-64 font-mono text-xs" value={json} onChange={(e) => setJson(e.target.value)} />
      ) : (
        <>
          <GroupEditor node={tree} path={[]} deal={deal} unassigned={unassigned}
            patchNode={patchNode} update={update} />
          {unassigned.length > 0 && (
            <div className="text-xs text-amber-700">
              Not in the tree (the deal will not validate until they are): {unassigned.join(", ")}
            </div>
          )}
          {unknown.length > 0 && (
            <div className="text-xs text-red-600">Tree references unknown classes: {unknown.join(", ")}</div>
          )}
          {dupGroups.length > 0 && (
            <div className="text-xs text-red-600">Duplicate group names: {[...new Set(dupGroups)].join(", ")}</div>
          )}
          <p className="text-xs text-slate-500">
            sequential: children in order · pro_rata: by current/original balance, overflow
            redistributed · target_balance: principal paid only down to the period's target
            (schedule or % of pool), the rest flows to the next target listed on the step -
            list the scheduled class again after its companions to let it absorb the tail.
          </p>
        </>
      )}
    </div>
  );
}

function GroupEditor({
  node, path, deal, unassigned, patchNode, update,
}: {
  node: AllocationNode;
  path: Path;
  deal: Deal;
  unassigned: string[];
  patchNode: (path: Path, fn: (n: AllocationNode) => void) => void;
  update: Props["update"];
}) {
  const children = node.children ?? [];
  const isRoot = path.length === 0;
  const spec = node.target_balance_spec ?? null;
  const setSpec = (patch: Partial<TargetBalanceSpec>) =>
    patchNode(path, (n) => { n.target_balance_spec = { ...(n.target_balance_spec ?? defaultSpec()), ...patch }; });

  const parentOps = (i: number) => ({
    move: (dir: -1 | 1) =>
      patchNode(path, (n) => {
        const j = i + dir;
        if (j < 0 || j >= n.children!.length) return;
        [n.children![i], n.children![j]] = [n.children![j], n.children![i]];
      }),
    remove: () => patchNode(path, (n) => { n.children!.splice(i, 1); }),
  });

  return (
    <div className={`rounded border ${isRoot ? "border-slate-300" : "border-slate-200"} bg-slate-50 p-2`}>
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label className="label">Group</label>
          <input className="input w-32" value={node.name ?? ""}
            onChange={(e) => patchNode(path, (n) => { n.name = e.target.value; })} />
        </div>
        <div>
          <label className="label">Mode</label>
          <select className="input w-36" value={node.mode ?? "sequential"}
            onChange={(e) =>
              patchNode(path, (n) => {
                n.mode = e.target.value as AllocationNode["mode"];
                if (n.mode === "target_balance" && !n.target_balance_spec) n.target_balance_spec = defaultSpec();
              })
            }>
            {MODES.map((m) => <option key={m}>{m}</option>)}
          </select>
        </div>
        {node.mode === "pro_rata" && (
          <div>
            <label className="label">Pro-rata basis</label>
            <select className="input w-28" value={node.pro_rata_basis ?? "current"}
              onChange={(e) => patchNode(path, (n) => { n.pro_rata_basis = e.target.value as "current" | "original"; })}>
              <option>current</option>
              <option>original</option>
            </select>
          </div>
        )}
        {node.mode === "target_balance" && (
          <>
            <div>
              <label className="label">Target</label>
              <select className="input w-28" value={spec?.kind ?? "schedule"}
                onChange={(e) => setSpec({ kind: e.target.value as TargetBalanceSpec["kind"] })}>
                <option>schedule</option>
                <option>pct_of_pool</option>
              </select>
            </div>
            {(spec?.kind ?? "schedule") === "schedule" ? (
              <div className="grow">
                <label className="label">Schedule (balance per period, comma-sep; 0 after the end)</label>
                <input className="input font-mono text-xs"
                  defaultValue={(spec?.schedule ?? []).join(",")}
                  key={`${path.join(".")}-sched`}
                  onBlur={(e) =>
                    setSpec({
                      schedule: e.target.value.split(",").map((x) => Number(x.trim())).filter((x) => !Number.isNaN(x)),
                    })
                  } />
              </div>
            ) : (
              <>
                <div>
                  <label className="label">% of pool</label>
                  <input className="input w-24" type="number" step="0.01" value={spec?.pct ?? 0}
                    onChange={(e) => setSpec({ pct: Number(e.target.value) })} />
                </div>
                <div>
                  <label className="label">Pool basis</label>
                  <select className="input w-28" value={spec?.pool_basis ?? "trust"}
                    onChange={(e) => setSpec({ pool_basis: e.target.value as PoolBasis })}>
                    {BASES.map((b) => <option key={b}>{b}</option>)}
                  </select>
                </div>
              </>
            )}
            <div>
              <label className="label">Within group</label>
              <select className="input w-28" value={spec?.distribution ?? "sequential"}
                onChange={(e) => setSpec({ distribution: e.target.value as "sequential" | "pro_rata" })}>
                <option>sequential</option>
                <option>pro_rata</option>
              </select>
            </div>
          </>
        )}
        <div className="ml-auto flex items-end gap-1">
          {unassigned.length > 0 && (
            <select className="input w-32" value=""
              onChange={(e) => {
                const id = e.target.value;
                if (id) patchNode(path, (n) => { n.children!.push({ type: "class", class_id: id }); });
              }}>
              <option value="">+ class…</option>
              {unassigned.map((id) => <option key={id}>{id}</option>)}
            </select>
          )}
          <button className="btn-ghost"
            onClick={() =>
              patchNode(path, (n) => {
                const existing = groupNames(deal.structure.allocation_tree);
                let k = 1;
                while (existing.includes(`group_${k}`)) k += 1;
                n.children!.push({ type: "group", name: `group_${k}`, mode: "sequential", children: [] });
              })
            }>
            + group
          </button>
        </div>
      </div>

      <div className="mt-2 space-y-1 border-l-2 border-slate-300 pl-3">
        {children.length === 0 && <div className="text-xs text-red-600">Empty group (needs at least one child)</div>}
        {children.map((child, i) => {
          const ops = parentOps(i);
          return (
            <div key={i} className="flex items-start gap-1">
              <div className="flex flex-col pt-1">
                <button className="btn-ghost py-0 leading-none" onClick={() => ops.move(-1)}>▲</button>
                <button className="btn-ghost py-0 leading-none" onClick={() => ops.move(1)}>▼</button>
              </div>
              <div className="grow">
                {child.type === "class" ? (
                  <div className="flex items-center gap-2 rounded border border-slate-200 bg-white px-2 py-1 text-sm">
                    <span className="font-mono">{child.class_id}</span>
                    <span className="text-xs text-slate-500">
                      {deal.structure.classes.find((c) => c.id === child.class_id)?.name ?? ""}
                    </span>
                    <button className="btn-ghost ml-auto text-red-600" onClick={ops.remove}>✕</button>
                  </div>
                ) : (
                  <div className="relative">
                    <GroupEditor node={child} path={[...path, i]} deal={deal} unassigned={unassigned}
                      patchNode={patchNode} update={update} />
                    <button className="btn-ghost absolute right-2 top-2 text-red-600" title="remove group (its classes become unassigned)"
                      onClick={ops.remove}>✕</button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
