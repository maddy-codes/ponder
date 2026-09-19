"use client";

import { useState } from "react";
import { EffortView } from "@/components/EffortView";
import { EvidenceStrip } from "@/components/EvidenceStrip";
import { FrontierMeter } from "@/components/FrontierMeter";
import { Queue } from "@/components/Queue";
import { SpendCounter } from "@/components/SpendCounter";
import { useRun } from "@/lib/useRun";

const SPEEDS = [1, 2, 4];

export default function MissionControl() {
  const [speed, setSpeed] = useState(2);
  const [playing, setPlaying] = useState(true);
  const { state, frontier, ruleProof, reset } = useRun(speed, playing);

  return (
    <main className="mx-auto flex h-screen max-w-[1500px] flex-col gap-3 p-4">
      <header className="flex items-center gap-4">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-zinc-100">
            Ponder <span className="text-zinc-600">·</span>{" "}
            <span className="text-zinc-400">Mission Control</span>
          </h1>
          <p className="text-xs text-zinc-500">
            An agent that decides how hard to think — difficulty × stakes → compute.
          </p>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <span className="rounded-full border border-zinc-700 px-2.5 py-1 text-[10px] uppercase tracking-widest text-zinc-400">
            replay
          </span>
          <button
            onClick={() => setPlaying((p) => !p)}
            className="rounded-md border border-zinc-700 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
          >
            {playing ? "pause" : "play"}
          </button>
          <button
            onClick={reset}
            className="rounded-md border border-zinc-700 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
          >
            restart
          </button>
          <div className="flex overflow-hidden rounded-md border border-zinc-700">
            {SPEEDS.map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                className={`px-2.5 py-1 text-xs ${
                  speed === s ? "bg-zinc-700 text-zinc-100" : "text-zinc-400 hover:bg-zinc-800"
                }`}
              >
                {s}×
              </button>
            ))}
          </div>
        </div>
      </header>

      {state.error && (
        <div className="rounded-lg border border-amber-600/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          {state.error}
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-12 gap-3">
        <div className="col-span-3 min-h-0">
          <Queue completed={state.completed} current={state.current} total={state.total} />
        </div>

        <div className="col-span-5 min-h-0">
          <EffortView event={state.current} stage={state.stage} samplesLit={state.samplesLit} />
        </div>

        <div className="col-span-4 flex min-h-0 flex-col gap-3">
          <SpendCounter spend={state.spend} counterfactual={state.counterfactual} />
          <FrontierMeter frontier={frontier} />
        </div>
      </div>

      <EvidenceStrip ruleProof={ruleProof} frontier={frontier} />
    </main>
  );
}
