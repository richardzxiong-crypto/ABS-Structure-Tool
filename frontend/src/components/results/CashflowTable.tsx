import type { ColDef } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useMemo } from "react";

interface Props {
  /** column-oriented data from the API: {col: values[]} */
  columns: Record<string, (number | string | null)[]>;
  pageSize?: number;
}

export default function CashflowTable({ columns, pageSize = 12 }: Props) {
  const { rows, colDefs } = useMemo(() => {
    const names = Object.keys(columns);
    const n = names.length ? columns[names[0]].length : 0;
    const rows = Array.from({ length: n }, (_, i) =>
      Object.fromEntries(names.map((c) => [c, columns[c][i]])),
    );
    const colDefs: ColDef[] = names.map((c) => ({
      field: c,
      headerName: c,
      type: typeof columns[c][0] === "number" ? "rightAligned" : undefined,
      valueFormatter:
        typeof columns[c][0] === "number" && !Number.isInteger(columns[c][0])
          ? (p) => (p.value == null ? "" : (p.value as number).toLocaleString(undefined, { maximumFractionDigits: 4 }))
          : undefined,
      minWidth: 110,
    }));
    return { rows, colDefs };
  }, [columns]);

  return (
    <div className="ag-theme-quartz" style={{ height: 420 }}>
      <AgGridReact
        rowData={rows}
        columnDefs={colDefs}
        defaultColDef={{ resizable: true, sortable: true }}
        pagination
        paginationPageSize={pageSize}
        paginationPageSizeSelector={[12, 15, 24, 60, 120]}
      />
    </div>
  );
}
