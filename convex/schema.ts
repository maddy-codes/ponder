import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

// Mirrors agent/events.py::TaskEvent. `id` there becomes `taskId` here because
// Convex owns `_id`. Change both sides together or not at all.
export default defineSchema({
  taskEvents: defineTable({
    taskId: v.string(),
    promptPreview: v.string(),
    difficulty: v.number(),
    stakes: v.number(),
    budget: v.string(),
    ruleId: v.string(),
    strategy: v.string(),
    samples: v.array(
      v.object({
        status: v.string(),
        tokens: v.number(),
        gpuSeconds: v.number(),
      })
    ),
    sandboxRan: v.boolean(),
    sandboxPassed: v.union(v.boolean(), v.null()),
    answer: v.union(v.string(), v.null()),
    correct: v.union(v.boolean(), v.null()),
    latencyMs: v.number(),
    totalTokens: v.number(),
    totalGpuSeconds: v.number(),
    logfireTraceUrl: v.union(v.string(), v.null()),
    status: v.string(),
    ts: v.number(),
  }).index("by_task", ["taskId"]),
});
