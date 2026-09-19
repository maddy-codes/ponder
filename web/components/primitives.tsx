"use client";

import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** Every panel on the page is this shape: one card, one header rhythm. */
export function Panel({ className, ...props }: React.ComponentProps<typeof Card>) {
  return (
    <Card
      className={cn(
        "gap-0 rounded-xl border border-border bg-card py-0 ring-0 shadow-xs dark:shadow-none",
        className
      )}
      {...props}
    />
  );
}

export function PanelHeader({
  title,
  description,
  icon: Icon,
  children,
  className,
}: {
  title: string;
  description?: string;
  icon?: LucideIcon;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn("flex items-start gap-3 border-b border-border px-4 py-3", className)}
    >
      {Icon && (
        <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-muted">
          <Icon className="size-3.5 text-muted-foreground" aria-hidden />
        </span>
      )}
      <div className="min-w-0">
        <h3 className="text-sm leading-tight font-semibold tracking-tight">{title}</h3>
        {description && (
          <p className="mt-0.5 text-xs leading-snug text-muted-foreground">{description}</p>
        )}
      </div>
      {children && <div className="ml-auto flex shrink-0 items-center gap-2">{children}</div>}
    </header>
  );
}

export function SectionHeading({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex items-end gap-4">
      <div>
        <h2 className="text-base font-semibold tracking-tight">{title}</h2>
        {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
      </div>
      {children && <div className="ml-auto flex items-center gap-2">{children}</div>}
    </div>
  );
}

const TONE_TEXT = {
  neutral: "text-foreground",
  ok: "text-ok",
  rule: "text-rule",
  deep: "text-deep",
  miss: "text-miss",
} as const;

export type Tone = keyof typeof TONE_TEXT;

export function Stat({
  label,
  value,
  unit,
  hint,
  icon: Icon,
  tone = "neutral",
}: {
  label: string;
  value: string;
  unit?: string;
  hint?: React.ReactNode;
  icon: LucideIcon;
  tone?: Tone;
}) {
  return (
    <Panel className="px-4 py-3.5">
      <div className="flex items-center gap-2">
        <Icon className="size-3.5 text-muted-foreground" aria-hidden />
        <span className="field-label">{label}</span>
      </div>
      <div className="mt-2 flex items-baseline gap-1.5">
        <span className={cn("font-mono text-[26px] leading-none font-medium", TONE_TEXT[tone])}>
          {value}
        </span>
        {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
      </div>
      {hint && <p className="mt-2 text-xs leading-snug text-muted-foreground">{hint}</p>}
    </Panel>
  );
}

/** 0..1 gauge. The colour carries the meaning: difficulty is cool, stakes is warm. */
export function Gauge({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "difficulty" | "stakes";
}) {
  const clamped = Math.min(1, Math.max(0, value));
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="field-label">{label}</span>
        <span className="font-mono text-sm">{value.toFixed(2)}</span>
      </div>
      <div
        className="mt-2 h-2 overflow-hidden rounded-full bg-muted"
        role="meter"
        aria-label={label}
        aria-valuenow={Math.round(clamped * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-300 ease-out",
            tone === "stakes" ? "bg-stakes" : "bg-difficulty"
          )}
          style={{ width: `${clamped * 100}%` }}
        />
      </div>
    </div>
  );
}

export function BudgetTag({
  budget,
  className,
}: {
  budget: "cheap" | "deep";
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium",
        budget === "deep"
          ? "bg-deep/12 text-deep"
          : "bg-cheap/12 text-cheap",
        className
      )}
    >
      {budget}
    </span>
  );
}

export function RuleTag({ rule, className }: { rule: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-md bg-rule/12 px-1.5 py-0.5 font-mono text-[11px] text-rule",
        className
      )}
    >
      {rule}
    </span>
  );
}

export function VerdictTag({ correct }: { correct: boolean | null }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium",
        correct === null
          ? "bg-muted text-muted-foreground"
          : correct
            ? "bg-ok/12 text-ok"
            : "bg-miss/12 text-miss"
      )}
    >
      {correct === null ? "ungraded" : correct ? "correct" : "miss"}
    </span>
  );
}

export function Dot({ className }: { className?: string }) {
  return <span className={cn("size-2 shrink-0 rounded-full", className)} />;
}

export function EmptyState({
  icon: Icon,
  title,
  body,
}: {
  icon: LucideIcon;
  title: string;
  body?: string;
}) {
  return (
    <div className="flex h-full min-h-32 flex-col items-center justify-center px-6 text-center">
      <Icon className="size-5 text-muted-foreground/60" aria-hidden />
      <p className="mt-2 text-sm font-medium">{title}</p>
      {body && <p className="mt-1 max-w-sm text-xs text-muted-foreground">{body}</p>}
    </div>
  );
}
