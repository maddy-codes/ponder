"use client";

import { Coins } from "lucide-react";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { EmptyState, Panel, PanelHeader } from "@/components/primitives";
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { fmtTokens, type SpendPoint } from "@/lib/derive";

const config = {
  alwaysDeep: { label: "Always-deep", color: "var(--chart-2)" },
  ponder: { label: "Ponder", color: "var(--chart-3)" },
} satisfies ChartConfig;

/** The headline: the gap between the two lines is the money the rule layer saves. */
export function SpendChart({
  points,
  hasCounterfactual,
}: {
  points: SpendPoint[];
  hasCounterfactual: boolean;
}) {
  const last = points[points.length - 1];
  const saved =
    hasCounterfactual && last && last.alwaysDeep > 0 ? 1 - last.ponder / last.alwaysDeep : 0;

  return (
    <Panel className="flex h-full flex-col">
      <PanelHeader
        title="Cumulative token spend"
        description="Ponder against the same queue run always-deep"
        icon={Coins}
      >
        {saved > 0 && (
          <span className="rounded-md bg-ok/12 px-2 py-0.5 text-xs font-medium text-ok">
            {Math.round(saved * 100)}% saved
          </span>
        )}
      </PanelHeader>

      <div className="flex-1 p-3">
        {points.length === 0 ? (
          <EmptyState icon={Coins} title="No tasks yet" body="Spend accrues as the queue drains." />
        ) : !hasCounterfactual ? (
          <SingleSeries points={points} />
        ) : (
          <ChartContainer config={config} className="aspect-auto h-full min-h-48 w-full">
            <AreaChart data={points} margin={{ left: 4, right: 8, top: 8, bottom: 0 }}>
              <defs>
                <linearGradient id="fillDeep" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-alwaysDeep)" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="var(--color-alwaysDeep)" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="fillPonder" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-ponder)" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="var(--color-ponder)" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} strokeDasharray="3 4" />
              <XAxis
                dataKey="step"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={24}
                tickFormatter={(v: number) => `#${v}`}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={44}
                tickFormatter={(v: number) => fmtTokens(v)}
              />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    labelFormatter={(_, payload) => `Task ${payload?.[0]?.payload?.id ?? ""}`}
                    formatter={(value, name) => (
                      <span className="flex w-full justify-between gap-4">
                        <span className="text-muted-foreground">{config[name as keyof typeof config]?.label ?? name}</span>
                        <span className="font-mono">{fmtTokens(Number(value))}</span>
                      </span>
                    )}
                  />
                }
              />
              <Area
                dataKey="alwaysDeep"
                type="monotone"
                fill="url(#fillDeep)"
                stroke="var(--color-alwaysDeep)"
                strokeWidth={2}
                isAnimationActive={false}
              />
              <Area
                dataKey="ponder"
                type="monotone"
                fill="url(#fillPonder)"
                stroke="var(--color-ponder)"
                strokeWidth={2}
                isAnimationActive={false}
              />
              <ChartLegend content={<ChartLegendContent />} />
            </AreaChart>
          </ChartContainer>
        )}
      </div>
    </Panel>
  );
}

/** Without a recorded `deep` run there is no second line to draw — say so, don't fake it. */
function SingleSeries({ points }: { points: SpendPoint[] }) {
  return (
    <div className="flex h-full min-h-48 flex-col">
      <ChartContainer config={config} className="aspect-auto min-h-0 w-full flex-1">
        <AreaChart data={points} margin={{ left: 4, right: 8, top: 8, bottom: 0 }}>
          <defs>
            <linearGradient id="fillPonderSolo" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-ponder)" stopOpacity={0.3} />
              <stop offset="100%" stopColor="var(--color-ponder)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} strokeDasharray="3 4" />
          <XAxis
            dataKey="step"
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            minTickGap={24}
            tickFormatter={(v: number) => `#${v}`}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            width={44}
            tickFormatter={(v: number) => fmtTokens(v)}
          />
          <ChartTooltip
            content={
              <ChartTooltipContent
                labelFormatter={(_, payload) => `Task ${payload?.[0]?.payload?.id ?? ""}`}
                formatter={(value) => (
                  <span className="flex w-full justify-between gap-4">
                    <span className="text-muted-foreground">Ponder</span>
                    <span className="font-mono">{fmtTokens(Number(value))}</span>
                  </span>
                )}
              />
            }
          />
          <Area
            dataKey="ponder"
            type="monotone"
            fill="url(#fillPonderSolo)"
            stroke="var(--color-ponder)"
            strokeWidth={2}
            isAnimationActive={false}
          />
        </AreaChart>
      </ChartContainer>
      <p className="px-1 pt-2 text-xs text-muted-foreground">
        No always-deep events in this recording — run{" "}
        <code className="font-mono">python -m agent.baselines --fresh</code> to draw the
        counterfactual.
      </p>
    </div>
  );
}
