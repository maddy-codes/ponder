"""Phase 1 evidence for the Pydantic prize.

Runs ONE task twice through Pydantic AI -> Pydantic AI Gateway -> the Modal-hosted
model: once with the default rule, once with a custom rule of yours. Captures both
Logfire trace ids and the token delta, and writes artifacts/rule_proof.json, which
Mission Control's evidence strip renders.

This refuses to run in stub mode on purpose. A prize submission needs real traces,
so it will not manufacture plausible-looking ones.

    uv run python scripts/prove_rule.py --task s01
"""

from __future__ import annotations

import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

import argparse
import asyncio
import json
import sys

from agent.settings import ARTIFACTS, settings
from agent.tasks import load_tasks
from agent.worker import gateway_sample


def _trace_url() -> tuple[str | None, str | None]:
    """Current trace id, and a link to it if LOGFIRE_PROJECT_URL is set."""
    try:
        from opentelemetry import trace

        ctx = trace.get_current_span().get_span_context()
        if not ctx or not ctx.trace_id:
            return None, None
        trace_id = format(ctx.trace_id, "032x")
    except Exception:
        return None, None
    if not settings.logfire_project_url:
        return trace_id, None
    base = settings.logfire_project_url.rstrip("/")
    return trace_id, f"{base}?q=trace_id%3D%27{trace_id}%27"


async def one_pass(task, rule_id: str, label: str) -> dict:
    import logfire

    with logfire.span("ponder.rule_proof {label}", label=label, rule_id=rule_id, task_id=task.id):
        result = await gateway_sample(task, rule_id, seed=0)
        trace_id, url = _trace_url()
        logfire.info("rule pass complete", tokens=result.tokens, rule_id=rule_id)

    if not result.ok:
        raise SystemExit(f"[prove_rule] {label} call failed: {result.error}")
    print(f"  {label:9} rule={rule_id:28} tokens={result.tokens:>6}  trace={trace_id}")
    return {
        "rule_id": rule_id,
        "tokens": result.tokens,
        "gpu_seconds": result.gpu_seconds,
        "trace_id": trace_id,
        "trace_url": url,
        "answer": result.text[:400],
    }


async def main_async(task_id: str) -> None:
    if not settings.live:
        sys.exit(
            "[prove_rule] needs live mode. Set PONDER_MODE=live, PYDANTIC_AI_GATEWAY_API_KEY "
            "and a Gateway model backed by your Modal endpoint.\n"
            "It will not fabricate trace links for a prize submission."
        )
    if not settings.use_logfire:
        sys.exit("[prove_rule] LOGFIRE_TOKEN is required -- the two trace links are the evidence.")

    import logfire

    logfire.configure(token=settings.logfire_token, service_name="ponder-rule-proof", console=False)
    logfire.instrument_pydantic_ai()

    task = next((t for t in load_tasks() if t.id == task_id), None)
    if task is None:
        sys.exit(f"[prove_rule] no task {task_id!r}")

    print(f"task {task.id}: {task.preview}\n")
    off = await one_pass(task, settings.rule_deep, "rule off")   # default reasoning behaviour
    on = await one_pass(task, settings.rule_cheap, "rule on")    # your custom answer-only rule

    delta = on["tokens"] - off["tokens"]
    pct = round(100 * delta / off["tokens"], 1) if off["tokens"] else 0.0
    proof = {"task": task.id, "prompt": task.prompt, "rule_off": off, "rule_on": on,
             "token_delta": delta, "token_delta_pct": pct}

    ARTIFACTS.mkdir(exist_ok=True)
    out = ARTIFACTS / "rule_proof.json"
    out.write_text(json.dumps(proof, indent=2))
    print(f"\ntoken delta: {delta:+} ({pct:+}%)\nwrote {out}")
    if not off["trace_url"]:
        print("note: set LOGFIRE_PROJECT_URL to turn the trace ids into clickable links.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="s01")
    asyncio.run(main_async(ap.parse_args().task))


if __name__ == "__main__":
    main()
