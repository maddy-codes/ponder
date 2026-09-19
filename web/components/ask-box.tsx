"use client";

import { useState } from "react";
import { CornerDownLeft, Loader2, TriangleAlert } from "lucide-react";
import { Panel } from "@/components/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { TaskEvent } from "@/lib/types";

const EXAMPLES = [
  "What is the total cost of 3 items at 4.50 each?",
  "What is the capital of Peru?",
  "A patient weighs 24 kg and the dose is 12 mg/kg. What is the dose in mg?",
];

/**
 * Hand the agent one task and watch it decide. Goes through POST /api/ask, which runs
 * the same pipeline as the batch and emits the same TaskEvent -- the panel that renders
 * the result is the same panel, reading the same fields.
 */
export function AskBox({ onEvent }: { onEvent: (event: TaskEvent) => void }) {
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
    <Panel className="px-4 py-3.5">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit(prompt);
        }}
        className="flex items-center gap-2.5"
      >
        <label htmlFor="ask" className="sr-only">
          Ask Ponder a task
        </label>
        <Input
          id="ask"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={busy}
          autoComplete="off"
          placeholder="Ask Ponder a task and watch it choose a budget…"
          className="h-10 flex-1 text-sm"
        />
        <Button type="submit" disabled={busy || !prompt.trim()} size="lg" className="h-10 px-4">
          {busy ? (
            <>
              <Loader2 className="animate-spin" />
              Thinking
            </>
          ) : (
            <>
              Run
              <CornerDownLeft data-icon="inline-end" />
            </>
          )}
        </Button>
      </form>

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <span className="mr-0.5 text-xs text-muted-foreground">Try</span>
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            disabled={busy}
            onClick={() => {
              setPrompt(example);
              void submit(example);
            }}
            className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
          >
            {example.length > 52 ? `${example.slice(0, 50)}…` : example}
          </button>
        ))}
      </div>

      {error && (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-destructive">
          <TriangleAlert className="size-3.5" aria-hidden />
          {error}
        </p>
      )}
    </Panel>
  );
}
