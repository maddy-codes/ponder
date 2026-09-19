"use client";

import { useState } from "react";
import type { TaskEvent } from "@/lib/types";

const EXAMPLES = [
  "What is the total cost of 3 items at 4.50 each?",
  "What is the capital of Peru?",
  "A patient weighs 24 kg and the dose is 12 mg/kg. What is the dose in mg?",
];

/**
 * Hand the agent one task and watch it decide. Goes through POST /api/ask, which
 * runs the same pipeline as the batch and emits the same TaskEvent -- the panel
 * that renders the result is the same panel, reading the same fields.
 */
export function TaskInput({ onEvent }: { onEvent: (event: TaskEvent) => void }) {
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  async function submit(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(undefined);
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: trimmed }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error ?? `request failed (${res.status})`);
      onEvent(data.event as TaskEvent);
      setPrompt("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-950/60 px-4 py-3">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit(prompt);
        }}
        className="flex items-center gap-2"
      >
        <label
          htmlFor="ask"
          className="shrink-0 text-[10px] font-semibold uppercase tracking-widest text-zinc-500"
        >
          ask ponder
        </label>
        <input
          id="ask"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={busy}
          placeholder="type one task — watch it triage, match a rule, and choose a budget"
          className="min-w-0 flex-1 rounded-md border border-zinc-700 bg-zinc-900/60 px-3 py-1.5 text-sm text-zinc-200 placeholder:text-zinc-600 focus:border-violet-500/60 focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={busy || !prompt.trim()}
          className="shrink-0 rounded-md border border-violet-500/50 bg-violet-500/10 px-3 py-1.5 text-xs font-semibold text-violet-200 hover:bg-violet-500/20 disabled:opacity-40"
        >
          {busy ? "pondering…" : "run"}
        </button>
      </form>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] uppercase tracking-widest text-zinc-600">try</span>
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            disabled={busy}
            onClick={() => {
              setPrompt(example);
              void submit(example);
            }}
            className="rounded border border-zinc-800 px-2 py-0.5 text-[11px] text-zinc-500 hover:border-zinc-600 hover:text-zinc-300 disabled:opacity-40"
          >
            {example.length > 46 ? `${example.slice(0, 44)}…` : example}
          </button>
        ))}
      </div>

      {error && <p className="mt-2 text-xs text-rose-300">{error}</p>}
    </section>
  );
}
