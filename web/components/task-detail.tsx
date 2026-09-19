"use client";

import Image from "next/image";
import {
  ArrowRight,
  Brain,
  Clock,
  Cpu,
  ExternalLink,
  FlaskConical,
  Hash,
  Scale,
  SlidersHorizontal,
} from "lucide-react";
import {
  BudgetTag,
  Dot,
  Gauge,
  Panel,
  PanelHeader,
  VerdictTag,
} from "@/components/primitives";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { fmtGpu, fmtTokens } from "@/lib/derive";
import { bareId, escalatedOnStakes, ruleOverrode, type TaskEvent } from "@/lib/types";
import type { Stage } from "@/lib/useRun";
import { cn } from "@/lib/utils";

function ChainStep({
  label,
  value,
  tone = "muted",
}: {
  label: string;
  value: string;
  tone?: "muted" | "rule" | "deep" | "cheap";
}) {
  return (
    <span
      className={cn(
        "flex items-center gap-2 rounded-lg border px-2.5 py-1.5",
        {
          muted: "border-border bg-muted/50",
          rule: "border-rule/30 bg-rule/8 text-rule",
          deep: "border-deep/30 bg-deep/8 text-deep",
          cheap: "border-cheap/30 bg-cheap/8 text-cheap",
        }[tone]
      )}
    >
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className="font-mono text-xs">{value}</span>
    </span>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Hash;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="ml-auto font-mono text-xs">{value}</span>
    </div>
  );
}

export function TaskDetail({
  event,
  stage,
  samplesLit,
  live,
}: {
  event?: TaskEvent;
  stage: Stage;
  samplesLit: number;
  live: boolean;
}) {
  if (!event) {
    return (
      <Panel className="flex h-full items-center justify-center">
        <div className="px-6 text-center">
          <Image
            src="/ponder-mark.png"
            alt=""
            width={185}
            height={192}
            className="mx-auto h-9 w-auto opacity-25 dark:hidden"
          />
          <Image
            src="/ponder-mark-dark.png"
            alt=""
            width={185}
            height={192}
            className="mx-auto hidden h-9 w-auto opacity-30 dark:block"
          />
          <p className="mt-3 text-sm font-medium">No task selected</p>
          <p className="mt-1 max-w-sm text-xs text-muted-foreground">
            Pick any task in the queue, the decision map or the task log to see exactly how its
            budget was decided.
          </p>
        </div>
      </Panel>
    );
  }

  // Only the live task animates; a task you clicked into is shown finished.
  const shownStage: Stage = live ? stage : "done";
  const lit = live ? Math.max(samplesLit, 1) : event.samples.length;
  const overrode = ruleOverrode(event);
  const escalated = escalatedOnStakes(event) && event.stakes >= 0.66;

  return (
    <Panel className="flex h-full min-h-0 flex-col">
      <PanelHeader
        title="How hard to think"
        description={live ? "Live — the agent is deciding now" : "Recorded decision"}
        icon={Brain}
      >
        <span className="font-mono text-xs text-muted-foreground">{bareId(event)}</span>
        {live && shownStage !== "done" && (
          <span className="flex items-center gap-1.5 rounded-md bg-live/12 px-2 py-0.5 text-[11px] font-medium text-live">
            <Dot className="breathe size-1.5 bg-live" />
            {shownStage}
          </span>
        )}
        <BudgetTag budget={event.budget} />
      </PanelHeader>

      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-5 px-4 py-4">
          <p className="text-sm leading-relaxed">{event.prompt_preview}</p>

          {/* triage → rule → budget → spend, straight off the event's own fields */}
          <div className="flex flex-wrap items-center gap-1.5">
            <ChainStep
              label="triage"
              value={`${event.difficulty.toFixed(2)} × ${event.stakes.toFixed(2)}`}
            />
            <ArrowRight className="size-3 shrink-0 text-muted-foreground/50" aria-hidden />
            <ChainStep
              label="rule"
              value={event.matched_rule ?? "none"}
              tone={event.matched_rule ? "rule" : "muted"}
            />
            <ArrowRight className="size-3 shrink-0 text-muted-foreground/50" aria-hidden />
            <ChainStep
              label="budget"
              value={event.budget}
              tone={event.budget === "deep" ? "deep" : "cheap"}
            />
            <ArrowRight className="size-3 shrink-0 text-muted-foreground/50" aria-hidden />
            <ChainStep
              label="spend"
              value={`${event.samples.length} sample${event.samples.length === 1 ? "" : "s"}${
                event.sandbox_ran ? " + sandbox" : ""
              }`}
            />
          </div>

          <div className="grid grid-cols-2 gap-5">
            <Gauge label="Difficulty" value={event.difficulty} tone="difficulty" />
            <Gauge label="Stakes" value={event.stakes} tone="stakes" />
          </div>

          {event.matched_rule ? (
            <div
              className={cn(
                "rounded-lg border px-3.5 py-3",
                overrode ? "border-rule/35 bg-rule/6" : "border-border bg-muted/40"
              )}
            >
              <div className="flex items-center gap-2">
                <Scale className="size-3.5 text-rule" aria-hidden />
                <span className="text-xs font-medium text-rule">Domain rule</span>
                <code className="font-mono text-xs text-rule">{event.matched_rule}</code>
                <span
                  className={cn(
                    "ml-auto shrink-0 rounded-md px-1.5 py-0.5 text-[11px] font-medium",
                    overrode ? "bg-rule/12 text-rule" : "bg-muted text-muted-foreground"
                  )}
                >
                  {overrode ? "overrode the score" : "confirmed the score"}
                </span>
              </div>
              <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                {event.rule_reason}
              </p>
            </div>
          ) : (
            <div className="rounded-lg border border-border bg-muted/30 px-3.5 py-2.5">
              <span className="text-xs font-medium">No named rule matched</span>
              <p className="mt-0.5 text-xs text-muted-foreground">
                The difficulty × stakes score decided this one on its own.
              </p>
            </div>
          )}

          {escalated && !overrode && (
            <div className="rounded-lg border border-stakes/35 bg-stakes/6 px-3.5 py-3">
              <p className="text-xs font-medium text-stakes">Escalated on stakes</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Looks easy ({event.difficulty.toFixed(2)}), but being wrong is expensive (
                {event.stakes.toFixed(2)}). A router that only reads difficulty spends nothing here.
              </p>
            </div>
          )}

          <Separator />

          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <SlidersHorizontal className="size-3.5 text-muted-foreground" aria-hidden />
              <span className="field-label">Gateway rule</span>
              <code className="ml-auto rounded-md bg-rule/10 px-2 py-1 font-mono text-xs text-rule">
                {event.rule_id}
              </code>
            </div>

            <div>
              <div className="flex items-center gap-2">
                <Cpu className="size-3.5 text-muted-foreground" aria-hidden />
                <span className="field-label">
                  Modal fan-out · best of {event.samples.length}
                </span>
                <span className="ml-auto font-mono text-xs text-muted-foreground">
                  {fmtGpu(event.total_gpu_seconds)} gpu
                </span>
              </div>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {event.samples.map((s, i) => {
                  const on = i < lit;
                  const failed = s.status === "failed";
                  return (
                    <div
                      key={i}
                      title={`sample ${i + 1}: ${s.status}, ${s.tokens} tokens, ${s.gpu_seconds.toFixed(2)}s`}
                      className={cn(
                        "flex h-11 w-16 flex-col items-center justify-center rounded-lg border transition-colors",
                        !on && "border-dashed border-border bg-muted/30 text-muted-foreground/50",
                        on && failed && "border-miss/35 bg-miss/8 text-miss",
                        on && !failed && "border-border bg-muted/60 text-foreground"
                      )}
                    >
                      <span className="font-mono text-xs">{on ? s.tokens : "—"}</span>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {on ? `${s.gpu_seconds.toFixed(1)}s` : ""}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {event.sandbox_ran && (
              <div
                className={cn(
                  "flex items-center gap-2.5 rounded-lg border px-3.5 py-2.5",
                  shownStage === "verifying"
                    ? "border-live/35 bg-live/6"
                    : event.sandbox_passed === false
                      ? "border-miss/35 bg-miss/6"
                      : event.sandbox_passed === null
                        ? "border-deep/35 bg-deep/6"
                        : "border-ok/35 bg-ok/6"
                )}
              >
                <FlaskConical
                  className={cn(
                    "size-4 shrink-0",
                    shownStage === "verifying"
                      ? "text-live"
                      : event.sandbox_passed === false
                        ? "text-miss"
                        : event.sandbox_passed === null
                          ? "text-deep"
                          : "text-ok"
                  )}
                  aria-hidden
                />
                <span className="text-xs">
                  {shownStage === "verifying"
                    ? "Executing verification in a Modal sandbox…"
                    : event.sandbox_passed === false
                      ? "Sandbox disagreed — the answer was replaced by the executed value"
                      : event.sandbox_passed === null
                        ? "Sandbox inconclusive — the answer was kept and flagged"
                        : "Sandbox executed the check and agreed"}
                </span>
              </div>
            )}
          </div>

          <Separator />

          <div className="grid grid-cols-2 gap-x-6 gap-y-2">
            <Metric icon={Hash} label="Tokens" value={fmtTokens(event.total_tokens)} />
            <Metric icon={Cpu} label="GPU" value={fmtGpu(event.total_gpu_seconds)} />
            <Metric icon={Clock} label="Latency" value={`${event.latency_ms} ms`} />
            <Metric icon={Scale} label="Strategy" value={event.strategy} />
          </div>

          {event.logfire_trace_url && (
            <a
              href={event.logfire_trace_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-rule hover:underline"
            >
              Open the Logfire trace
              <ExternalLink className="size-3" aria-hidden />
            </a>
          )}
        </div>
      </ScrollArea>

      <footer className="flex shrink-0 items-center gap-3 border-t border-border bg-muted/30 px-4 py-3">
        <span className="field-label shrink-0">Answer</span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs">
          {shownStage === "done" ? (event.answer ?? "—") : "…"}
        </span>
        {shownStage === "done" && <VerdictTag correct={event.correct} />}
      </footer>
    </Panel>
  );
}
