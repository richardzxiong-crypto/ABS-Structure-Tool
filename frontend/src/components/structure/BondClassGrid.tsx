import type { ColDef } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";

import type { BondClass, Deal } from "../../api/client";
import AllocationTreeEditor from "./AllocationTreeEditor";

interface Props {
  deal: Deal;
  update: (fn: (draft: Deal) => void) => void;
}

interface Row {
  id: string;
  name: string;
  balance: number;
  coupon_type: "fixed" | "floating";
  coupon_rate: number; // fixed rate, or floating margin
  index: string;
  day_count: BondClass["day_count"];
  price: number | null;
}

const COLS: ColDef<Row>[] = [
  { field: "id", headerName: "Class", editable: true, pinned: "left" },
  { field: "name", headerName: "Name", editable: true },
  { field: "balance", headerName: "Balance", editable: true, valueParser: (p) => Number(p.newValue), type: "rightAligned" },
  {
    field: "coupon_type", headerName: "Coupon type", editable: true,
    cellEditor: "agSelectCellEditor", cellEditorParams: { values: ["fixed", "floating"] },
  },
  {
    field: "coupon_rate", headerName: "Rate / margin", editable: true,
    valueParser: (p) => Number(p.newValue), type: "rightAligned",
  },
  {
    field: "index", headerName: "Index (floating)", editable: (p) => p.data?.coupon_type === "floating",
    valueFormatter: (p) => (p.data?.coupon_type === "floating" ? p.value : "—"),
  },
  {
    field: "day_count", headerName: "Day count", editable: true,
    cellEditor: "agSelectCellEditor", cellEditorParams: { values: ["30/360", "ACT/360", "ACT/365"] },
  },
  { field: "price", headerName: "Price", editable: true, valueParser: (p) => (p.newValue === "" ? null : Number(p.newValue)), type: "rightAligned" },
];

export default function BondClassGrid({ deal, update }: Props) {
  const rows: Row[] = deal.structure.classes.map((c) => ({
    id: c.id,
    name: c.name,
    balance: c.balance,
    coupon_type: c.coupon.type,
    coupon_rate: (c.coupon.type === "fixed" ? c.coupon.rate : c.coupon.margin) ?? 0,
    index: c.coupon.index ?? "",
    day_count: c.day_count,
    price: c.price,
  }));

  const applyRow = (i: number, row: Row) =>
    update((d) => {
      const c: BondClass = d.structure.classes[i];
      c.id = row.id;
      c.name = row.name;
      c.balance = row.balance;
      c.coupon =
        row.coupon_type === "floating"
          ? { type: "floating", index: row.index || "SOFR", margin: row.coupon_rate }
          : { type: "fixed", rate: row.coupon_rate };
      c.day_count = row.day_count;
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

      <AllocationTreeEditor deal={deal} update={update} />
    </div>
  );
}
