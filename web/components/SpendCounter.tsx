"use client";

const fmt = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${Math.round(n)}`);

export function SpendCounter({
  spend,
  counterfactual,
}: {
  spend: { tokens: number; gpuSeconds: number };
  counterfactual: { tokens: number; gpuSeconds: number };
}) {
  const saved = counterfactual.tokens > 0 ? 1 - spend.tokens / counterfactual.tokens : 0;
  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-950/60 px-4 py-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-400">Spend</h2>
        <span className="text-[10px] uppercase tracking-widest text-emerald-400">
          {saved > 0 ? `${Math.round(saved * 100)}% saved` : "—"}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-4">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-zinc-500">ponder</p>
          <p className="font-mono text-2xl text-zinc-100 tabular-nums">{fmt(spend.tokens)}</p>
          <p className="font-mono text-[11px] text-zinc-500">{spend.gpuSeconds.toFixed(1)} gpu-s</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-widest text-zinc-500">always-deep</p>
          <p className="font-mono text-2xl text-zinc-500 tabular-nums">{fmt(counterfactual.tokens)}</p>
          <p className="font-mono text-[11px] text-zinc-600">
            {counterfactual.gpuSeconds.toFixed(1)} gpu-s
          </p>
        </div>
      </div>

      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-zinc-800">
        <div
          className="h-full rounded-full bg-emerald-400 transition-[width] duration-200"
          style={{
            width: `${counterfactual.tokens ? Math.min(100, (spend.tokens / counterfactual.tokens) * 100) : 0}%`,
          }}
        />
      </div>
    </section>
  );
}
