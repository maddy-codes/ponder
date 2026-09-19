"""`govern()` -- put Ponder's policy in front of an agent somebody else already wrote.

Everything else in this repo is Ponder deciding how hard *its own* worker should think.
That is the demo. This module is the product: an existing Pydantic AI agent, with its
own model, tools and prompts, wrapped so that every call it makes is triaged, policed
by the domain rules, guarded, and -- when the stakes justify it -- widened into a
best-of-N fan-out and executed in a sandbox before its answer is trusted.

    from pydantic_ai import Agent
    from agent.govern import govern

    support = Agent("openai:gpt-5", tools=[lookup_order, issue_refund])   # unchanged
    support = govern(support)                                            # one line

    result = support.run_sync("Refund invoice 4471 -- what's the VAT-inclusive total?")
    result.output                 # the answer, as before
    result.ponder.matched_rule    # 'financial_total'
    result.ponder.budget          # 'deep'   -- the rule overrode the easy-looking score
    result.ponder.verified        # True     -- recomputed in a Modal sandbox
    result.ponder.guardrails      # ('numeric_answer_present', 'no_hedging', ...)

Three things make this more than a retry wrapper:

* **The agent is not modified.** Guardrails ride on Pydantic AI's per-run `capabilities`
  parameter and effort rides on `model_settings`, so a governed agent is the same object
  it was -- no subclass, no re-registration of its tools, no second definition to keep in
  sync. Hand it back ungoverned and it behaves exactly as it did.
* **There is no second pipeline.** `govern` supplies a *sampler* to the same `run_task`
  the batch queue runs. Identical triage, identical rules, identical guardrail gate,
  identical sandbox, and one TaskEvent to the same three sinks -- so a governed call
  shows up in Mission Control next to everything else, with the same audit trail and the
  same decision receipt.
* **Policy is not code.** The rules live in `agent/rules.json` and are edited in the
  dashboard. Governing a new domain is authoring a rule, not shipping a release.

What it costs the caller: a cheap-budget call is one call, the same as before. Only a
task the policy says is consequential pays for width and verification.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from agent.ask import PonderResult, as_task, _wrap
from agent.events import Emitter, TaskEvent
from agent.loop import run_task
from agent.tasks import Task
from agent.worker import WorkerResult, _run, call_settings
from agent.guardrails import capabilities


@dataclass
class GovernedResult:
    """What the caller gets back: their result, plus why it cost what it cost."""

    output: Any
    ponder: PonderResult
    runs: list[Any]

    @property
    def event(self) -> TaskEvent:
        """The full audit record, already emitted to Logfire, Convex and events.jsonl."""
        return self.ponder.event

    def __str__(self) -> str:
        return str(self.output)


class GovernedAgent:
    """A Pydantic AI agent with Ponder's policy layer in front of it.

    Holds a reference to the caller's agent and never mutates it.
    """

    def __init__(self, agent: Any, *, effort: bool = True) -> None:
        self.agent = agent
        # Pass the Gateway rule header and the model's own reasoning parameter through to
        # the governed agent. On by default because that is the point -- the rule should
        # reach the model. Turn it off for a provider that rejects unknown settings and
        # the policy still controls width, verification and guardrails.
        self.effort = effort
        self._last: list[Any] = []

    def _sampler(self):
        async def sample_one(
            task: Task, rule_id: str, guardrails: tuple[str, ...]
        ) -> tuple[WorkerResult, Any]:
            started = time.perf_counter()
            ms = call_settings(rule_id) if self.effort else {}
            try:
                result = await _run(self.agent, task.prompt, ms, capabilities(guardrails))
            except Exception as exc:
                blocked = type(exc).__name__ == "OutputBlocked"
                return (
                    WorkerResult("", 0, 0.0, ok=False, error=str(exc)[:200], blocked=blocked),
                    None,
                )
            elapsed = round(time.perf_counter() - started, 4)
            tokens = 0
            usage = getattr(result, "usage", None)
            if usage is not None:
                usage = usage() if callable(usage) else usage
                tokens = int(getattr(usage, "total_tokens", 0) or 0)
            # `gpu_seconds` is wall-clock here: a governed agent may be talking to a
            # provider we do not host, so this is the honest reading of that field
            # rather than a GPU number we cannot measure.
            return WorkerResult(str(result.output), tokens, elapsed), result

        async def spend(
            task: Task, budget: str, rule_id: str, n: int, guardrails: tuple[str, ...]
        ) -> list[WorkerResult]:
            pairs = await asyncio.gather(
                *(sample_one(task, rule_id, guardrails) for _ in range(max(1, n)))
            )
            self._last = [raw for _, raw in pairs if raw is not None]
            return [r for r, _ in pairs]

        return spend

    async def run(
        self, user_prompt: str, *, task_id: str | None = None, emitter: Emitter | None = None
    ) -> GovernedResult:
        self._last = []
        event = await run_task(
            as_task(user_prompt, task_id), "ponder", emitter, sampler=self._sampler()
        )
        result = _wrap(event)
        # One sample means one real run, so the caller keeps their agent's own output
        # object -- typed outputs and all. Best-of-N has to agree across samples, and
        # agreement is decided on the answer text, so a widened task returns the text.
        output: Any = self._last[0].output if len(self._last) == 1 else result.answer
        if event.guardrail_blocked:
            output = event.answer
        return GovernedResult(output=output, ponder=result, runs=list(self._last))

    def run_sync(self, user_prompt: str, *, task_id: str | None = None) -> GovernedResult:
        return asyncio.run(self.run(user_prompt, task_id=task_id))


def govern(agent: Any, *, effort: bool = True) -> GovernedAgent:
    """Wrap an existing Pydantic AI agent in Ponder's policy layer.

    `effort=False` stops Ponder passing the Gateway rule header and the provider's own
    reasoning parameter to the governed agent, for a provider that rejects settings it
    does not recognise. The rules still choose the budget, the width, the sandbox and
    the guardrails; only the per-call effort dial goes quiet.
    """
    return GovernedAgent(agent, effort=effort)
