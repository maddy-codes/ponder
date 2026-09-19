"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  ChevronRight,
  CircleDashed,
  CornerDownLeft,
  Cpu,
  FlaskConical,
  Gauge as GaugeIcon,
  Loader2,
  Scale,
  Square,
  TriangleAlert,
  X,
} from "lucide-react";
import { Panel, BudgetTag, RuleTag } from "@/components/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { TaskEvent } from "@/lib/types";

/** A streamed snapshot: a TaskEvent plus the flag marking the durable one. */
type Snapshot = TaskEvent & { final?: boolean };

const EXAMPLES = [
  "What is the total cost of 3 items at 4.50 each?",
  "What is the capital of Peru?",
  "A patient weighs 24 kg and the dose is 12 mg/kg. What is the dose in mg?",
];

type StageState = "pending" | "active" | "done";

type Stage = {
  key: string;
  label: string;
  state: StageState;
  detail: string;
  tone?: string;
};

/**
 * Derive the stage rail from the snapshots the agent actually sent.
 *
 * Every line here reads a field the TaskEvent already carries — the panel stays a
 * renderer. A stage is `active` when the agent has reached it and `done` when a later
 * snapshot proves it finished; nothing is timed out or guessed on the client.
 */
function stagesOf(snap: Snapshot | undefined, running: boolean): Stage[] {
  const has = Boolean(snap);
  const done = snap ? snap.samples.filter((s) => s.status === "done").length : 0;
  const failed = snap ? snap.samples.filter((s) => s.status === "failed").length : 0;
  const total = snap ? snap.samples.length : 0;
  const fanDone = has && done + failed >= total && total > 0;
  const verifying = snap?.status === "verifying";
  const finished = snap?.status === "done";

  return [
    {
      key: "triage",
      label: "Triage",
      state: has ? "done" : running ? "active" : "pending",
      detail: has
        ? `difficulty ${snap!.difficulty.toFixed(2)} · stakes ${snap!.stakes.toFixed(2)}`
        : "scoring difficulty × stakes from the prompt",
      tone: "text-difficulty",
    },
    {
      key: "rule",
      label: "Rule",
      state: has ? "done" : "pending",
      detail: !has
        ? "matching named domain rules"
        : snap!.matched_rule
          ? (snap!.rule_reason ?? snap!.matched_rule)
          : "no named rule matched — the score decides",
      tone: "text-rule",
    },
    {
      key: "budget",
      label: "Budget",
      state: has ? "done" : "pending",
      detail: has
        ? `${snap!.budget} · ${total} sample${total === 1 ? "" : "s"} · Gateway rule ${snap!.rule_id}`
        : "choosing how hard to think",
      tone: snap?.budget === "deep" ? "text-deep" : "text-cheap",
    },
    {
      key: "samples",
      label: "Model",
      state: fanDone ? "done" : has ? "active" : "pending",
      detail: has
        ? `${done}/${total} returned${failed ? ` · ${failed} failed` : ""}${
            snap!.total_tokens ? ` · ${snap!.total_tokens.toLocaleString()} tokens` : ""
          }`
        : "fanning out across Modal containers",
      tone: "text-live",
    },
    {
      key: "sandbox",
      label: "Sandbox",
      state: snap?.sandbox_ran ? "done" : verifying ? "active" : "pending",
      detail: snap?.sandbox_ran
        ? snap.sandbox_passed
          ? "executed and agreed with the answer"
          : "executed and disagreed — the executed value won"
        : verifying
          ? "executing the answer to check it"
          : finished
            ? "not required at this stake level"
            : "runs only when being wrong is expensive",
      tone: "text-deep",
    },
    {
      key: "answer",
      label: "Answer",
      state: finished ? "done" : "pending",
      detail: finished
        ? `${snap!.latency_ms.toLocaleString()} ms · ${snap!.total_gpu_seconds.toFixed(2)} GPU-s`
        : "waiting on the aggregate",
      tone: "text-ok",
    },
  ];
}

function StageRow({ stage }: { stage: Stage }) {
  return (
    <li className="flex items-start gap-2.5">
      <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center">
        {stage.state === "done" ? (
          <Check className={cn("size-3.5", stage.tone ?? "text-ok")} aria-hidden />
        ) : stage.state === "active" ? (
          <Loader2 className="size-3.5 animate-spin text-live" aria-hidden />
        ) : (
          <CircleDashed className="size-3.5 text-muted-foreground/40" aria-hidden />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span
          className={cn(
            "text-xs font-medium",
            stage.state === "pending" ? "text-muted-foreground/60" : "text-foreground"
          )}
        >
          {stage.label}
        </span>
        <span
          className={cn(
            "mt-0.5 block text-[11px] leading-snug",
            stage.state === "pending" ? "text-muted-foreground/50" : "text-muted-foreground"
          )}
        >
          {stage.detail}
        </span>
      </span>
    </li>
  );
}

/** The fan-out, one cell per Modal container, filling in as each one returns. */
function SampleGrid({ snap }: { snap: Snapshot }) {
  if (snap.samples.length <= 1) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {snap.samples.map((s, i) => (
        <span
          key={i}
          title={
            s.status === "done"
              ? `${s.tokens} tokens · ${s.gpu_seconds.toFixed(2)} GPU-s`
              : s.status
          }
          className={cn(
            "h-1.5 flex-1 rounded-full transition-colors",
            s.status === "done"
              ? "bg-live"
              : s.status === "failed"
                ? "bg-miss"
                : "animate-pulse bg-muted-foreground/25"
          )}
        />
      ))}
    </div>
  );
}

type Run = {
  key: string;
  prompt: string;
  snap?: Snapshot;
  error?: string;
  running: boolean;
  elapsedMs: number;
};

/**
 * The bench: type a task, watch the agent decide, read the answer in place.
 *
 * The result stays on screen until the next run replaces it, which the old top-of-page
 * box could not do — it dropped its event into a replay that was still animating, so a
 * live answer was one frame in a scrolling recording. Everything rendered here comes
 * off the streamed TaskEvent, and the final one is still injected into the dashboard
 * so the queue, the map and the log all see it exactly as before.
 */
export function Bench({ onEvent }: { onEvent: (event: TaskEvent) => void }) {
  const [prompt, setPrompt] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [history, setHistory] = useState<Run[]>([]);
  const abort = useRef<AbortController | null>(null);

  const running = run?.running ?? false;

  // A live elapsed count is the honest answer to "has it hung?" — a deep task fans out
  // real containers and can legitimately take the better part of a minute.
  useEffect(() => {
    if (!running) return;
    const started = Date.now() - (run?.elapsedMs ?? 0);
    const id = setInterval(() => {
      setRun((r) => (r && r.running ? { ...r, elapsedMs: Date.now() - started } : r));
    }, 100);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, run?.key]);

  const stop = useCallback(() => {
    abort.current?.abort();
    abort.current = null;
    setRun((r) => (r ? { ...r, running: false, error: r.error ?? "stopped" } : r));
  }, []);

  const submit = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || running) return;

      const controller = new AbortController();
      abort.current = controller;
      const key = `${Date.now()}`;
      setRun((prev) => {
        if (prev && !prev.running && (prev.snap || prev.error)) {
          setHistory((h) => [prev, ...h].slice(0, 12));
        }
        return { key, prompt: trimmed, running: true, elapsedMs: 0 };
      });
      setPrompt("");

      try {
        const res = await fetch("/api/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: trimmed }),
          signal: controller.signal,
        });
        if (!res.ok || !res.body) {
          const fallback = await res.json().catch(() => ({}));
          throw new Error(fallback.error ?? `request failed (${res.status})`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        // NDJSON: one snapshot per line, and a chunk can split a line in half.
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";
          for (const line of lines) {
            if (!line.trim()) continue;
            const payload = JSON.parse(line);
            if (payload.error) throw new Error(payload.error);
            const snap = payload as Snapshot;
            setRun((r) => (r && r.key === key ? { ...r, snap } : r));
            if (snap.final) onEvent(snap as TaskEvent);
          }
        }
        setRun((r) => (r && r.key === key ? { ...r, running: false } : r));
      } catch (e) {
        if (controller.signal.aborted) return;
        const message = e instanceof Error ? e.message : String(e);
        setRun((r) => (r && r.key === key ? { ...r, running: false, error: message } : r));
      } finally {
        if (abort.current === controller) abort.current = null;
      }
    },
    [running, onEvent]
  );

  const snap = run?.snap;
  const stages = stagesOf(snap, running);

  return (
    <Panel className="flex h-full min-h-0 flex-col overflow-hidden p-0">
      {/* ── prompt ─────────────────────────────────────────────── */}
      <div className="shrink-0 border-b border-border px-4 py-3.5">
        <div className="mb-2.5 flex items-center gap-2">
          <FlaskConical className="size-3.5 text-rule" aria-hidden />
          <h2 className="text-xs font-semibold tracking-wide text-foreground uppercase">Bench</h2>
          <span className="ml-auto text-[11px] text-muted-foreground">
            {running ? (
              <span className="flex items-center gap-1.5 text-live">
                <span className="size-1.5 animate-pulse rounded-full bg-live" />
                {(run!.elapsedMs / 1000).toFixed(1)}s
              </span>
            ) : (
              "live agent · same pipeline as the queue"
            )}
          </span>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit(prompt);
          }}
          className="flex items-center gap-2"
        >
          <label htmlFor="bench" className="sr-only">
            Ask Ponder a task
          </label>
          <Input
            id="bench"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={running}
            autoComplete="off"
            placeholder="Ask Ponder a task…"
            className="h-9 flex-1 text-sm"
          />
          {running ? (
            <Button type="button" variant="outline" className="h-9 px-3" onClick={stop}>
              <Square className="size-3.5" />
              Stop
            </Button>
          ) : (
            <Button type="submit" disabled={!prompt.trim()} className="h-9 px-3">
              Run
              <CornerDownLeft data-icon="inline-end" />
            </Button>
          )}
        </form>

        <div className="mt-2 flex flex-wrap gap-1">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              disabled={running}
              onClick={() => void submit(example)}
              className="rounded-md border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
            >
              {example.length > 34 ? `${example.slice(0, 32)}…` : example}
            </button>
          ))}
        </div>
      </div>

      {/* ── live decision + result ─────────────────────────────── */}
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-4 px-4 py-3.5">
          {!run ? (
            <p className="py-8 text-center text-xs text-muted-foreground">
              Type a task above. You&rsquo;ll see it triaged, matched against the domain rules,
              fanned out to the model and — when the stakes justify it — executed in a sandbox
              before the answer is trusted.
            </p>
          ) : (
            <>
              <p className="text-sm leading-snug text-foreground">{run.prompt}</p>

              {snap && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <BudgetTag budget={snap.budget} />
                  {snap.matched_rule && <RuleTag rule={snap.matched_rule} />}
                  {snap.sandbox_ran && (
                    <span className="inline-flex items-center gap-1 rounded-md border border-deep/30 bg-deep/10 px-1.5 py-0.5 text-[11px] font-medium text-deep">
                      <FlaskConical className="size-3" aria-hidden />
                      verified
                    </span>
                  )}
                </div>
              )}

              {snap && <SampleGrid snap={snap} />}

              <ul className="space-y-2">
                {stages.map((stage) => (
                  <StageRow key={stage.key} stage={stage} />
                ))}
              </ul>

              {run.error && (
                <p className="flex items-start gap-1.5 rounded-md border border-destructive/30 bg-destructive/8 px-2 py-1.5 text-[11px] text-destructive">
                  <TriangleAlert className="mt-px size-3.5 shrink-0" aria-hidden />
                  {run.error}
                </p>
              )}

              {snap?.answer && (
                <div className="rounded-md border border-border bg-muted/40 px-3 py-2.5">
                  <p className="mb-1 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                    Answer
                  </p>
                  <p className="text-sm leading-relaxed whitespace-pre-wrap text-foreground">
                    {snap.answer}
                  </p>
                </div>
              )}

              {snap?.status === "done" && (
                <dl className="grid grid-cols-3 gap-2 text-center">
                  {[
                    { icon: GaugeIcon, label: "tokens", value: snap.total_tokens.toLocaleString() },
                    { icon: Cpu, label: "GPU-s", value: snap.total_gpu_seconds.toFixed(2) },
                    { icon: Scale, label: "samples", value: `${snap.samples.length}` },
                  ].map(({ icon: Icon, label, value }) => (
                    <div key={label} className="rounded-md border border-border px-2 py-1.5">
                      <dt className="flex items-center justify-center gap-1 text-[10px] text-muted-foreground">
                        <Icon className="size-3" aria-hidden />
                        {label}
                      </dt>
                      <dd className="mt-0.5 font-mono text-sm text-foreground">{value}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </>
          )}

          {/* ── this session's earlier runs ───────────────────── */}
          {history.length > 0 && (
            <div className="border-t border-border pt-3">
              <p className="mb-1.5 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                Earlier this session
              </p>
              <ul className="space-y-0.5">
                {history.map((h) => (
                  <li key={h.key}>
                    <button
                      type="button"
                      onClick={() => {
                        setRun((cur) => {
                          if (cur && !cur.running && (cur.snap || cur.error)) {
                            setHistory((list) => [cur, ...list.filter((x) => x.key !== h.key)].slice(0, 12));
                          } else {
                            setHistory((list) => list.filter((x) => x.key !== h.key));
                          }
                          return h;
                        });
                        if (h.snap) onEvent(h.snap as TaskEvent);
                      }}
                      className="flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-left text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    >
                      {h.error ? (
                        <X className="size-3 shrink-0 text-miss" aria-hidden />
                      ) : (
                        <ChevronRight className="size-3 shrink-0" aria-hidden />
                      )}
                      <span className="truncate">{h.prompt}</span>
                      {h.snap && (
                        <span
                          className={cn(
                            "ml-auto shrink-0 font-mono text-[10px]",
                            h.snap.budget === "deep" ? "text-deep" : "text-cheap"
                          )}
                        >
                          {h.snap.budget}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </ScrollArea>
    </Panel>
  );
}
