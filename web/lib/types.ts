export type Sample = { status: string; tokens: number; gpu_seconds: number };

/** One named guardrail's verdict on the answer that was about to be returned. */
export type GuardrailVerdict = {
  name: string;
  outcome: "allow" | "retry" | "block" | "replace";
  detail: string;
};

/** Mirrors agent/events.py::TaskEvent, verbatim off events.jsonl. */
export type TaskEvent = {
  id: string;
  prompt_preview: string;
  difficulty: number;
  stakes: number;
  budget: "cheap" | "deep";
  /** named domain rule that decided, from agent/rules.py */
  matched_rule: string | null;
  rule_reason: string | null;
  rule_id: string;
  strategy: "cheap" | "deep" | "ponder";
  samples: Sample[];
  sandbox_ran: boolean;
  sandbox_passed: boolean | null;
  /** guardrails the matched rule demanded (agent/rules.json -> then.guardrails) */
  guardrails?: string[];
  guardrail_verdicts?: GuardrailVerdict[];
  /** a guardrail trip bought deep compute rather than returning a refusal */
  guardrail_escalated?: boolean;
  guardrail_blocked?: boolean;
  answer: string | null;
  correct: boolean | null;
  latency_ms: number;
  total_tokens: number;
  total_gpu_seconds: number;
  logfire_trace_url: string | null;
  status: "queued" | "thinking" | "verifying" | "done";
  ts: number;
};

export type StrategyReport = {
  strategy: string;
  n: number;
  correct: number;
  accuracy: number;
  high_stakes_n: number;
  high_stakes_correct: number;
  high_stakes_accuracy: number;
  total_tokens: number;
  total_gpu_seconds: number;
  deep_tasks: number;
  sandbox_runs: number;
  misses: string[];
  low_stakes_share_of_misses: number;
};

export type Frontier = { reports: StrategyReport[]; verdict: string[] };

export type RuleProof = {
  task: string;
  rule_off: { rule_id: string; tokens: number; trace_url: string | null; answer: string };
  rule_on: { rule_id: string; tokens: number; trace_url: string | null; answer: string };
  token_delta: number;
  token_delta_pct: number;
};

/** The money shot: deep compute spent on something that did not look hard. */
export const escalatedOnStakes = (e: TaskEvent) => e.budget === "deep" && e.difficulty < 0.55;

export const bareId = (e: TaskEvent) => e.id.split(":").pop() ?? e.id;

/** The rule engine visibly outranking the classifier. */
export const ruleOverrode = (e: TaskEvent) =>
  Boolean(e.matched_rule) && (e.rule_reason ?? "").includes("would have spent");
