"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { Coins, Cpu, FlaskConical, Layers, Scale, TriangleAlert } from "lucide-react";
import { Bench } from "@/components/bench";
import { BudgetChart } from "@/components/charts/budget-chart";
import { ConvexLive } from "@/components/convex-live";
import { DecisionMap } from "@/components/charts/decision-map";
import { FrontierChart } from "@/components/charts/frontier-chart";
import { SpendChart } from "@/components/charts/spend-chart";
import { StakesAccuracyChart } from "@/components/charts/stakes-accuracy-chart";
import { EvidenceBar } from "@/components/evidence-bar";
import { Panel, SectionHeading, Stat } from "@/components/primitives";
import { QueueList } from "@/components/queue-list";
import { RuleEditor } from "@/components/rule-editor";
import { RuleLedger } from "@/components/rule-ledger";
import { SiteHeader } from "@/components/site-header";
import { TaskDetail } from "@/components/task-detail";
import { TaskTable } from "@/components/task-table";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import {
  accuracyByStakes,
  budgetMix,
  cumulativeSpend,
  decisionMap,
  fmtGpu,
  fmtTokens,
  pct,
  ruleLedger,
  totals,
} from "@/lib/derive";
import { bareId, type TaskEvent } from "@/lib/types";
import { useRun } from "@/lib/useRun";

export default function MissionControl() {
  const [speed, setSpeed] = useState(2);
  const [playing, setPlaying] = useState(true);
  const { state, frontier, ruleProof, reset, inject, queue, deepTwins } = useRun(speed, playing);

  /** null = follow the live task; otherwise the id of the task the user clicked into. */
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [ruleFilter, setRuleFilter] = useState<string | null>(null);
  const consoleRef = useRef<HTMLDivElement>(null);

  const landed = state.completed;

  const byBareId = useMemo(() => {
    const map = new Map<string, TaskEvent>();
    for (const e of queue) map.set(bareId(e), e);
    return map;
  }, [queue]);

  const selectById = useCallback(
    (id: string) => {
      setSelectedId((prev) => (prev === id ? prev : id));
      consoleRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    },
    []
  );

  /** Charts key on the short id, so translate before selecting. */
  const selectByBareId = useCallback(
    (short: string) => {
      const found = byBareId.get(short);
      if (found) selectById(found.id);
    },
    [byBareId, selectById]
  );

  const selected = selectedId ? queue.find((e) => e.id === selectedId) : undefined;
  const detail = selected ?? state.current ?? landed[landed.length - 1];
  const following = !selected;

  const t = useMemo(() => totals(landed, deepTwins), [landed, deepTwins]);
  const spendSeries = useMemo(() => cumulativeSpend(landed, deepTwins), [landed, deepTwins]);
  const mix = useMemo(() => budgetMix(landed), [landed]);
  const rules = useMemo(() => ruleLedger(landed), [landed]);
  const map = useMemo(() => decisionMap(landed), [landed]);
  const bands = useMemo(() => accuracyByStakes(landed), [landed]);

  const saved = state.hasCounterfactual && t.counterTokens > 0 ? 1 - t.tokens / t.counterTokens : 0;
  const ponderReport = frontier?.reports.find((r) => r.strategy === "ponder");
  const deepReport = frontier?.reports.find((r) => r.strategy === "deep");

  return (
    <div className="min-h-screen">
      <SiteHeader
        playing={playing}
        onToggle={() => setPlaying((p) => !p)}
        onRestart={() => {
          setSelectedId(null);
          reset();
        }}
        speed={speed}
        onSpeed={setSpeed}
        done={landed.length}
        total={state.total}
      />

      <div className="mx-auto flex max-w-[1900px] flex-col gap-5 px-5 py-6 xl:flex-row xl:items-start">
        <main className="min-w-0 flex-1 space-y-8">
        {state.error && (
          <Alert className="border-deep/40 bg-deep/8">
            <TriangleAlert className="text-deep" />
            <AlertDescription className="text-deep">{state.error}</AlertDescription>
          </Alert>
        )}

        {/* ── This run ─────────────────────────────────────────────────── */}
        <section className="space-y-3">
          <SectionHeading
            title="This run"
            description="An agent that decides how hard to think — and whether to verify before you trust it."
          />
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Stat
              icon={Layers}
              label="Tasks landed"
              value={`${t.n}`}
              unit={`of ${state.total}`}
              hint={`${t.deep} deep · ${t.cheap} cheap`}
            />
            <Stat
              icon={Coins}
              label="Compute saved"
              value={saved > 0 ? pct(saved) : "—"}
              tone="ok"
              hint={
                state.hasCounterfactual
                  ? `${fmtTokens(t.tokens)} vs ${fmtTokens(t.counterTokens)} always-deep`
                  : `${fmtTokens(t.tokens)} spent · no always-deep run recorded`
              }
            />
            <Stat
              icon={Cpu}
              label="GPU burned"
              value={fmtGpu(t.gpu)}
              hint={`${fmtTokens(t.tokens)} tokens across ${t.n} tasks`}
            />
            <Stat
              icon={Scale}
              label="Rule decisions"
              value={`${t.matched}`}
              unit={t.n ? `of ${t.n}` : undefined}
              tone="rule"
              hint={
                t.matched
                  ? `${t.overrides} overrode the score · ${t.matched - t.overrides} confirmed it`
                  : "no named rule has fired yet"
              }
            />
            <Stat
              icon={FlaskConical}
              label="Sandbox verified"
              value={`${t.sandboxRuns}`}
              tone="deep"
              hint={`${t.sandboxPassed} executed and agreed`}
            />
          </div>
        </section>

        {/* Live tasks from any agent run, via Convex. No-ops when unconfigured. */}

        <ConvexLive onEvent={inject} />

        {/* ── Console ──────────────────────────────────────────────────── */}
        <section ref={consoleRef} className="scroll-mt-20 space-y-3">
          <SectionHeading
            title="Console"
            description="Click any task — in the queue, the map or the log — to inspect its decision."
          />
          {state.loading ? (
            <Skeleton className="h-[620px] w-full rounded-xl" />
          ) : (
            <div className="grid gap-3 lg:h-[620px] lg:grid-cols-12">
              <div className="h-[420px] lg:col-span-4 lg:h-auto lg:min-h-0">
                <QueueList
                  completed={landed}
                  current={state.current}
                  total={state.total}
                  selectedId={selectedId}
                  onSelect={selectById}
                  following={following}
                  onFollow={() => setSelectedId(null)}
                />
              </div>
              <div className="h-[620px] lg:col-span-8 lg:h-auto lg:min-h-0">
                <TaskDetail
                  event={detail}
                  stage={state.stage}
                  samplesLit={state.samplesLit}
                  live={following && Boolean(state.current)}
                />
              </div>
            </div>
          )}
        </section>

        {/* ── Spend ────────────────────────────────────────────────────── */}
        <section className="space-y-3">
          <SectionHeading
            title="Spend"
            description="What the run cost, against what always-deep would have cost for the same queue."
          />
          <div className="grid gap-3 lg:grid-cols-5">
            <div className="h-[300px] lg:col-span-3">
              <SpendChart points={spendSeries} hasCounterfactual={state.hasCounterfactual} />
            </div>
            <div className="h-[300px] lg:col-span-2">
              <BudgetChart slices={mix} />
            </div>
          </div>
        </section>

        {/* ── Decisions ────────────────────────────────────────────────── */}
        <section className="space-y-3">
          <SectionHeading
            title="Decisions"
            description="Where the compute went, and which named rule put it there."
          />
          <div className="grid gap-3 lg:grid-cols-5">
            <div className="h-[380px] lg:col-span-3">
              <DecisionMap
                points={map}
                focusId={detail ? bareId(detail) : null}
                dimOthers={Boolean(selected)}
                onSelect={selectByBareId}
              />
            </div>
            <div className="h-[380px] lg:col-span-2">
              <RuleLedger rows={rules} activeRule={ruleFilter} onPick={setRuleFilter} />
            </div>
          </div>
        </section>

        {/* ── Policy ───────────────────────────────────────────────────── */}
        <section className="space-y-3">
          <SectionHeading
            title="Policy"
            description="The named rules themselves — authored here, not in the code. Each one sets how hard to think, whether the answer is executed to verify it, and which guardrails it must clear."
          />
          <RuleEditor />
        </section>

        {/* ── Baselines ────────────────────────────────────────────────── */}
        <section className="space-y-3">
          <SectionHeading
            title="Baselines"
            description="Ponder against always-cheap and always-deep on the same queue."
          />
          <div className="grid gap-3 lg:grid-cols-5">
            <div className="h-[340px] lg:col-span-3">
              <FrontierChart frontier={frontier} />
            </div>
            <div className="h-[340px] lg:col-span-2">
              <StakesAccuracyChart bands={bands} />
            </div>
          </div>
          {ponderReport && deepReport && (
            <Panel className="px-4 py-3">
              <p className="text-sm text-muted-foreground">
                Ponder holds{" "}
                <span className="font-medium text-foreground">
                  {pct(ponderReport.high_stakes_accuracy)}
                </span>{" "}
                high-stakes accuracy against always-deep&rsquo;s{" "}
                <span className="font-medium text-foreground">
                  {pct(deepReport.high_stakes_accuracy)}
                </span>
                , on{" "}
                <span className="font-medium text-foreground">
                  {fmtGpu(ponderReport.total_gpu_seconds)}
                </span>{" "}
                of GPU instead of {fmtGpu(deepReport.total_gpu_seconds)}.
              </p>
            </Panel>
          )}
          <EvidenceBar ruleProof={ruleProof} frontier={frontier} />
        </section>

        {/* ── Task log ─────────────────────────────────────────────────── */}
        <section className="space-y-3 pb-10">
          <SectionHeading title="Task log" description="Every task in the recording." />
          <TaskTable
            events={landed}
            selectedId={selectedId}
            onSelect={selectById}
            ruleFilter={ruleFilter}
            onClearRuleFilter={() => setRuleFilter(null)}
          />
        </section>
        </main>

        {/*
          The bench is docked, not stacked: a live answer used to be dropped into a
          replay that was still animating, so it was one frame in a scrolling
          recording. Here it holds still next to the dashboard it feeds.
          `order-first` keeps it on top on narrow screens, where there is no rail.
        */}
        <aside className="order-first xl:order-none xl:w-[380px] xl:shrink-0 2xl:w-[420px]">
          {/* Needs an explicit height at every width: the panel is a flex column whose
              scroll area fills the remainder, and `flex-1` has nothing to claim against
              an auto-height parent. Below xl it is a capped block, above it a full rail. */}
          <div className="h-[min(72vh,620px)] xl:sticky xl:top-[72px] xl:h-[calc(100vh-88px)]">
            <Bench
              onEvent={(event) => {
                setPlaying(true);
                setSelectedId(null);
                inject(event);
              }}
            />
          </div>
        </aside>
      </div>
    </div>
  );
}
