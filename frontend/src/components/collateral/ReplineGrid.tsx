import type { ColDef } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";

import type { Deal, Repline } from "../../api/client";

interface Props {
  deal: Deal;
  update: (fn: (draft: Deal) => void) => void;
}

const numCol = (field: keyof Repline, headerName: string): ColDef<Repline> => ({
  field,
  headerName,
  editable: true,
  valueParser: (p) => Number(p.newValue),
  type: "rightAligned",
});

const COLS: ColDef<Repline>[] = [
  { field: "id", headerName: "Repline", editable: true, pinned: "left" },
  numCol("balance", "Balance"),
  numCol("gross_rate", "Gross Rate"),
  numCol("original_term", "Orig Term"),
  numCol("remaining_term", "Rem Term"),
  numCol("collection_delay", "Collection Delay"),
  numCol("funding_delay", "Funding Delay"),
];

export default function ReplineGrid({ deal, update }: Props) {
  const replines = deal.collateral.replines;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-end gap-4">
          <div>
            <label className="label">Servicing fee (annual)</label>
            <input
              className="input w-32"
              type="number"
              step="0.001"
              value={deal.collateral.servicing_fee_rate}
              onChange={(e) =>
                update((d) => {
                  d.collateral.servicing_fee_rate = Number(e.target.value);
                })
              }
            />
          </div>
          <div>
            <label className="label">Periods</label>
            <input
              className="input w-24"
              type="number"
              value={deal.num_periods}
              onChange={(e) =>
                update((d) => {
                  d.num_periods = Number(e.target.value);
                })
              }
            />
          </div>
        </div>
        <div className="flex gap-2">
          <button
            className="btn"
            onClick={() =>
              update((d) => {
                d.collateral.replines.push({
                  id: `R${d.collateral.replines.length + 1}`,
                  balance: 1_000_000,
                  gross_rate: 0.07,
                  original_term: 60,
                  remaining_term: 60,
                  amort_type: "level_pay",
                  collection_delay: 0,
                  funding_delay: 0,
                });
              })
            }>
            + Add repline
          </button>
          <button
            className="btn"
            disabled={replines.length <= 1}
            onClick={() =>
              update((d) => {
                d.collateral.replines.pop();
              })
            }>
            − Remove last
          </button>
        </div>
      </div>

      <div className="ag-theme-quartz" style={{ height: 320 }}>
        <AgGridReact<Repline>
          rowData={structuredClone(replines)}
          columnDefs={COLS}
          defaultColDef={{ flex: 1, resizable: true }}
          onCellValueChanged={(e) =>
            update((d) => {
              d.collateral.replines[e.rowIndex!] = e.data;
            })
          }
        />
      </div>
      <p className="text-xs text-slate-500">
        Collection delay d: repline periods 1..1+d collections combine into trust period 1.
        Funding delay f: repline cash shows up f trust periods late (prefunding).
      </p>
    </div>
  );
}
