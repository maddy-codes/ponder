import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

// The Python emitter sends the TaskEvent verbatim (snake_case). Normalising here
// keeps the contract in one place and the client in camelCase.
const normalise = (e: any) => ({
  taskId: String(e.id),
  promptPreview: String(e.prompt_preview ?? ""),
  difficulty: Number(e.difficulty ?? 0),
  stakes: Number(e.stakes ?? 0),
  budget: String(e.budget ?? "cheap"),
  ruleId: String(e.rule_id ?? ""),
  strategy: String(e.strategy ?? "ponder"),
  samples: (e.samples ?? []).map((s: any) => ({
    status: String(s.status ?? "running"),
    tokens: Number(s.tokens ?? 0),
    gpuSeconds: Number(s.gpu_seconds ?? 0),
  })),
  sandboxRan: Boolean(e.sandbox_ran ?? false),
  sandboxPassed: e.sandbox_passed ?? null,
  answer: e.answer ?? null,
  correct: e.correct ?? null,
  latencyMs: Number(e.latency_ms ?? 0),
  totalTokens: Number(e.total_tokens ?? 0),
  totalGpuSeconds: Number(e.total_gpu_seconds ?? 0),
  logfireTraceUrl: e.logfire_trace_url ?? null,
  status: String(e.status ?? "queued"),
  ts: Number(e.ts ?? Date.now() / 1000),
});

/** Upsert by taskId, so one task stays one row however many progress pushes arrive. */
export const upsert = mutation({
  args: { event: v.any() },
  handler: async (ctx, { event }) => {
    const doc = normalise(event);
    const existing = await ctx.db
      .query("taskEvents")
      .withIndex("by_task", (q) => q.eq("taskId", doc.taskId))
      .unique();
    if (existing) {
      await ctx.db.patch(existing._id, doc);
      return existing._id;
    }
    return await ctx.db.insert("taskEvents", doc);
  },
});

export const list = query({
  args: { strategy: v.optional(v.string()) },
  handler: async (ctx, { strategy }) => {
    const all = await ctx.db.query("taskEvents").collect();
    const rows = strategy ? all.filter((r) => r.strategy === strategy) : all;
    return rows.sort((a, b) => a.ts - b.ts);
  },
});

export const clear = mutation({
  args: {},
  handler: async (ctx) => {
    for (const row of await ctx.db.query("taskEvents").collect()) {
      await ctx.db.delete(row._id);
    }
  },
});
