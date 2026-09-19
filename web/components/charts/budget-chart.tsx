"use client";

import { PieChart as PieIcon } from "lucide-react";
import { Bar, BarChart, CartesianGrid, LabelList, XAxis, YAxis } from "recharts";
import { EmptyState, Panel, PanelHeader } from "@/components/primitives";
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { type BudgetSlice, fmtGpu, fmtTokens } from "@/lib/derive";

const config = {
  tokens: { label: "Tokens" },
  cheap: { label: "Cheap path", color: "var(--chart-1)" },
  deep: { label: "Deep path", color: "var(--chart-2)" },
} satisfies ChartConfig;

/** Where the compute actually went. Deep is a minority of tasks and most of the bill. */
export function BudgetChart({ slices }: { slices: BudgetSlice[] }) {
  const total = slices.reduce((a, s) => a + s.tokens, 0);
  const tasks = slices.reduce((a, s) => a + s.tasks, 0);
  const data = slices.map((s) => ({
    ...s,
    label: s.budget === "deep" ? "Deep path" : "Cheap path",
    fill: s.budget === "deep" ? "var(--color-deep)" : "var(--color-cheap)",
  }));

  return (
    <Panel className="flex h-full flex-col">
      <PanelHeader
        title="Where the compute went"
        description="Tokens by budget, with the task count behind each"
        icon={PieIcon}
      />

      {total === 0 ? (
        <div className="flex-1 p-3">
          <EmptyState icon={PieIcon} title="Nothing spent yet" />
        </div>
      ) : (
        <>
          <div className="p-3 pb-0">
            <ChartContainer config={config} className="aspect-auto h-[132px] w-full">
              <BarChart
                data={data}
                layout="vertical"
                margin={{ left: 0, right: 56, top: 4, bottom: 4 }}
                barSize={26}
              >
                <CartesianGrid horizontal={false} strokeDasharray="3 4" />
                <XAxis type="number" dataKey="tokens" hide />
                <YAxis
                  type="category"
                  dataKey="label"
                  tickLine={false}
                  axisLine={false}
                  width={84}
                  tick={{ fontSize: 12 }}
                />
                <ChartTooltip
                  cursor={false}
                  content={
                    <ChartTooltipContent
                      hideLabel
                      formatter={(value, _name, item) => (
                        <div className="grid gap-0.5">
                          <span className="font-medium">{item?.payload?.label}</span>
                          <span className="text-muted-foreground">
                            {fmtTokens(Number(value))} tokens · {fmtGpu(item?.payload?.gpu ?? 0)}{" "}
                            gpu · {item?.payload?.tasks} tasks
                          </span>
                        </div>
                      )}
                    />
                  }
                />
                <Bar dataKey="tokens" radius={6} isAnimationActive={false}>
                  {/* Value labels do the secondary-encoding job the palette check asks for. */}
                  <LabelList
                    dataKey="tokens"
                    position="right"
                    offset={8}
                    className="fill-foreground"
                    fontSize={12}
                    formatter={(v: unknown) => fmtTokens(Number(v))}
                  />
                </Bar>
              </BarChart>
            </ChartContainer>
          </div>

          <div className="mt-auto grid grid-cols-2 divide-x divide-border border-t border-border">
            {data.map((s) => (
              <div key={s.budget} className="px-4 py-2.5">
                <div className="flex items-center gap-1.5">
                  <span className="size-2 rounded-full" style={{ background: s.fill }} aria-hidden />
                  <span className="field-label">{s.label}</span>
                </div>
                <p className="mt-1 flex items-baseline gap-1">
                  <span className="font-mono text-lg leading-none">
                    {total ? Math.round((s.tokens / total) * 100) : 0}%
                  </span>
                  <span className="text-xs text-muted-foreground">of tokens</span>
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {s.tasks} tasks ({tasks ? Math.round((s.tasks / tasks) * 100) : 0}% of the queue)
                </p>
              </div>
            ))}
          </div>
        </>
      )}
    </Panel>
  );
}
