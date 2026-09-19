"use client";

/**
 * The Convex side of "instrument once, fan out".
 *
 * The agent emits every TaskEvent to three sinks; `events.jsonl` drives Replay and
 * this drives the live view. Run `python -m agent.loop` in a terminal and the tasks
 * land on the dashboard as they finish, without a page refresh.
 *
 * Deliberately additive: when NEXT_PUBLIC_CONVEX_URL is unset nothing renders, no
 * hook runs, and Replay behaves exactly as before. Convex being down must never be
 * able to take the demo with it.
 */

import { useEffect, useRef } from "react";
import { ConvexProvider, ConvexReactClient, useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import type { TaskEvent } from "@/lib/types";

const url = process.env.NEXT_PUBLIC_CONVEX_URL;
const client = url ? new ConvexReactClient(url) : null;

/** Convex stores camelCase (it owns `_id`); the renderer speaks the Python contract. */
function fromConvex(row: Record<string, unknown>): TaskEvent {
  const n = (v: unknown, d = 0) => (typeof v === "number" ? v : d);
  const s = (v: unknown, d = "") => (typeof v === "string" ? v : d);
  return {
    id: s(row.taskId),
    prompt_preview: s(row.promptPreview),
    difficulty: n(row.difficulty),
    stakes: n(row.stakes),
    budget: s(row.budget, "cheap") as TaskEvent["budget"],
    matched_rule: (row.matchedRule ?? null) as string | null,
    rule_reason: (row.ruleReason ?? null) as string | null,
    rule_id: s(row.ruleId),
    strategy: s(row.strategy, "ponder") as TaskEvent["strategy"],
    samples: ((row.samples ?? []) as Record<string, unknown>[]).map((x) => ({
      status: s(x.status, "done") as "running" | "done" | "failed",
      tokens: n(x.tokens),
      gpu_seconds: n(x.gpuSeconds),
    })),
    sandbox_ran: Boolean(row.sandboxRan),
    sandbox_passed: (row.sandboxPassed ?? null) as boolean | null,
    answer: (row.answer ?? null) as string | null,
    correct: (row.correct ?? null) as boolean | null,
    latency_ms: n(row.latencyMs),
    total_tokens: n(row.totalTokens),
    total_gpu_seconds: n(row.totalGpuSeconds),
    logfire_trace_url: (row.logfireTraceUrl ?? null) as string | null,
    status: s(row.status, "done") as TaskEvent["status"],
    ts: n(row.ts),
  };
}

function Feed({ onEvent }: { onEvent: (e: TaskEvent) => void }) {
  const rows = useQuery(api.events.list, { strategy: "ponder" });
  // The first snapshot is history, not news: adopting it would replay the whole
  // table through the live animation the moment the page opens.
  const seen = useRef<Set<string> | null>(null);

  useEffect(() => {
    if (!rows) return;
    if (seen.current === null) {
      seen.current = new Set(rows.map((r) => String(r.taskId)));
      return;
    }
    for (const row of rows) {
      const id = String(row.taskId);
      if (seen.current.has(id)) continue;
      seen.current.add(id);
      onEvent(fromConvex(row as Record<string, unknown>));
    }
  }, [rows, onEvent]);

  return null;
}

export function ConvexLive({ onEvent }: { onEvent: (e: TaskEvent) => void }) {
  if (!client) return null;
  return (
    <ConvexProvider client={client}>
      <Feed onEvent={onEvent} />
    </ConvexProvider>
  );
}
