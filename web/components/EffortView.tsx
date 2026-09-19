"use client";

import { bareId, escalatedOnStakes, type TaskEvent } from "@/lib/types";
import type { Stage } from "@/lib/useRun";

function Meter({ label, value, tone }: { label: string; value: number; tone: "diff" | "stakes" }) {
  const pct = Math.round(value * 100);
  const bar = tone === "stakes" ? "bg-amber-400" : "bg-sky-400";
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
          {label}
        </span>
        <span className="font-mono text-sm text-zinc-200">{value.toFixed(2)}</span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-zinc-800">
        <div
          className={`h-full rounded-full ${bar} transition-[width] duration-200`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function EffortView({
  event,
  stage,
  samplesLit,
}: {
  event?: TaskEvent;
  stage: Stage;
  samplesLit: number;
}) {
  if (!event) {
    return (
      <section className="flex h-full items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950/60 text-sm text-zinc-600">
        run complete
      </section>
    );
  }

  const money = escalatedOnStakes(event) && event.stakes >= 0.66;
  const lit = event.samples.slice(0, Math.max(samplesLit, 1));

  return (
    <section
      className={`flex h-full flex-col rounded-xl border bg-zinc-950/60 transition-colors ${
        money ? "border-amber-500/60 shadow-[0_0_40px_-12px] shadow-amber-500/30" : "border-zinc-800"
      }`}
    >
      <header className="flex items-center gap-3 border-b border-zinc-800 px-5 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
          Effort allocation
        </h2>
        <span className="font-mono text-xs text-zinc-600">{bareId(event)}</span>
        <span className="ml-auto flex items-center gap-2">
          <span
            className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest ${
              event.budget === "deep"
                ? "bg-orange-400/15 text-orange-300"
                : "bg-emerald-400/15 text-emerald-300"
            }`}
          >
            {event.budget} path
          </span>
        </span>
      </header>

      <div className="flex-1 space-y-5 px-5 py-4">
        <p className="text-sm leading-relaxed text-zinc-300">{event.prompt_preview}</p>

        <div className="grid grid-cols-2 gap-5">
          <Meter label="difficulty" value={event.difficulty} tone="diff" />
          <Meter label="stakes" value={event.stakes} tone="stakes" />
        </div>

        {money && (
          <div className="pop rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2">
            <p className="text-xs font-semibold uppercase tracking-widest text-amber-300">
              escalated on stakes
            </p>
            <p className="mt-0.5 text-xs text-amber-100/80">
              Looks easy ({event.difficulty.toFixed(2)}), but being wrong is expensive (
              {event.stakes.toFixed(2)}). A difficulty router spends nothing here.
            </p>
          </div>
        )}

        <div>
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
              gateway rule
            </span>
            <code className="rounded bg-zinc-900 px-2 py-0.5 font-mono text-[11px] text-violet-300">
              {event.rule_id}
            </code>
          </div>
        </div>

        <div>
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
              modal samples · best-of-{event.samples.length}
            </span>
            <span className="font-mono text-[11px] text-zinc-400">
              {event.total_gpu_seconds.toFixed(2)} gpu-s
            </span>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {event.samples.map((s, i) => {
              const on = i < lit.length;
              return (
                <div
                  key={i}
                  className={`flex h-9 w-14 flex-col items-center justify-center rounded border text-[9px] font-mono transition-all duration-150 ${
                    on
                      ? s.status === "failed"
                        ? "border-rose-500/50 bg-rose-500/10 text-rose-300"
                        : "border-sky-500/50 bg-sky-500/10 text-sky-300"
                      : "border-zinc-800 bg-zinc-900/40 text-zinc-700"
                  }`}
                >
                  <span>{on ? s.tokens : "—"}</span>
                  <span className="text-[8px] opacity-70">{on ? `${s.gpu_seconds.toFixed(1)}s` : ""}</span>
                </div>
              );
            })}
          </div>
        </div>

        {event.sandbox_ran && (
          <div
            className={`flex items-center gap-2 rounded-lg border px-3 py-2 ${
              stage === "verifying"
                ? "border-sky-500/50 bg-sky-500/10"
                : event.sandbox_passed === false
                  ? "border-rose-500/40 bg-rose-500/10"
                  : "border-emerald-500/40 bg-emerald-500/10"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                stage === "verifying" ? "bg-sky-400 ring-pulse" : event.sandbox_passed === false ? "bg-rose-400" : "bg-emerald-400"
              }`}
            />
            <span className="text-xs text-zinc-300">
              {stage === "verifying"
                ? "executing verification in Modal sandbox…"
                : event.sandbox_passed === false
                  ? "sandbox disagreed — answer replaced by the executed value"
                  : event.sandbox_passed === null
                    ? "sandbox inconclusive — answer kept and flagged"
                    : "sandbox verified the answer"}
            </span>
          </div>
        )}
      </div>

      <footer className="border-t border-zinc-800 px-5 py-2.5">
        <div className="flex items-center gap-3 text-xs">
          <span className="text-[10px] uppercase tracking-widest text-zinc-500">answer</span>
          <span className="flex-1 truncate font-mono text-zinc-300">
            {stage === "done" ? (event.answer ?? "—") : "…"}
          </span>
          {stage === "done" && (
            <span
              className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest ${
                event.correct ? "bg-emerald-400/15 text-emerald-300" : "bg-rose-500/15 text-rose-300"
              }`}
            >
              {event.correct ? "correct" : "miss"}
            </span>
          )}
        </div>
      </footer>
    </section>
  );
}
