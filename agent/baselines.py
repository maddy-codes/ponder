"""always-cheap vs always-deep vs ponder, over the same queue.

The claim being tested is not "ponder is more accurate". It is:
  ponder matches always-deep where being wrong is expensive, at a fraction of the
  compute, and the errors it does make land on tasks nobody is harmed by.

`stakes_tag` from tasks.jsonl is held-out ground truth. Triage never sees it; it is
used only here, to say where the errors landed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass

from agent.events import TaskEvent, get_emitter
from agent.loop import run_queue
from agent.settings import ARTIFACTS, EVENTS_PATH, settings
from agent.tasks import Task, load_tasks


@dataclass
class StrategyReport:
    strategy: str
    n: int
    correct: int
    accuracy: float
    high_stakes_n: int
    high_stakes_correct: int
    high_stakes_accuracy: float
    total_tokens: int
    total_gpu_seconds: float
    deep_tasks: int
    sandbox_runs: int
    misses: list[str]
    low_stakes_share_of_misses: float


def summarise(strategy: str, tasks: list[Task], events: list[TaskEvent]) -> StrategyReport:
    by_id = {t.id: t for t in tasks}
    paired = [(by_id[e.id.split(":", 1)[1]], e) for e in events]

    correct = sum(1 for _, e in paired if e.correct)
    high = [(t, e) for t, e in paired if t.stakes_tag == "high"]
    high_correct = sum(1 for _, e in high if e.correct)
    misses = [t.id for t, e in paired if not e.correct]
    low_misses = sum(1 for t, e in paired if not e.correct and t.stakes_tag != "high")

    return StrategyReport(
        strategy=strategy,
        n=len(paired),
        correct=correct,
        accuracy=round(correct / len(paired), 4),
        high_stakes_n=len(high),
        high_stakes_correct=high_correct,
        high_stakes_accuracy=round(high_correct / len(high), 4) if high else 0.0,
        total_tokens=sum(e.total_tokens for e in events),
        total_gpu_seconds=round(sum(e.total_gpu_seconds for e in events), 2),
        deep_tasks=sum(1 for e in events if e.budget == "deep"),
        sandbox_runs=sum(1 for e in events if e.sandbox_ran),
        misses=sorted(misses),
        low_stakes_share_of_misses=round(low_misses / len(misses), 4) if misses else 1.0,
    )


def render(reports: list[StrategyReport]) -> str:
    head = (
        f"{'strategy':9} {'acc':>6} {'high-stakes acc':>16} {'tokens':>9} {'gpu s':>8} "
        f"{'deep':>5} {'sbx':>4} {'misses that were low-stakes':>28}"
    )
    lines = [head, "-" * len(head)]
    for r in reports:
        lines.append(
            f"{r.strategy:9} {r.accuracy:6.0%} "
            f"{r.high_stakes_correct:>7}/{r.high_stakes_n:<3} {r.high_stakes_accuracy:>4.0%} "
            f"{r.total_tokens:>9,} {r.total_gpu_seconds:>8.1f} {r.deep_tasks:>5} {r.sandbox_runs:>4} "
            f"{r.low_stakes_share_of_misses:>27.0%}"
        )
    return "\n".join(lines)


def verdict(reports: list[StrategyReport]) -> list[str]:
    by = {r.strategy: r for r in reports}
    cheap, deep, ponder = by["cheap"], by["deep"], by["ponder"]
    out = []

    token_saving = 1 - (ponder.total_tokens / deep.total_tokens) if deep.total_tokens else 0
    gpu_saving = 1 - (ponder.total_gpu_seconds / deep.total_gpu_seconds) if deep.total_gpu_seconds else 0
    out.append(
        f"compute: ponder uses {token_saving:.0%} fewer tokens and {gpu_saving:.0%} less GPU "
        f"time than always-deep."
    )
    out.append(
        f"high-stakes accuracy: ponder {ponder.high_stakes_accuracy:.0%} vs always-deep "
        f"{deep.high_stakes_accuracy:.0%} vs always-cheap {cheap.high_stakes_accuracy:.0%}."
    )
    out.append(
        f"error placement: {ponder.low_stakes_share_of_misses:.0%} of ponder's misses are "
        f"low-stakes (always-cheap: {cheap.low_stakes_share_of_misses:.0%})."
    )

    ok = (
        ponder.high_stakes_accuracy >= deep.high_stakes_accuracy - 0.06
        and token_saving > 0.25
        and ponder.low_stakes_share_of_misses >= 0.75
    )
    out.append("VERDICT: " + ("frontier holds." if ok else
                              "frontier does NOT hold -- widen the difficulty/stakes spread "
                              "in tasks.jsonl or retune the thresholds in settings.py."))
    return out


async def run_all(tasks: list[Task], strategies: list[str]) -> list[StrategyReport]:
    emitter = get_emitter()
    reports = []
    for strategy in strategies:
        print(f"\n=== {strategy} ===")
        events = await run_queue(tasks, strategy, emitter, quiet=True)
        report = summarise(strategy, tasks, events)
        print(render([report]))
        reports.append(report)
    return reports


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the cost-vs-accuracy frontier.")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--fresh", action="store_true", help="truncate events.jsonl first")
    ap.add_argument("--strategies", default="cheap,deep,ponder")
    args = ap.parse_args()

    if args.fresh and EVENTS_PATH.exists():
        EVENTS_PATH.unlink()

    tasks = load_tasks()[: args.limit] if args.limit else load_tasks()
    strategies = args.strategies.split(",")
    print(f"ponder frontier :: {settings.describe()} :: {len(tasks)} tasks")

    reports = asyncio.run(run_all(tasks, strategies))

    print("\n" + render(reports))
    print()
    lines = verdict(reports)
    for line in lines:
        print("  " + line)

    ARTIFACTS.mkdir(exist_ok=True)
    out = ARTIFACTS / "frontier.json"
    out.write_text(json.dumps({"reports": [asdict(r) for r in reports], "verdict": lines}, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
