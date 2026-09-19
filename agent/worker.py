"""The worker-model seam.

Live:  Pydantic AI -> Pydantic AI Gateway -> Modal-hosted open-weight model.
Stub:  a deterministic simulator so the whole loop runs, and the dashboard can be
       built and rehearsed, with zero credentials. Same interface, same TaskEvent
       fields, so switching is a config change and not a code change.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import re
import time
from dataclasses import dataclass

from agent.settings import settings
from agent.tasks import Task


@dataclass
class WorkerResult:
    text: str
    tokens: int
    gpu_seconds: float
    ok: bool = True
    error: str = ""


# --------------------------------------------------------------------------- stub


def _rng(task_id: str, seed: int) -> random.Random:
    digest = hashlib.sha256(f"{task_id}:{seed}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def _corrupt(task: Task, rng: random.Random) -> str:
    """A plausible wrong answer -- the kind a small model actually produces."""
    if task.kind == "numeric":
        match = re.search(r"-?\d[\d,]*\.?\d*", task.answer)
        value = float(match.group().replace(",", "")) if match else 1.0
        slip = rng.choice([value * 10, value / 10, value + 1, value - 1, value * 2, value / 2])
        return f"Working through it, the answer is {round(slip, 2):g}."
    if task.kind == "exact":
        return rng.choice(["Sydney", "Ag", "1968", "analysis", "17:35", "no"])
    # exec: drop the edge case, or flip a boundary -- the classic near-miss
    code = task.answer
    for old, new in ((" <= ", " < "), ("0 < amount <= balance", "amount <= balance"),
                     ("if not cleaned:", "if False:"), ("if not xs:", "if False:")):
        if old in code:
            return f"```python\n{code.replace(old, new, 1)}\n```"
    return f"```python\n{code.replace('return', 'return None or', 1)}\n```"


STUB_NO_ANSWER = (
    "[stub worker] no completion available — this task was typed in live and has no "
    "reference answer for the simulator to imitate. Run with PONDER_MODE=live for the "
    "real model's answer; everything else on this card is real."
)


async def stub_sample(task: Task, budget: str, seed: int) -> WorkerResult:
    """Deterministic given (task id, seed). Deep costs ~10x the tokens of cheap."""
    rng = _rng(task.id, seed)
    deep = budget == "deep"

    if not task.has_reference:
        # Typed into Mission Control. The simulator mocks the worker model and nothing
        # else, so triage, the matched rule, the budget, the fan-out width and the
        # token/GPU accounting below are all genuine -- only the words are missing.
        tokens = max(12, int(rng.gauss(620, 140) if deep else rng.gauss(58, 14)))
        gpu_seconds = round(tokens / rng.uniform(55, 95), 4)
        await asyncio.sleep(gpu_seconds * 0.12)
        return WorkerResult(text=STUB_NO_ANSWER, tokens=tokens, gpu_seconds=gpu_seconds)

    # A cheap single pass degrades sharply with true hardness; the deep reasoning
    # rule recovers most of it, and best-of-N over independent seeds recovers more.
    p_correct = (1.0 - task.hardness) if not deep else (1.0 - task.hardness * 0.42)
    p_correct = min(0.97, max(0.04, p_correct))
    correct = rng.random() < p_correct

    tokens = int(rng.gauss(620, 140) if deep else rng.gauss(58, 14))
    tokens = max(12, tokens)
    gpu_seconds = round(tokens / rng.uniform(55, 95), 4)
    await asyncio.sleep(gpu_seconds * 0.12)  # keep the dashboard animation honest, but fast

    text = (f"The answer is {task.answer}." if task.kind != "exec"
            else f"```python\n{task.answer}\n```") if correct else _corrupt(task, rng)
    return WorkerResult(text=text, tokens=tokens, gpu_seconds=gpu_seconds)


# --------------------------------------------------------------------------- live

_CHEAP_SYSTEM = "Answer with the final answer only. No working, no explanation, no preamble."
_DEEP_SYSTEM = (
    "Reason carefully and step by step before answering. Check your arithmetic and your edge "
    "cases. Finish with the final answer on its own last line."
)

_agents: dict[str, object] = {}


def _agent_for(rule_id: str):
    """One Pydantic AI agent per Gateway rule.

    The rule is the actuator: effort is selected by asking the Gateway for a rule,
    not by branching in this file. `GATEWAY_RULE_HEADER` is the single integration
    point to confirm against your Gateway console.
    """
    if rule_id in _agents:
        return _agents[rule_id]

    import os

    from openai import AsyncOpenAI
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider

    header = os.environ.get("GATEWAY_RULE_HEADER", "X-Gateway-Rule")
    client = AsyncOpenAI(
        api_key=settings.gateway_api_key,
        base_url=settings.gateway_base_url,
        default_headers={header: rule_id},
    )
    model = OpenAIModel(settings.gateway_model, provider=OpenAIProvider(openai_client=client))
    system = _CHEAP_SYSTEM if rule_id == settings.rule_cheap else _DEEP_SYSTEM
    agent = Agent(model, system_prompt=system)
    _agents[rule_id] = agent
    return agent


async def _run(agent, prompt: str, effort: dict | None):
    """Run the agent, and fall back once if the endpoint rejects the effort parameter.

    A served model that has never seen `reasoning_effort` returns a 400 rather than
    ignoring it, and losing the whole sample to an optional parameter would be a
    silly way to fail a live demo.
    """
    if effort is None:
        return await agent.run(prompt)
    try:
        return await agent.run(prompt, model_settings=effort)
    except Exception as exc:  # pragma: no cover - endpoint dependent
        print(f"[worker] native effort parameter rejected, retrying without it: {str(exc)[:120]}")
        return await agent.run(prompt)


def effort_settings(rule_id: str) -> dict:
    """The model's OWN reasoning control, set from the same rule that set ours.

    Ponder sits *above* provider-level effort parameters rather than duplicating
    them: selecting a Gateway rule is what decides the setting, and the setting is
    passed through to whatever the served model exposes. Best-effort by design --
    many open-weight models expose nothing here, and the deep path is still deep
    without it because the rule and the fan-out are doing the work.
    """
    deep = rule_id != settings.rule_cheap
    return {
        "openai_reasoning_effort": "high" if deep else "low",
        # vLLM's passthrough for hybrid-reasoning chat templates (Qwen3 et al).
        "extra_body": {"chat_template_kwargs": {"enable_thinking": deep}},
    }


async def gateway_sample(task: Task, rule_id: str, seed: int) -> WorkerResult:
    agent = _agent_for(rule_id)
    started = time.perf_counter()
    effort = effort_settings(rule_id) if settings.native_effort else None
    try:
        result = await _run(agent, task.prompt, effort)
    except Exception as exc:  # pragma: no cover - network dependent
        return WorkerResult("", 0, 0.0, ok=False, error=str(exc)[:200])
    elapsed = time.perf_counter() - started

    usage = result.usage()
    tokens = int(getattr(usage, "total_tokens", 0) or 0)
    # The Modal endpoint is a dedicated single-GPU container, so the generation
    # wall-clock is the GPU time this request occupied.
    return WorkerResult(text=str(result.output), tokens=tokens, gpu_seconds=round(elapsed, 4))


# --------------------------------------------------------------------------- entry


async def sample(task: Task, budget: str, rule_id: str, seed: int = 0) -> WorkerResult:
    if settings.live:
        return await gateway_sample(task, rule_id, seed)
    return await stub_sample(task, budget, seed)


async def fan_out(task: Task, budget: str, rule_id: str, n: int) -> list[WorkerResult]:
    """Best-of-N.

    Live with Modal: the N samples are dispatched across Modal containers
    (`modal_app.sample_batch` -> `.map()`), which is the runtime compute the Modal
    prize is about. Otherwise they run concurrently through the same seam.
    """
    if n <= 1:
        return [await sample(task, budget, rule_id, seed=0)]

    if settings.use_modal:
        try:
            from agent.modal_app import remote_fan_out

            return await remote_fan_out(task, rule_id, n)
        except Exception as exc:  # pragma: no cover
            print(f"[worker] modal fan-out unavailable, running locally: {exc}")

    return list(await asyncio.gather(*(sample(task, budget, rule_id, seed=i) for i in range(n))))


# --------------------------------------------------------------------------- verification

_RECOMPUTE_SYSTEM = (
    "Write a short Python program that recomputes the answer to the task from first "
    "principles and prints ONLY the final value, nothing else. No explanation, no comments. "
    "Output a single ```python code block."
)


async def stub_recompute(task: Task, seed: int) -> WorkerResult:
    """Simulated second derivation. Independent of the first pass, so it usually
    disagrees with a wrong answer -- which is the point of verifying."""
    rng = _rng(task.id + ":verify", seed)
    if not task.has_reference:
        # Nothing to recompute against; verify() reports this as inconclusive rather
        # than inventing a verdict.
        return WorkerResult("", 0, 0.0, ok=False, error="stub verifier has no reference to recompute")
    right = rng.random() < 0.86
    value = task.answer if right else _corrupt(task, rng)
    literal = repr(value.strip())
    tokens = max(20, int(rng.gauss(150, 30)))
    await asyncio.sleep(0.02)
    return WorkerResult(
        text=f"```python\nprint({literal})\n```",
        tokens=tokens,
        gpu_seconds=round(tokens / rng.uniform(55, 95), 4),
    )


async def recompute_program(task: Task, rule_id: str, seed: int = 99) -> WorkerResult:
    """Ask the worker for a program that independently recomputes the answer."""
    if not settings.live:
        return await stub_recompute(task, seed)

    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider
    import os

    from openai import AsyncOpenAI

    header = os.environ.get("GATEWAY_RULE_HEADER", "X-Gateway-Rule")
    client = AsyncOpenAI(
        api_key=settings.gateway_api_key,
        base_url=settings.gateway_base_url,
        default_headers={header: rule_id},
    )
    agent = Agent(
        OpenAIModel(settings.gateway_model, provider=OpenAIProvider(openai_client=client)),
        system_prompt=_RECOMPUTE_SYSTEM,
    )
    started = time.perf_counter()
    try:
        result = await _run(agent, task.prompt, effort_settings(rule_id) if settings.native_effort else None)
    except Exception as exc:  # pragma: no cover
        return WorkerResult("", 0, 0.0, ok=False, error=str(exc)[:200])
    usage = result.usage()
    return WorkerResult(
        text=str(result.output),
        tokens=int(getattr(usage, "total_tokens", 0) or 0),
        gpu_seconds=round(time.perf_counter() - started, 4),
    )
