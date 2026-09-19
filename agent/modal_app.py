"""Modal: the compute fabric. Three distinct jobs, all load-bearing.

  1. `serve`            - a dense single-GPU open-weight model behind an
                          OpenAI-compatible endpoint. This is what the Pydantic AI
                          Gateway points at as a BYOK provider.
  2. `sample_once` + `.map()`
                        - best-of-N at REQUEST time. "Think harder" becomes N real
                          containers, not a bigger prompt. Each container runs the
                          Pydantic AI agent against the Gateway, so the required call
                          path (agent -> Pydantic AI -> Gateway -> Modal model) holds
                          for every sample.
  3. `run_in_sandbox`   - executed verification of high-stakes answers in a
                          modal.Sandbox, isolated from the agent process.

Deploy:  modal deploy agent/modal_app.py
Serve:   the endpoint URL Modal prints goes in MODEL_ENDPOINT_URL and into the
         Gateway console as the BYOK base URL.
"""

from __future__ import annotations

import asyncio
import os
import time

import modal

APP_NAME = "ponder"

# Dense, single-GPU, instruct-tuned. Explicitly NOT an MoE model: an MoE risks
# sitting unscheduled waiting for a multi-GPU slot, which is the last thing you
# want during a timed demo.
MODEL_NAME = os.environ.get("PONDER_MODEL", "Qwen/Qwen2.5-7B-Instruct")
GPU = os.environ.get("PONDER_GPU", "A10G")
VLLM_PORT = 8000

app = modal.App(APP_NAME)

hf_cache = modal.Volume.from_name("ponder-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("ponder-vllm-cache", create_if_missing=True)

vllm_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm==0.8.5", "huggingface_hub[hf_transfer]==0.30.2")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "VLLM_USE_V1": "1"})
)

agent_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "pydantic-ai-slim[openai]>=0.0.30", "pydantic>=2.9", "logfire>=2.0",
        # The guardrail chain runs inside each fan-out container, so the harness has
        # to be in the image too -- the checks travel with the compute.
        "pydantic-ai-harness>=0.32",
        # agent.settings calls load_dotenv() at import, so every container needs it.
        "python-dotenv>=1.0",
    )
    .add_local_python_source("agent")
)

# Nothing but the standard library: the sandbox executes answers we do not trust.
sandbox_image = modal.Image.debian_slim(python_version="3.12")


# --------------------------------------------------------------------------- 1. serve


def _serve() -> None:
    """OpenAI-compatible endpoint. Point the Gateway's BYOK provider here."""
    import subprocess

    subprocess.Popen(
        [
            "vllm", "serve", MODEL_NAME,
            "--host", "0.0.0.0",
            "--port", str(VLLM_PORT),
            "--served-model-name", "ponder-worker",
            "--max-model-len", "8192",
            "--gpu-memory-utilization", "0.90",
        ]
    )


# Registering a GPU function needs a payment method on the workspace, and that one
# failure aborts the ENTIRE deploy -- taking the fan-out and sandbox down with it,
# neither of which needs a GPU. PONDER_SERVE_GPU=0 ships everything else meanwhile.
SERVE_GPU = os.environ.get("PONDER_SERVE_GPU", "1") not in {"0", "off", "false"}

if SERVE_GPU:
    serve = app.function(
        image=vllm_image,
        gpu=GPU,
        volumes={"/root/.cache/huggingface": hf_cache, "/root/.cache/vllm": vllm_cache},
        scaledown_window=15 * 60,
        timeout=60 * 60,
    )(modal.concurrent(max_inputs=32)(
        modal.web_server(port=VLLM_PORT, startup_timeout=15 * 60)(_serve)
    ))


# --------------------------------------------------------------------------- 2. fan-out


@app.function(
    image=agent_image,
    timeout=300,
    secrets=[modal.Secret.from_name("ponder-secrets", required_keys=[])],
    max_containers=16,
)
def sample_once(payload: dict) -> dict:
    """One best-of-N sample, in its own container.

    `.map()` over this is the runtime compute the deep path spends. GPU seconds are
    measured here, inside the container, so TaskEvent.samples carries real numbers
    rather than an estimate made by the orchestrator.
    """
    import asyncio as _asyncio

    from agent.tasks import Task
    from agent.worker import gateway_sample

    task = Task.model_validate(payload["task"])
    started = time.perf_counter()
    result = _asyncio.run(
        gateway_sample(
            task,
            payload["rule_id"],
            payload["seed"],
            tuple(payload.get("guardrails") or ()),
        )
    )
    return {
        "text": result.text,
        "tokens": result.tokens,
        "gpu_seconds": round(time.perf_counter() - started, 4),
        "ok": result.ok,
        "error": result.error,
        "blocked": result.blocked,
    }


def _fan_out_blocking(task_payload: dict, rule_id: str, n: int, guardrails: tuple) -> list[dict]:
    fn = modal.Function.from_name(APP_NAME, "sample_once")
    payloads = [
        {"task": task_payload, "rule_id": rule_id, "seed": i, "guardrails": list(guardrails)}
        for i in range(n)
    ]
    return list(fn.map(payloads))


async def remote_fan_out(task, rule_id: str, n: int, guardrails: tuple = ()):
    """Called by agent.worker.fan_out when Modal is live."""
    from agent.worker import WorkerResult

    raw = await asyncio.to_thread(
        _fan_out_blocking, task.model_dump(), rule_id, n, tuple(guardrails)
    )
    return [
        WorkerResult(
            text=r.get("text", ""),
            tokens=int(r.get("tokens", 0)),
            gpu_seconds=float(r.get("gpu_seconds", 0.0)),
            ok=bool(r.get("ok", True)),
            error=str(r.get("error", "")),
            blocked=bool(r.get("blocked", False)),
        )
        for r in raw
    ]


# --------------------------------------------------------------------------- 3. sandbox


def run_in_sandbox(program: str, timeout_s: int = 30):
    """Execute an untrusted candidate answer in a modal.Sandbox."""
    from agent.sandbox import ExecResult

    sb = modal.Sandbox.create(
        image=sandbox_image,
        app=modal.App.lookup(APP_NAME, create_if_missing=True),
        timeout=timeout_s,
        block_network=True,
    )
    try:
        proc = sb.exec("python", "-c", program)
        stdout, stderr = proc.stdout.read(), proc.stderr.read()
        proc.wait()
    finally:
        sb.terminate()
    return ExecResult("CHECKS_PASSED" in stdout, stdout, stderr, "modal-sandbox")


# --------------------------------------------------------------------------- local entry


@app.local_entrypoint()
def smoke() -> None:
    """modal run agent/modal_app.py -- proves fan-out and sandbox are both real."""
    print("sandbox:", run_in_sandbox("print('CHECKS_PASSED')").passed)
    results = _fan_out_blocking(
        {"id": "smoke", "prompt": "What is 2 + 2?", "answer": "4", "kind": "numeric",
         "stakes_tag": "low", "hardness": 0.05, "checks": []},
        os.environ.get("GATEWAY_RULE_CHEAP", "ponder-cheap-answer-only"),
        3,
    )
    for r in results:
        print(f"  sample tokens={r['tokens']} gpu={r['gpu_seconds']}s ok={r['ok']}")
