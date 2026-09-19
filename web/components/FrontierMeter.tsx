"use client";

import {
  CartesianGrid,
  Label,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import type { Frontier } from "@/lib/types";

const COLOR: Record<string, string> = {
  cheap: "#71717a",
  deep: "#fb923c",
  ponder: "#34d399",
};

export function FrontierMeter({ frontier }: { frontier: Frontier | null }) {
  const reports = frontier?.reports ?? [];
  const points = reports.map((r) => ({
    x: Math.max(r.total_gpu_seconds, 0.1),
    y: r.high_stakes_accuracy * 100,
    strategy: r.strategy,
  }));

  return (
    <section className="flex flex-col rounded-xl border border-zinc-800 bg-zinc-950/60 px-4 py-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
          Cost vs accuracy
        </h2>
        <span className="text-[10px] text-zinc-600">high-stakes tasks</span>
      </div>

      <div className="mt-1 h-[168px] w-full">
        {points.length === 0 ? (
          <div className="flex h-full items-center justify-center text-xs text-zinc-600">
            run `python -m agent.baselines` to plot the frontier
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 12, right: 14, bottom: 18, left: -14 }}>
              <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
              <XAxis
                type="number"
                dataKey="x"
                scale="log"
                domain={["auto", "auto"]}
                stroke="#52525b"
                tick={{ fontSize: 10, fill: "#71717a" }}
                tickFormatter={(v: number) => `${v < 10 ? v.toFixed(0) : Math.round(v)}s`}
              >
                <Label
                  value="GPU seconds (log)"
                  position="insideBottom"
                  offset={-10}
                  style={{ fontSize: 10, fill: "#52525b" }}
                />
              </XAxis>
              <YAxis
                type="number"
                dataKey="y"
                domain={[0, 100]}
                stroke="#52525b"
                tick={{ fontSize: 10, fill: "#71717a" }}
                tickFormatter={(v: number) => `${v}%`}
              />
              <ZAxis range={[220, 220]} />
              <Tooltip
                cursor={{ stroke: "#3f3f46" }}
                contentStyle={{
                  background: "#18181b",
                  border: "1px solid #3f3f46",
                  borderRadius: 8,
                  fontSize: 11,
                }}
                formatter={(value: number, name: string) =>
                  name === "y" ? [`${value.toFixed(0)}%`, "high-stakes acc"] : [`${value.toFixed(1)}s`, "gpu"]
                }
                labelFormatter={() => ""}
              />
              {points.map((p) => (
                <Scatter key={p.strategy} name={p.strategy} data={[p]} fill={COLOR[p.strategy]} />
              ))}
            </ScatterChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="flex gap-4 border-t border-zinc-800 pt-2">
        {reports.map((r) => (
          <div key={r.strategy} className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: COLOR[r.strategy] }}
            />
            <span className="text-[10px] uppercase tracking-wider text-zinc-500">{r.strategy}</span>
            <span className="font-mono text-[10px] text-zinc-300">
              {Math.round(r.high_stakes_accuracy * 100)}%
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
