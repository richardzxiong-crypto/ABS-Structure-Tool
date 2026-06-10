import type { ColDef } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useState } from "react";

import type { BondClass, Deal } from "../../api/client";

interface Props {
  deal: Deal;
  update: (fn: (draft: Deal) => void) => void;
}

interface Row {
  id: string;
  name: string;
  balance: number;
  coupon_rate: number;
  price: number | null;
}

const COLS: ColDef<Row>[] = [
  { field: "id", headerName: "Class", editable: true, pinned: "left" },
  { field: "name", headerName: "Name", editable: true },
  { field: "balance", headerName: "Balance", editable: true, valueParser: (p) => Number(p.newValue), type: "rightAligned" },
  { field: "coupon_rate", headerName: "Coupon", editable: true, valueParser: (p) => Number(p.newValue), type: "rightAligned" },
  { field: "price", headerName: "Price", editable: true, valueParser: (p) => (p.newValue === "" ? null : Number(p.newValue)), type: "rightAligned" },
];

export default function BondClassGrid({ deal, update }: Props) {
  const [treeJson, setTreeJson] = useState<string | null>(null);
  const [treeError, setTreeError] = useState<string | null>(null);

  const rows: Row[] = deal.structure.classes.map((c) => ({
    id: c.id,
    name: c.name,
    balance: c.balance,
    coupon_rate: c.coupon.rate ?? 0,
    price: c.price,
  }));

  const applyRow = (i: number, row: Row) =>
    update((d) => {
      const c: BondClass = d.structure.classes[i];
      c.id = row.id;
      c.name = row.name;
      c.balance = row.balance;
      c.coupon = { type: "fixed", rate: row.coupon_rate };
      c.price = row.price;
    });

  return (
    <div className="space-y-4">
      <div className="ag-theme-quartz" style={{ height: 280 }}>
        <AgGridReact<Row>
          rowData={rows}
          columnDefs={COLS}
          defaultColDef={{ flex: 1, resizable: true }}
          onCellValueChanged={(e) => applyRow(e.rowIndex!, e.data)}
        />
      </div>

      <div className="card">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">
            Allocation tree (payment modes per group; recursive editor lands in Phase 2)
          </h2>
          {treeJson === null ? (
            <button className="btn-ghost"
              onClick={() => setTreeJson(JSON.stringify(deal.structure.allocation_tree, null, 2))}>
              Edit JSON
            </button>
          ) : (
            <div className="flex gap-2">
              <button className="btn-ghost" onClick={() => { setTreeJson(null); setTreeError(null); }}>
                Cancel
              </button>
              <button className="btn-primary"
                onClick={() => {
                  try {
                    const parsed = JSON.parse(treeJson);
                    update((d) => {
                      d.structure.allocation_tree = parsed;
                    });
                    setTreeJson(null);
                    setTreeError(null);
                  } catch (e) {
                    setTreeError(String(e));
                  }
                }}>
                Apply
              </button>
            </div>
          )}
        </div>
        {treeError && <div className="mb-2 text-sm text-red-600">{treeError}</div>}
        {treeJson === null ? (
          <pre className="overflow-auto rounded bg-slate-50 p-3 text-xs text-slate-700">
            {renderTree(deal.structure.allocation_tree, 0)}
          </pre>
        ) : (
          <textarea className="input h-64 font-mono text-xs" value={treeJson}
            onChange={(e) => setTreeJson(e.target.value)} />
        )}
      </div>
    </div>
  );
}

function renderTree(node: Deal["structure"]["allocation_tree"], depth: number): string {
  const pad = "  ".repeat(depth);
  if (node.type === "class") return `${pad}└ ${node.class_id}\n`;
  let out = `${pad}${node.name} (${node.mode}${node.mode === "pro_rata" ? `, basis=${node.pro_rata_basis}` : ""})\n`;
  for (const child of node.children ?? []) out += renderTree(child, depth + 1);
  return out;
}
