"use client";

import { bareId, escalatedOnStakes, type TaskEvent } from "@/lib/types";

const dot = (e: TaskEvent) =>
  e.correct ? "bg-emerald-400" : "bg-rose-500";

export function Queue({
  completed,
  current,
  total,
}: {
  completed: TaskEvent[];
  current?: TaskEvent;
  total: number;
}) {
  const rows = [...completed].reverse().slice(0, 14);
  return (
    <section className="flex h-full flex-col rounded-xl border border-zinc-800 bg-zinc-950/60">
      <header className="flex items-baseline justify-between border-b border-zinc-800 px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-400">Queue</h2>
        <span className="text-xs tabular-nums text-zinc-500">
          {completed.length}/{total}
        </span>
      </header>

      <div className="flex-1 overflow-hidden">
        {current && (
          <div className="border-b border-zinc-800 bg-sky-500/5 px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 shrink-0 rounded-full bg-sky-400 ring-pulse" />
              <span className="font-mono text-xs text-sky-300">{bareId(current)}</span>
              <span className="ml-auto text-[10px] uppercase tracking-wider text-sky-400/80">
                running
              </span>
            </div>
            <p className="mt-1 line-clamp-2 text-xs leading-snug text-zinc-400">
              {current.prompt_preview}
            </p>
          </div>
        )}

        <ul className="divide-y divide-zinc-900">
          {rows.map((e) => (
            <li key={e.id} className="pop flex items-center gap-2 px-4 py-2">
              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot(e)}`} />
              <span className="font-mono text-[11px] text-zinc-500">{bareId(e)}</span>
              <span className="flex-1 truncate text-xs text-zinc-400">{e.prompt_preview}</span>
              {escalatedOnStakes(e) && (
                <span className="shrink-0 rounded bg-amber-400/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-300">
                  stakes
                </span>
              )}
              <span
                className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider ${
                  e.budget === "deep"
                    ? "bg-orange-400/10 text-orange-300"
                    : "bg-zinc-700/40 text-zinc-400"
                }`}
              >
                {e.budget}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
