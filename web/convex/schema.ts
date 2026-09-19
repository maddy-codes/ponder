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
    matchedRule: v.union(v.string(), v.null()),
    ruleReason: v.union(v.string(), v.null()),
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
    // Guardrails the matched rule demanded, and how they ruled on the answer.
    // `guardrailEscalated` means a trip bought deep compute instead of a refusal.
    guardrails: v.optional(v.array(v.string())),
    guardrailVerdicts: v.optional(
      v.array(v.object({ name: v.string(), outcome: v.string(), detail: v.string() }))
    ),
    guardrailEscalated: v.optional(v.boolean()),
    guardrailBlocked: v.optional(v.boolean()),
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
