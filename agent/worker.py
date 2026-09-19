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


def gateway_route(rule_id: str | None = None) -> str:
    """The BYOK provider name as created in the Gateway console (`route=` in the SDK).

    THE effort actuator. A Gateway Optimization is targeted at a route, so switching
    effort means asking for a different route -- not an `if` branch in this file, and
    not a header the Gateway never had. Point GATEWAY_ROUTE_CHEAP and _DEEP at two
    providers that front the SAME Modal endpoint, each carrying its own optimization.

    Kept separate from the model id on purpose: the model is a Hugging Face repo id like
    `google/gemma-4-31B-it`, so deriving a route by splitting on "/" would silently route
    to `google`. A wrong route returns a 404 that lists the valid names.
    """
    if rule_id == settings.rule_cheap and settings.route_cheap:
        return settings.route_cheap
    if rule_id is not None and rule_id != settings.rule_cheap and settings.route_deep:
        return settings.route_deep
    return settings.gateway_route


def _model_name() -> str:
    """The Hugging Face repo id, verbatim -- slashes and all."""
    return settings.gateway_model


_METADATA_WIDENED = False


def _widen_modal_metadata() -> None:
    """Modal returns `metadata.weight_versions` as a list; the OpenAI schema types
    `metadata` as `dict[str, str]`.

    Without this the request SUCCEEDS and the response is then thrown away as
    `UnexpectedModelBehavior: 1 validation error`. Both classes need widening because
    the payload passes through both: the SDK's serializes it, pydantic-ai's validates it.
    """
    global _METADATA_WIDENED
    if _METADATA_WIDENED:
        return
    from typing import Any

    from openai.types.chat import ChatCompletion
    from pydantic_ai.models.openai import _ChatCompletion

    for model in (ChatCompletion, _ChatCompletion):
        model.model_fields["metadata"].annotation = dict[str, Any] | None
        model.model_rebuild(force=True)
    _METADATA_WIDENED = True


def rule_headers(rule_id: str) -> dict[str, str]:
    """Ask the Gateway for a named rule.

    THE one integration point to confirm against your Gateway console: the SDK has no
    rule primitive, so the rule travels as a header. Sent per request rather than baked
    into the client, so one connection serves both rules. Set GATEWAY_RULE_HEADER to
    whatever your console expects, or to `off` to stop sending it.
    """
    import os

    header = os.environ.get("GATEWAY_RULE_HEADER", "X-Gateway-Rule").strip()
    return {} if header.lower() == "off" else {header: rule_id}


def _gateway_model(rule_id: str | None = None):
    """A model bound to the Gateway provider. Auth, the region-inferred base URL and
    the traceparent header all come from the SDK rather than being hand-rolled here."""
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.gateway import gateway_provider

    _widen_modal_metadata()
    route = gateway_route(rule_id)
    base = settings.gateway_base_url.rstrip("/")
    # The credentials file hands you the gateway root WITH the endpoint id already on
    # it. The SDK appends `route` to whatever base it is given, so pasting that value
    # verbatim yields /proxy/ep-xxx/ep-xxx and a "route not found" 404. Strip it back
    # to the root rather than making the reader debug a doubled path.
    if base.endswith("/" + route):
        base = base[: -(len(route) + 1)]
    provider = gateway_provider(
        # "openai-chat", not "openai": Modal implements /chat/completions but not
        # /responses, which the plain openai flavor would reach for.
        "openai-chat",
        route=route,
        api_key=settings.gateway_api_key,
        # Blank base_url means "infer from the key's region" (gateway-eu / gateway-us).
        base_url=base or None,
    )
    return OpenAIChatModel(_model_name(), provider=provider)


def _agent_for(rule_id: str):
    """One Pydantic AI agent per Gateway rule.

    The rule is the actuator: effort is selected by asking the Gateway for a rule, not
    by branching in this file.
    """
    if rule_id in _agents:
        return _agents[rule_id]

    from pydantic_ai import Agent

    system = _CHEAP_SYSTEM if rule_id == settings.rule_cheap else _DEEP_SYSTEM
    agent = Agent(_gateway_model(rule_id), system_prompt=system)
    _agents[rule_id] = agent
    return agent


async def _run(agent, prompt: str, ms: dict | None):
    """Run the agent, and fall back once if the endpoint rejects the effort parameter.

    A served model that has never seen `reasoning_effort` returns a 400 rather than
    ignoring it, and losing the whole sample to an optional parameter would be a
    silly way to fail a live demo. The rule header is KEPT on the retry: that one is
    load-bearing, so if the endpoint dislikes it we want the error rather than a
    silent downgrade to an unruled call that still looks like it worked.
    """
    if not ms:
        return await agent.run(prompt)
    try:
        return await agent.run(prompt, model_settings=ms)
    except Exception as exc:  # pragma: no cover - endpoint dependent
        bare = {k: v for k, v in ms.items() if k == "extra_headers"}
        if bare == ms:
            raise
        print(f"[worker] native effort parameter rejected, retrying without it: {str(exc)[:120]}")
        return await agent.run(prompt, model_settings=bare) if bare else await agent.run(prompt)


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


def _usage_of(result) -> int:
    """Total tokens for a run.

    `usage` is a property in pydantic-ai 2.x and was a method in 1.x; accept either so
    an SDK bump cannot silently zero out every token number on the dashboard.
    """
    usage = result.usage
    if callable(usage):
        usage = usage()
    return int(getattr(usage, "total_tokens", 0) or 0)


def call_settings(rule_id: str) -> dict:
    """Everything that rides on one live request: the Gateway rule header, plus the
    model's own effort parameter when PONDER_NATIVE_EFFORT is on."""
    out: dict = {}
    if headers := rule_headers(rule_id):
        out["extra_headers"] = headers
    if settings.native_effort:
        out.update(effort_settings(rule_id))
    return out


async def gateway_sample(task: Task, rule_id: str, seed: int) -> WorkerResult:
    agent = _agent_for(rule_id)
    started = time.perf_counter()
    try:
        result = await _run(agent, task.prompt, call_settings(rule_id))
    except Exception as exc:  # pragma: no cover - network dependent
        return WorkerResult("", 0, 0.0, ok=False, error=str(exc)[:200])
    elapsed = time.perf_counter() - started

    # The Modal endpoint is a dedicated single-GPU container, so the generation
    # wall-clock is the GPU time this request occupied.
    return WorkerResult(text=str(result.output), tokens=_usage_of(result), gpu_seconds=round(elapsed, 4))


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


_recompute: dict[str, object] = {}


def _recompute_agent():
    """The verifier's agent. Same Gateway route as the worker, different system prompt."""
    if "agent" not in _recompute:
        from pydantic_ai import Agent

        _recompute["agent"] = Agent(_gateway_model(settings.rule_deep), system_prompt=_RECOMPUTE_SYSTEM)
    return _recompute["agent"]


async def recompute_program(task: Task, rule_id: str, seed: int = 99) -> WorkerResult:
    """Ask the worker for a program that independently recomputes the answer."""
    if not settings.live:
        return await stub_recompute(task, seed)

    agent = _recompute_agent()
    started = time.perf_counter()
    try:
        result = await _run(agent, task.prompt, call_settings(rule_id))
    except Exception as exc:  # pragma: no cover
        return WorkerResult("", 0, 0.0, ok=False, error=str(exc)[:200])
    return WorkerResult(
        text=str(result.output),
        tokens=_usage_of(result),
        gpu_seconds=round(time.perf_counter() - started, 4),
    )
