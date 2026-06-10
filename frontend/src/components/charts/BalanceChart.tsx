import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { RunResult } from "../../api/client";

const COLORS = ["#2563eb", "#16a34a", "#ea580c", "#9333ea", "#0891b2", "#be123c"];

export default function BalanceChart({ result }: { result: RunResult }) {
  const periods = result.collateral["period"] as number[];
  const classIds = Object.keys(result.metrics.bonds);

  // bonds arrive row-per-(period,class); pivot end_balance into per-class series
  const byClass: Record<string, number[]> = Object.fromEntries(classIds.map((c) => [c, []]));
  const bClass = result.bonds["class_id"] as string[];
  const bBal = result.bonds["end_balance"] as number[];
  bClass.forEach((cid, i) => byClass[cid]?.push(bBal[i]));

  const data = periods.map((p, i) => {
    const row: Record<string, number> = {
      period: p,
      pool_trust: result.collateral["end_trust"][i],
      pool_performing: result.collateral["end_performing"][i],
    };
    for (const cid of classIds) row[cid] = byClass[cid][i];
    return row;
  });

  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="period" />
        <YAxis tickFormatter={(v: number) => v.toLocaleString()} width={90} />
        <Tooltip formatter={(v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 })} />
        <Legend />
        <Line dataKey="pool_trust" stroke="#334155" dot={false} strokeWidth={2} />
        <Line dataKey="pool_performing" stroke="#94a3b8" dot={false} strokeDasharray="4 4" />
        {classIds.map((cid, i) => (
          <Line key={cid} dataKey={cid} stroke={COLORS[i % COLORS.length]} dot={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
