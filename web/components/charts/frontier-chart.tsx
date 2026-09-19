"use client";

import { TrendingUp } from "lucide-react";
import { CartesianGrid, LabelList, Scatter, ScatterChart, XAxis, YAxis, ZAxis } from "recharts";
import { EmptyState, Panel, PanelHeader } from "@/components/primitives";
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { fmtGpu } from "@/lib/derive";
import type { Frontier, StrategyReport } from "@/lib/types";

const config = {
  cheap: { label: "Cheap", color: "var(--chart-1)" },
  deep: { label: "Deep", color: "var(--chart-2)" },
  ponder: { label: "Ponder", color: "var(--chart-3)" },
} satisfies ChartConfig;

const colorOf = (s: string) => config[s as keyof typeof config]?.color ?? "var(--chart-5)";

type Point = { x: number; y: number; strategy: string; report: StrategyReport };

export function FrontierChart({ frontier }: { frontier: Frontier | null }) {
  const reports = frontier?.reports ?? [];
  const points: Point[] = reports.map((r) => ({
    x: Math.max(r.total_gpu_seconds, 0.1),
    y: r.high_stakes_accuracy * 100,
    strategy: r.strategy,
    report: r,
  }));

  return (
    <Panel className="flex h-full flex-col">
      <PanelHeader
        title="Cost against accuracy"
        description="High-stakes accuracy per GPU second, for all three strategies"
        icon={TrendingUp}
      />

      <div className="flex-1 p-3">
        {points.length === 0 ? (
          <EmptyState
            icon={TrendingUp}
            title="No baselines recorded"
            body="Run python -m agent.baselines --fresh to plot the frontier."
          />
        ) : (
          <ChartContainer config={config} className="aspect-auto h-full min-h-44 w-full">
            <ScatterChart margin={{ left: 0, right: 28, top: 20, bottom: 14 }}>
              <CartesianGrid strokeDasharray="3 4" />
              <XAxis
                type="number"
                dataKey="x"
                scale="log"
                domain={["auto", "auto"]}
                tickLine={false}
                axisLine={false}
                tickMargin={6}
                tickFormatter={(v: number) => fmtGpu(v)}
                label={{
                  value: "gpu seconds (log)",
                  position: "insideBottom",
                  offset: -8,
                  fontSize: 11,
                  fill: "var(--muted-foreground)",
                }}
              />
              <YAxis
                type="number"
                dataKey="y"
                domain={[0, 100]}
                ticks={[0, 50, 100]}
                tickLine={false}
                axisLine={false}
                width={42}
                tickFormatter={(v: number) => `${v}%`}
              />
              <ZAxis range={[260, 260]} />
              <ChartTooltip
                cursor={{ strokeDasharray: "3 3" }}
                content={
                  <ChartTooltipContent
                    hideLabel
                    formatter={(_v, _n, item) => {
                      const p = item?.payload as Point | undefined;
                      if (!p) return null;
                      const r = p.report;
                      return (
                        <div className="grid gap-0.5">
                          <span className="font-medium capitalize">{p.strategy}</span>
                          <span className="text-muted-foreground">
                            {Math.round(r.high_stakes_accuracy * 100)}% high-stakes ·{" "}
                            {fmtGpu(r.total_gpu_seconds)} gpu · {r.deep_tasks}/{r.n} deep
                          </span>
                        </div>
                      );
                    }}
                  />
                }
              />
              {points.map((p) => (
                <Scatter
                  key={p.strategy}
                  name={p.strategy}
                  data={[p]}
                  fill={colorOf(p.strategy)}
                  stroke="var(--card)"
                  strokeWidth={2}
                  isAnimationActive={false}
                >
                  {/* Identity is never colour alone: every mark carries its name. */}
                  <LabelList
                    dataKey="strategy"
                    position="top"
                    offset={11}
                    className="fill-muted-foreground"
                    fontSize={11}
                  />
                </Scatter>
              ))}
            </ScatterChart>
          </ChartContainer>
        )}
      </div>

      {reports.length > 0 && (
        <div className="grid grid-cols-3 divide-x divide-border border-t border-border">
          {reports.map((r) => (
            <div key={r.strategy} className="px-3 py-2.5">
              <div className="flex items-center gap-1.5">
                <span
                  className="size-2 rounded-full"
                  style={{ background: colorOf(r.strategy) }}
                  aria-hidden
                />
                <span className="field-label capitalize">{r.strategy}</span>
              </div>
              <p className="mt-1 font-mono text-lg leading-none">
                {Math.round(r.high_stakes_accuracy * 100)}%
              </p>
              <p className="mt-1 font-mono text-xs text-muted-foreground">
                {fmtGpu(r.total_gpu_seconds)} gpu
              </p>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
