"""Orchestration: triage -> budget -> spend -> aggregate -> grade -> emit.

One TaskEvent per task, fanned out to Logfire, Convex and events.jsonl by the
emitter. This module never talks to a sink directly.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections.abc import Awaitable, Callable

from agent.aggregate import majority
from agent.budget import Decision, decide
from agent.events import Emitter, GuardrailVerdict, Sample, TaskEvent, get_emitter, start_fresh
from agent.grader import grade
from agent.guardrails import check as check_guardrails
from agent.guardrails import check_input
from agent.rules import apply as apply_rules
from agent.settings import EVENTS_PATH, settings
from agent.tasks import Task, load_tasks
from agent.triage import Triage, triage
from agent.verify import verify
from agent.worker import WorkerResult, fan_out

from dotenv import load_dotenv

# How a task's compute is actually spent. `fan_out` is the default; anything with this
# shape can stand in, which is the whole extension point of the loop.
Sampler = Callable[[Task, str, str, int, tuple[str, ...]], Awaitable[list[WorkerResult]]]

load_dotenv()

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


async def run_task(
    task: Task,
    strategy: str = "ponder",
    emitter: Emitter | None = None,
    sampler: Sampler | None = None,
) -> TaskEvent:
    """One task, start to finish.

    `sampler` is the only seam: swap it and the *same* triage, rules, guardrails,
    verification and TaskEvent apply to a different model call. `agent/govern.py` uses
    it to police an agent it did not write, which is why there is no second pipeline
    for governed runs -- they are this one.
    """
    emitter = emitter or get_emitter()
    spend = sampler or fan_out
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

    # Scope is decided before anything is spent. A `block` here means no fan-out, no
    # sandbox and no tokens -- the refusal IS the finished task, so it emits its own
    # TaskEvent like any other and there is still exactly one per task.
    scope = check_input(decision.guardrails, task.prompt)
    if scope.blocked:
        event.guardrails = list(decision.guardrails)
        event.guardrail_verdicts = [GuardrailVerdict(**v.to_json()) for v in scope.verdicts]
        event.guardrail_blocked = True
        event.samples = []
        event.answer = f"[withheld by guardrail] {scope.block_message}"
        event.correct = None
        event.latency_ms = int((time.perf_counter() - started) * 1000)
        event.status = "done"
        event.ts = time.time()
        emitter.emit(event)
        return event

    results = await spend(task, decision.budget, rule_id, decision.samples, decision.guardrails)
    event.samples = [
        Sample(status="done" if r.ok else "failed", tokens=r.tokens, gpu_seconds=r.gpu_seconds)
        for r in results
    ]
    answer, agreement = majority(task, [r.text for r in results])
    emitter.progress(event)

    answer, rule_id = await _gate(task, event, decision, answer, rule_id, emitter, spend)

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

    if not event.guardrail_blocked:
        event.answer = (answer or "")[:600]
    event.correct = grade(task, answer)
    event.latency_ms = int((time.perf_counter() - started) * 1000)
    event.status = "done"
    event.ts = time.time()
    emitter.emit(event)

    event.__dict__["_agreement"] = agreement  # reporting only; not part of the contract
    return event


async def _gate(
    task: Task,
    event: TaskEvent,
    decision: Decision,
    answer: str,
    rule_id: str,
    emitter: Emitter,
    spend: Sampler,
) -> tuple[str, str]:
    """The guardrail gate on the answer best-of-N actually settled on.

    Per-call guardrails already ran inside every sample -- the framework attached them
    to the agent and retried the model where it could. This gate exists because none of
    those guards ever saw *this* string: the aggregate is chosen after they have all
    returned, and the aggregate is what the caller gets.

    What it does with a failure is the part that matters. A compliance filter's only
    move is to refuse. Ponder has another one: a guardrail trip on a cheap answer is
    evidence the task was underfunded, so the budget is escalated to deep and the
    fan-out is re-run. Thinking harder is a legitimate response to "this output is not
    good enough", and it is exactly the move a difficulty router cannot make, having
    already concluded the task was easy.

    Escalation fires at most once, and only upward from cheap. A deep answer that still
    trips a guard keeps its verdicts on the record and is allowed to stand: every one of
    its samples already had a framework-level retry, and re-running the widest budget on
    every failed check would burn the compute this project exists to save.
    """
    event.guardrails = list(decision.guardrails)
    if not decision.guardrails or not answer:
        return answer, rule_id

    report = check_guardrails(decision.guardrails, answer)
    event.guardrail_verdicts = [GuardrailVerdict(**v.to_json()) for v in report.verdicts]

    if report.blocked:
        event.guardrail_blocked = True
        event.answer = f"[withheld by guardrail] {report.block_message}"
        return "", rule_id

    if report.ok or decision.budget != "cheap":
        return answer, rule_id

    # Underfunded: buy the deep path and try again.
    tripped = ", ".join(v.name for v in report.failed)
    event.guardrail_escalated = True
    event.budget = "deep"
    rule_id = settings.rule_deep
    event.rule_id = rule_id
    event.rule_reason = (
        (event.rule_reason + " ") if event.rule_reason else ""
    ) + f"Guardrail {tripped} tripped on the cheap answer, so the budget was escalated to deep."
    event.status = "thinking"
    widened = max(decision.samples, settings.deep_samples)
    event.samples += [Sample(status="running") for _ in range(widened)]
    emitter.progress(event)

    retry = await spend(task, "deep", rule_id, widened, decision.guardrails)
    event.samples = event.samples[: -widened] + [
        Sample(status="done" if r.ok else "failed", tokens=r.tokens, gpu_seconds=r.gpu_seconds)
        for r in retry
    ]
    retried, _ = majority(task, [r.text for r in retry])
    if retried:
        answer = retried

    # The record keeps the verdicts of the answer that is actually returned.
    final = check_guardrails(decision.guardrails, answer)
    event.guardrail_verdicts = [GuardrailVerdict(**v.to_json()) for v in final.verdicts]
    if final.blocked:
        event.guardrail_blocked = True
        event.answer = f"[withheld by guardrail] {final.block_message}"
        return "", rule_id
    emitter.progress(event)
    return answer, rule_id


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

    if args.fresh:
        start_fresh()

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
