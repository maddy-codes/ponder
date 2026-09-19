"use client";

import { Crosshair } from "lucide-react";
import {
  CartesianGrid,
  Cell,
  ReferenceArea,
  Scatter,
  ScatterChart,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { EmptyState, Panel, PanelHeader } from "@/components/primitives";
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { type DecisionPoint, fmtTokens } from "@/lib/derive";

const config = {
  cheap: { label: "Cheap path", color: "var(--chart-1)" },
  deep: { label: "Deep path", color: "var(--chart-2)" },
} satisfies ChartConfig;

/**
 * The thesis in one picture. A difficulty-only router would draw a vertical split;
 * Ponder's deep spend fills the top-left too -- easy-looking, expensive-to-get-wrong.
 * Click any dot to open that task.
 */
export function DecisionMap({
  points,
  focusId,
  dimOthers,
  onSelect,
}: {
  points: DecisionPoint[];
  /** ringed, because the console is showing it */
  focusId: string | null;
  /** only true once the user has explicitly picked a task */
  dimOthers: boolean;
  onSelect: (bareId: string) => void;
}) {
  return (
    <Panel className="flex h-full flex-col">
      <PanelHeader
        title="Decision map"
        description="Difficulty (x) against stakes (y) — dot size is tokens spent. Click one to open it."
        icon={Crosshair}
      >
        <div className="flex items-center gap-3">
          {(["cheap", "deep"] as const).map((k) => (
            <span key={k} className="flex items-center gap-1.5">
              <span
                className="size-2 rounded-full"
                style={{ background: config[k].color }}
                aria-hidden
              />
              <span className="text-xs text-muted-foreground">{config[k].label}</span>
            </span>
          ))}
        </div>
      </PanelHeader>

      <div className="flex-1 p-3">
        {points.length === 0 ? (
          <EmptyState icon={Crosshair} title="No decisions recorded yet" />
        ) : (
          <ChartContainer config={config} className="aspect-auto h-full min-h-56 w-full">
            <ScatterChart margin={{ left: 0, right: 12, top: 10, bottom: 14 }}>
              {/* The quadrant a pure difficulty router gets wrong. */}
              <ReferenceArea
                x1={0}
                x2={0.55}
                y1={0.66}
                y2={1}
                fill="var(--stakes)"
                fillOpacity={0.06}
                stroke="var(--stakes)"
                strokeOpacity={0.2}
                strokeDasharray="3 4"
                label={{
                  value: "looks easy, costly if wrong",
                  position: "insideTopLeft",
                  fontSize: 10,
                  fill: "var(--muted-foreground)",
                  offset: 8,
                }}
              />
              <CartesianGrid strokeDasharray="3 4" />
              <XAxis
                type="number"
                dataKey="difficulty"
                name="Difficulty"
                domain={[0, 1]}
                ticks={[0, 0.25, 0.5, 0.75, 1]}
                tickLine={false}
                axisLine={false}
                tickMargin={6}
                label={{
                  value: "difficulty",
                  position: "insideBottom",
                  offset: -8,
                  fontSize: 11,
                  fill: "var(--muted-foreground)",
                }}
              />
              <YAxis
                type="number"
                dataKey="stakes"
                name="Stakes"
                domain={[0, 1]}
                ticks={[0, 0.5, 1]}
                tickLine={false}
                axisLine={false}
                width={40}
              />
              <ZAxis type="number" dataKey="tokens" range={[60, 420]} />
              <ChartTooltip
                cursor={{ strokeDasharray: "3 3" }}
                content={
                  <ChartTooltipContent
                    hideLabel
                    formatter={(_v, _n, item) => {
                      const p = item?.payload as DecisionPoint | undefined;
                      if (!p) return null;
                      return (
                        <div className="grid max-w-56 gap-1">
                          <span className="font-mono text-xs">{p.id}</span>
                          <span className="line-clamp-2 text-muted-foreground">{p.prompt}</span>
                          <span className="text-muted-foreground">
                            {p.budget} · {fmtTokens(p.tokens)} tokens
                            {p.rule ? ` · ${p.rule}` : ""}
                          </span>
                        </div>
                      );
                    }}
                  />
                }
              />
              <Scatter
                data={points}
                isAnimationActive={false}
                onClick={(d: unknown) => {
                  const p = (d as { payload?: DecisionPoint })?.payload;
                  if (p) onSelect(p.id);
                }}
                className="cursor-pointer"
              >
                {points.map((p) => (
                  <Cell
                    key={p.id}
                    fill={p.budget === "deep" ? "var(--color-deep)" : "var(--color-cheap)"}
                    fillOpacity={dimOthers && focusId !== p.id ? 0.3 : 0.85}
                    stroke={focusId === p.id ? "var(--foreground)" : "var(--card)"}
                    strokeWidth={focusId === p.id ? 2.5 : 1.5}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ChartContainer>
        )}
      </div>
    </Panel>
  );
}
