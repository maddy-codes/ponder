"""One prompt in, one pondered answer out -- the drop-in entry point.

This is the whole public surface: `ponder(prompt)` has the shape of a plain model
call and returns the same answer plus the effort decision and the audit trail that
produced it. Mission Control's single-task box and the README's integration snippet
both go through here, and so does `python -m agent.ask "<prompt>"`.

There is no second pipeline. An ad-hoc prompt is wrapped as a Task and handed to the
same `run_task` the batch queue uses, so it triages, matches rules, spends, verifies
and emits its one TaskEvent exactly like every other task.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass

from agent.events import Emitter, TaskEvent
from agent.loop import run_task
from agent.tasks import Task

_CODE_ASK = re.compile(r"\b(write|implement|define)\b.{0,40}\b(python\s+)?function\b", re.I)
_EXACT_ASK = re.compile(r"^\s*(who|what|which|where|when)\b(?!.*\bhow many\b)", re.I)


def classify(prompt: str) -> str:
    """Best-effort kind for an ad-hoc prompt.

    Only aggregation and the choice of verification path depend on this, and both
    degrade gracefully when it guesses wrong -- unlike `answer`, which we refuse to
    invent.
    """
    if _CODE_ASK.search(prompt):
        return "exec"
    if _EXACT_ASK.match(prompt) and not re.search(r"\d", prompt):
        return "exact"
    return "numeric"


def as_task(prompt: str, task_id: str | None = None) -> Task:
    """Wrap a typed prompt as a Task with no reference answer and no held-out tags."""
    return Task(
        id=task_id or f"ask{int(time.time() * 1000) % 100_000_000}",
        prompt=prompt.strip(),
        answer="",              # nothing to grade against; grade() returns None
        kind=classify(prompt),  # type: ignore[arg-type]
    )


@dataclass
class PonderResult:
    """What a caller replacing a direct model call actually wants back."""

    answer: str
    budget: str
    matched_rule: str | None
    rule_reason: str | None
    verified: bool | None
    difficulty: float
    stakes: float
    samples: int
    tokens: int
    gpu_seconds: float
    latency_ms: int
    event: TaskEvent          # the full audit record, already emitted to all three sinks

    def __str__(self) -> str:
        rule = self.matched_rule or "—"
        return (f"{self.answer}\n  [{self.budget} · rule={rule} · "
                f"{self.tokens} tokens · {self.gpu_seconds:.2f} gpu-s]")


def _wrap(event: TaskEvent) -> PonderResult:
    return PonderResult(
        answer=event.answer or "",
        budget=event.budget,
        matched_rule=event.matched_rule,
        rule_reason=event.rule_reason,
        verified=event.sandbox_passed if event.sandbox_ran else None,
        difficulty=event.difficulty,
        stakes=event.stakes,
        samples=len(event.samples),
        tokens=event.total_tokens,
        gpu_seconds=event.total_gpu_seconds,
        latency_ms=event.latency_ms,
        event=event,
    )


async def ponder_async(prompt: str, task_id: str | None = None) -> PonderResult:
    return _wrap(await run_task(as_task(prompt, task_id), strategy="ponder"))


def ponder(prompt: str, task_id: str | None = None) -> PonderResult:
    """Synchronous drop-in for a direct model call."""
    return asyncio.run(ponder_async(prompt, task_id))


class StreamEmitter(Emitter):
    """Echo every stage the loop already publishes as one NDJSON line on stdout.

    `run_task` calls `progress()` at each REAL transition -- once the triage scores
    and the budget decision exist, once the fan-out has landed with its per-sample
    token and GPU numbers, and again around the sandbox. Mission Control's bench
    renders those lines, so a 50-second deep task reads as working rather than dead.

    This invents nothing and adds no second pipeline: the same TaskEvent still goes
    to the same three sinks through `super()`. Stdout is just a fourth reader, and
    the last line printed is always the final event -- so a caller that only wants
    the result can still take the last line and ignore the rest.
    """

    def progress(self, event: TaskEvent) -> None:
        super().progress(event)
        self._line(event, final=False)

    def emit(self, event: TaskEvent) -> TaskEvent:
        emitted = super().emit(event)
        self._line(emitted, final=True)
        return emitted

    @staticmethod
    def _line(event: TaskEvent, final: bool) -> None:
        # Totals are rolled up on the durable emit only, so do it on a copy here to
        # give the bench a running count without disturbing the real event.
        snapshot = event.model_copy(deep=True)
        snapshot.roll_up()
        payload = snapshot.model_dump()
        payload["final"] = final
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()



def main() -> None:
    ap = argparse.ArgumentParser(description="Ponder a single prompt.")
    ap.add_argument("prompt", help="the task to ponder")
    ap.add_argument("--id", help="override the generated task id")
    ap.add_argument("--json", action="store_true", help="print the TaskEvent as JSON (nothing else)")
    ap.add_argument(
        "--stream",
        action="store_true",
        help="emit one NDJSON line per stage as it happens; the last line is the final event",
    )
    args = ap.parse_args()

    if args.stream:
        # Same run_task, same sinks -- only the extra stdout reader differs.
        asyncio.run(
            run_task(as_task(args.prompt, args.id), strategy="ponder", emitter=StreamEmitter())
        )
        return

    result = ponder(args.prompt, args.id)
    print(result.event.model_dump_json() if args.json else result)


if __name__ == "__main__":
    main()
