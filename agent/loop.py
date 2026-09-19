"""Orchestration: triage -> budget -> spend -> aggregate -> grade -> emit.

One TaskEvent per task, fanned out to Logfire, Convex and events.jsonl by the
emitter. This module never talks to a sink directly.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from agent.aggregate import majority
from agent.budget import Decision, decide
from agent.events import Emitter, Sample, TaskEvent, get_emitter
from agent.grader import grade
from agent.rules import apply as apply_rules
from agent.settings import EVENTS_PATH, settings
from agent.tasks import Task, load_tasks
from agent.triage import Triage, triage
from agent.verify import verify
from agent.worker import fan_out


def plan(task: Task, strategy: str) -> tuple[Triage, Decision]:
    """Triage always runs -- the baselines need the same scores for reporting --
    but only the ponder strategy lets it decide anything.

    Two layers, in order: the numeric difficulty x stakes score, then any named
    domain rule that outranks it. The baselines deliberately see neither -- an
    always-deep baseline that consulted the rules would stop being a baseline.
    """
    scores = triage(task.prompt)
    executable = task.kind == "exec"
    if strategy == "ponder":
        scored = decide(scores.difficulty, scores.stakes, executable=executable)
        return scores, apply_rules(task.prompt, scored, executable=executable)
    if strategy == "cheap":
        return scores, Decision(budget="cheap", reason="trivial", sandbox=False, samples=1)
    return scores, Decision(              # always-deep: maximum effort on everything
        budget="deep", reason="both", sandbox=True, samples=settings.deep_samples + 2
    )


async def run_task(task: Task, strategy: str = "ponder", emitter: Emitter | None = None) -> TaskEvent:
    emitter = emitter or get_emitter()
    started = time.perf_counter()

    scores, decision = plan(task, strategy)
    rule_id = settings.rule_cheap if decision.budget == "cheap" else settings.rule_deep

    event = TaskEvent(
        id=f"{strategy}:{task.id}",
        prompt_preview=task.preview,
        difficulty=scores.difficulty,
        stakes=scores.stakes,
        budget=decision.budget,
        matched_rule=decision.matched_rule,
        rule_reason=decision.rule_reason,
        rule_id=rule_id,
        strategy=strategy,  # type: ignore[arg-type]
        status="thinking",
        samples=[Sample(status="running") for _ in range(decision.samples)],
    )
    emitter.progress(event)

    results = await fan_out(task, decision.budget, rule_id, decision.samples)
    event.samples = [
        Sample(status="done" if r.ok else "failed", tokens=r.tokens, gpu_seconds=r.gpu_seconds)
        for r in results
    ]
    answer, agreement = majority(task, [r.text for r in results])
    emitter.progress(event)

    if decision.sandbox and answer:
        event.status = "verifying"
        emitter.progress(event)
        checked = await verify(task, answer, rule_id)
        event.sandbox_ran = checked.ran
        event.sandbox_passed = checked.passed
        if checked.tokens:
            event.samples.append(
                Sample(status="done", tokens=checked.tokens, gpu_seconds=checked.gpu_seconds)
            )
        if checked.corrected:
            answer = checked.corrected      # the executed value wins over the stated one

    event.answer = (answer or "")[:600]
    event.correct = grade(task, answer)
    event.latency_ms = int((time.perf_counter() - started) * 1000)
    event.status = "done"
    event.ts = time.time()
    emitter.emit(event)

    event.__dict__["_agreement"] = agreement  # reporting only; not part of the contract
    return event


async def run_queue(
    tasks: list[Task], strategy: str = "ponder", emitter: Emitter | None = None, quiet: bool = False
) -> list[TaskEvent]:
    emitter = emitter or get_emitter()
    gate = asyncio.Semaphore(settings.max_concurrency)
    done = 0

    async def one(task: Task) -> TaskEvent:
        nonlocal done
        async with gate:
            event = await run_task(task, strategy, emitter)
        done += 1
        if not quiet:
            mark = "ok " if event.correct else "MISS"
            print(
                f"  [{done:>2}/{len(tasks)}] {mark} {task.id:4} {event.budget:5} "
                f"d={event.difficulty:.2f} s={event.stakes:.2f} "
                f"n={len(event.samples)} tok={event.total_tokens:>5} "
                f"gpu={event.total_gpu_seconds:6.2f}s"
                + ("  sandbox" + ("+" if event.sandbox_passed else "-") if event.sandbox_ran else "")
            )
        return event

    return list(await asyncio.gather(*(one(t) for t in tasks)))


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the Ponder loop over the task queue.")
    ap.add_argument("--strategy", choices=["cheap", "deep", "ponder"], default="ponder")
    ap.add_argument("--task", help="run a single task by id")
    ap.add_argument("--limit", type=int, help="run only the first N tasks")
    ap.add_argument("--fresh", action="store_true", help="truncate events.jsonl first")
    args = ap.parse_args()

    if args.fresh and EVENTS_PATH.exists():
        EVENTS_PATH.unlink()

    tasks = load_tasks()
    if args.task:
        tasks = [t for t in tasks if t.id == args.task] or tasks[:1]
    if args.limit:
        tasks = tasks[: args.limit]

    emitter = get_emitter()
    print(f"ponder :: {settings.describe()} :: sinks={'+'.join(emitter.active)}")
    print(f"strategy={args.strategy} tasks={len(tasks)}\n")

    events = asyncio.run(run_queue(tasks, args.strategy, emitter))

    correct = sum(1 for e in events if e.correct)
    tokens = sum(e.total_tokens for e in events)
    gpu = sum(e.total_gpu_seconds for e in events)
    print(
        f"\n{args.strategy}: {correct}/{len(events)} correct "
        f"({correct / len(events):.0%})  tokens={tokens:,}  gpu={gpu:.1f}s"
    )
    print(f"events -> {EVENTS_PATH}")


if __name__ == "__main__":
    main()
