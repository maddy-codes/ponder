"use client";

import { Target } from "lucide-react";
import { Bar, BarChart, CartesianGrid, LabelList, XAxis, YAxis } from "recharts";
import { EmptyState, Panel, PanelHeader } from "@/components/primitives";
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import type { StakesBand } from "@/lib/derive";

const config = {
  accuracy: { label: "Accuracy", color: "var(--chart-3)" },
} satisfies ChartConfig;

/** The claim worth checking: whatever Ponder still gets wrong should be cheap to get wrong. */
export function StakesAccuracyChart({ bands }: { bands: StakesBand[] }) {
  const graded = bands.reduce((a, b) => a + b.n, 0);
  const data = bands.map((b) => ({ ...b, value: Math.round(b.accuracy * 100) }));

  return (
    <Panel className="flex h-full flex-col">
      <PanelHeader
        title="Accuracy by stakes"
        description="Errors should concentrate where being wrong is cheap"
        icon={Target}
      />
      <div className="flex-1 p-3">
        {graded === 0 ? (
          <EmptyState icon={Target} title="Nothing graded yet" />
        ) : (
          <ChartContainer config={config} className="aspect-auto h-full min-h-44 w-full">
            <BarChart data={data} margin={{ left: 0, right: 8, top: 16, bottom: 0 }} barSize={44}>
              <CartesianGrid vertical={false} strokeDasharray="3 4" />
              <XAxis dataKey="band" tickLine={false} axisLine={false} tickMargin={8} />
              <YAxis
                domain={[0, 100]}
                ticks={[0, 50, 100]}
                tickLine={false}
                axisLine={false}
                width={42}
                tickFormatter={(v: number) => `${v}%`}
              />
              <ChartTooltip
                cursor={false}
                content={
                  <ChartTooltipContent
                    hideLabel
                    formatter={(_v, _n, item) => {
                      const b = item?.payload as (StakesBand & { value: number }) | undefined;
                      if (!b) return null;
                      return (
                        <div className="grid gap-0.5">
                          <span className="font-medium capitalize">{b.band} stakes</span>
                          <span className="text-muted-foreground">
                            {b.correct}/{b.n} correct · {b.value}%
                          </span>
                        </div>
                      );
                    }}
                  />
                }
              />
              <Bar dataKey="value" fill="var(--color-accuracy)" radius={6} isAnimationActive={false}>
                <LabelList
                  dataKey="value"
                  position="top"
                  offset={6}
                  className="fill-foreground"
                  fontSize={12}
                  formatter={(v: unknown) => `${Number(v)}%`}
                />
              </Bar>
            </BarChart>
          </ChartContainer>
        )}
      </div>
    </Panel>
  );
}
