import { bareId, ruleOverrode, type TaskEvent } from "./types";

export const fmtTokens = (n: number) =>
  n >= 1_000_000
    ? `${(n / 1_000_000).toFixed(2)}M`
    : n >= 1000
      ? `${(n / 1000).toFixed(1)}k`
      : `${Math.round(n)}`;

export const fmtGpu = (n: number) => (n >= 100 ? `${Math.round(n)}s` : `${n.toFixed(1)}s`);

export const pct = (n: number) => `${Math.round(n * 100)}%`;

export type Totals = {
  n: number;
  deep: number;
  cheap: number;
  tokens: number;
  gpu: number;
  counterTokens: number;
  counterGpu: number;
  sandboxRuns: number;
  sandboxPassed: number;
  graded: number;
  correct: number;
  matched: number;
  overrides: number;
  highStakes: number;
  highStakesCorrect: number;
};

/** One pass over the landed events; every KPI on the page reads off this. */
export function totals(events: TaskEvent[], twins: Map<string, TaskEvent>): Totals {
  const t: Totals = {
    n: 0,
    deep: 0,
    cheap: 0,
    tokens: 0,
    gpu: 0,
    counterTokens: 0,
    counterGpu: 0,
    sandboxRuns: 0,
    sandboxPassed: 0,
    graded: 0,
    correct: 0,
    matched: 0,
    overrides: 0,
    highStakes: 0,
    highStakesCorrect: 0,
  };

  for (const e of events) {
    const twin = twins.get(bareId(e));
    t.n += 1;
    if (e.budget === "deep") t.deep += 1;
    else t.cheap += 1;
    t.tokens += e.total_tokens;
    t.gpu += e.total_gpu_seconds;
    t.counterTokens += twin?.total_tokens ?? e.total_tokens;
    t.counterGpu += twin?.total_gpu_seconds ?? e.total_gpu_seconds;
    if (e.sandbox_ran) t.sandboxRuns += 1;
    if (e.sandbox_passed === true) t.sandboxPassed += 1;
    if (e.correct !== null) {
      t.graded += 1;
      if (e.correct) t.correct += 1;
    }
    if (e.matched_rule) t.matched += 1;
    if (ruleOverrode(e)) t.overrides += 1;
    if (e.stakes >= 0.66) {
      t.highStakes += 1;
      if (e.correct) t.highStakesCorrect += 1;
    }
  }
  return t;
}

export type SpendPoint = {
  step: number;
  id: string;
  ponder: number;
  alwaysDeep: number;
  gpu: number;
};

/** Running token total as the queue drains, against the always-deep twin run. */
export function cumulativeSpend(
  events: TaskEvent[],
  twins: Map<string, TaskEvent>
): SpendPoint[] {
  let ponder = 0;
  let alwaysDeep = 0;
  let gpu = 0;
  return events.map((e, i) => {
    const twin = twins.get(bareId(e));
    ponder += e.total_tokens;
    alwaysDeep += twin?.total_tokens ?? e.total_tokens;
    gpu += e.total_gpu_seconds;
    return { step: i + 1, id: bareId(e), ponder, alwaysDeep, gpu };
  });
}

export type BudgetSlice = { budget: "cheap" | "deep"; tasks: number; tokens: number; gpu: number };

export function budgetMix(events: TaskEvent[]): BudgetSlice[] {
  const rows: Record<string, BudgetSlice> = {
    cheap: { budget: "cheap", tasks: 0, tokens: 0, gpu: 0 },
    deep: { budget: "deep", tasks: 0, tokens: 0, gpu: 0 },
  };
  for (const e of events) {
    const row = rows[e.budget];
    row.tasks += 1;
    row.tokens += e.total_tokens;
    row.gpu += e.total_gpu_seconds;
  }
  return [rows.cheap, rows.deep];
}

export type RuleRow = {
  rule: string;
  matches: number;
  deep: number;
  sandbox: number;
  tokens: number;
  gpu: number;
  graded: number;
  correct: number;
  overrides: number;
};

/** Per named rule: how often it fired, what it forced, and what that cost. */
export function ruleLedger(events: TaskEvent[]): RuleRow[] {
  const rows = new Map<string, RuleRow>();
  for (const e of events) {
    const key = e.matched_rule ?? "— no rule (score decided)";
    const row = rows.get(key) ?? {
      rule: key,
      matches: 0,
      deep: 0,
      sandbox: 0,
      tokens: 0,
      gpu: 0,
      graded: 0,
      correct: 0,
      overrides: 0,
    };
    row.matches += 1;
    if (e.budget === "deep") row.deep += 1;
    if (e.sandbox_ran) row.sandbox += 1;
    row.tokens += e.total_tokens;
    row.gpu += e.total_gpu_seconds;
    if (e.correct !== null) {
      row.graded += 1;
      if (e.correct) row.correct += 1;
    }
    if (ruleOverrode(e)) row.overrides += 1;
    rows.set(key, row);
  }
  return [...rows.values()].sort((a, b) => b.tokens - a.tokens);
}

export type DecisionPoint = {
  id: string;
  difficulty: number;
  stakes: number;
  tokens: number;
  budget: "cheap" | "deep";
  correct: boolean | null;
  rule: string | null;
  prompt: string;
};

/** The thesis, as one picture: what got spent, plotted against what it looked like. */
export function decisionMap(events: TaskEvent[]): DecisionPoint[] {
  return events.map((e) => ({
    id: bareId(e),
    difficulty: e.difficulty,
    stakes: e.stakes,
    tokens: e.total_tokens,
    budget: e.budget,
    correct: e.correct,
    rule: e.matched_rule,
    prompt: e.prompt_preview,
  }));
}

export type StakesBand = { band: string; n: number; correct: number; accuracy: number };

/** Where the remaining errors sit. The claim is that they cluster in low stakes. */
export function accuracyByStakes(events: TaskEvent[]): StakesBand[] {
  const defs: { band: string; test: (s: number) => boolean }[] = [
    { band: "low", test: (s) => s < 0.34 },
    { band: "medium", test: (s) => s >= 0.34 && s < 0.66 },
    { band: "high", test: (s) => s >= 0.66 },
  ];
  return defs.map(({ band, test }) => {
    const graded = events.filter((e) => test(e.stakes) && e.correct !== null);
    const correct = graded.filter((e) => e.correct).length;
    return {
      band,
      n: graded.length,
      correct,
      accuracy: graded.length ? correct / graded.length : 0,
    };
  });
}
