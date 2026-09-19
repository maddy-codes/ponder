export type Sample = { status: string; tokens: number; gpu_seconds: number };

/** Mirrors agent/events.py::TaskEvent, verbatim off events.jsonl. */
export type TaskEvent = {
  id: string;
  prompt_preview: string;
  difficulty: number;
  stakes: number;
  budget: "cheap" | "deep";
  rule_id: string;
  strategy: "cheap" | "deep" | "ponder";
  samples: Sample[];
  sandbox_ran: boolean;
  sandbox_passed: boolean | null;
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
