"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Frontier, RuleProof, TaskEvent } from "./types";

export type Stage = "thinking" | "verifying" | "done";

export type RunState = {
  loading: boolean;
  error?: string;
  /** ponder events that have finished, in order */
  completed: TaskEvent[];
  /** the one currently on screen, mid-flight */
  current?: TaskEvent;
  stage: Stage;
  samplesLit: number;
  /** what always-deep would have spent on the same tasks so far */
  counterfactual: { tokens: number; gpuSeconds: number };
  /** false when the recording holds no `deep` events -- then the counterfactual is
   *  just the ponder spend echoed back, and the panels must say so rather than
   *  claim a 0% saving. */
  hasCounterfactual: boolean;
  spend: { tokens: number; gpuSeconds: number };
  finished: boolean;
  total: number;
};

const TICK_MS = 55;
const VERIFY_TICKS = 5;

/**
 * Replay driver. events.jsonl holds one final TaskEvent per task; the timeline
 * (samples lighting up, the sandbox tick) is rendered from the fields that event
 * already carries. The dashboard stays a renderer -- it invents no data.
 */
export function useRun(speed: number, playing: boolean, strategy = "ponder") {
  const [all, setAll] = useState<TaskEvent[]>([]);
  /** Events produced live by the input box, kept apart so the replay fetch cannot clobber them. */
  const [injected, setInjected] = useState<TaskEvent[]>([]);
  const [frontier, setFrontier] = useState<Frontier | null>(null);
  const [ruleProof, setRuleProof] = useState<RuleProof | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  const [index, setIndex] = useState(0);
  const [stage, setStage] = useState<Stage>("thinking");
  const [samplesLit, setSamplesLit] = useState(0);
  const verifyTicks = useRef(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [r1, r2] = await Promise.all([fetch("/api/replay"), fetch("/api/frontier")]);
        const replay = await r1.json();
        const extras = await r2.json();
        if (cancelled) return;
        if (replay.error) setError(replay.error);
        setAll(replay.events ?? []);
        setFrontier(extras.frontier ?? null);
        setRuleProof(extras.ruleProof ?? null);
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const queue = useMemo(() => {
    const replayed = all.filter((e) => e.strategy === strategy);
    const seen = new Set(replayed.map((e) => e.id));
    return [...replayed, ...injected.filter((e) => !seen.has(e.id))];
  }, [all, injected, strategy]);
  const deepByTask = useMemo(() => {
    const map = new Map<string, TaskEvent>();
    for (const e of all) if (e.strategy === "deep") map.set(e.id.split(":").pop()!, e);
    return map;
  }, [all]);

  const reset = useCallback(() => {
    setIndex(0);
    setStage("thinking");
    setSamplesLit(0);
    verifyTicks.current = 0;
  }, []);

  // An injected event is appended, never replaces one, so its position is exactly
  // the queue length at the moment it arrives. The ref keeps that out of the tick.
  const queueLen = useRef(0);
  useEffect(() => {
    queueLen.current = queue.length;
  }, [queue]);

  /**
   * Take a TaskEvent the agent just produced for a typed-in task and play it.
   * It joins the same queue and runs through the same stages as a replayed one --
   * the only difference is that it was emitted a second ago rather than last night.
   */
  const inject = useCallback((event: TaskEvent) => {
    setInjected((prev) => (prev.some((e) => e.id === event.id) ? prev : [...prev, event]));
    setIndex(queueLen.current);
    setStage("thinking");
    setSamplesLit(0);
    verifyTicks.current = 0;
  }, []);

  useEffect(() => {
    if (!playing || queue.length === 0 || index >= queue.length) return;
    const id = setInterval(() => {
      const event = queue[index];
      if (!event) return;
      setStage((currentStage) => {
        if (currentStage === "thinking") {
          setSamplesLit((lit) => {
            if (lit + 1 >= event.samples.length) {
              setStage(event.sandbox_ran ? "verifying" : "done");
            }
            return Math.min(lit + 1, event.samples.length);
          });
          return currentStage;
        }
        if (currentStage === "verifying") {
          verifyTicks.current += 1;
          if (verifyTicks.current >= VERIFY_TICKS) {
            verifyTicks.current = 0;
            return "done";
          }
          return currentStage;
        }
        // done -> advance
        setIndex((i) => i + 1);
        setSamplesLit(0);
        return "thinking";
      });
    }, Math.max(12, TICK_MS / speed));
    return () => clearInterval(id);
  }, [playing, queue, index, speed]);

  const completed = queue.slice(0, index);
  const current = queue[index];

  const spend = completed.reduce(
    (acc, e) => ({
      tokens: acc.tokens + e.total_tokens,
      gpuSeconds: acc.gpuSeconds + e.total_gpu_seconds,
    }),
    { tokens: 0, gpuSeconds: 0 }
  );

  const counterfactual = completed.reduce(
    (acc, e) => {
      const twin = deepByTask.get(e.id.split(":").pop()!);
      return {
        tokens: acc.tokens + (twin?.total_tokens ?? e.total_tokens),
        gpuSeconds: acc.gpuSeconds + (twin?.total_gpu_seconds ?? e.total_gpu_seconds),
      };
    },
    { tokens: 0, gpuSeconds: 0 }
  );

  const state: RunState = {
    loading,
    error,
    completed,
    current,
    stage,
    samplesLit,
    spend,
    counterfactual,
    hasCounterfactual: deepByTask.size > 0,
    finished: queue.length > 0 && index >= queue.length,
    total: queue.length,
  };

  return { state, frontier, ruleProof, reset, inject, queue, deepTwins: deepByTask };
}
