"""Executed verification for high-stakes answers.

Deliberately NOT the grader. The grader's assertions are held out; verification
only uses what the agent could legitimately produce for itself:

  * code answers   -> execute the code and confirm it actually defines a working
                      callable (syntax and import soundness, no assertions).
  * value answers  -> have the worker write a SECOND, independent program that
                      recomputes the value, execute it, and compare. A disagreement
                      is a caught error, and the executed value replaces the stated
                      one. This is the loop that makes "high stakes" mean something.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent.grader import extract_code, extract_number
from agent.sandbox import execute
from agent.tasks import Task
from agent.worker import recompute_program

_DEF = re.compile(r"^\s*def\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)


@dataclass
class Verification:
    ran: bool
    passed: bool | None
    detail: str
    corrected: str | None = None
    tokens: int = 0
    gpu_seconds: float = 0.0


async def verify(task: Task, answer: str, rule_id: str) -> Verification:
    if task.kind == "exec":
        code = extract_code(answer)
        names = _DEF.findall(code)
        if not names:
            return Verification(True, False, "no function defined in the answer")
        smoke = [f"assert callable({names[-1]}), 'not callable'"]
        result = execute(code, smoke)
        return Verification(True, result.passed, result.summary)

    first = await _derive(task, rule_id, seed=99)
    if first.value is None:
        return Verification(True, None, f"verifier produced no value ({first.detail})",
                            tokens=first.tokens, gpu_seconds=first.gpu_seconds)

    if _agrees(task, first.value, answer):
        return Verification(True, True, f"executed check produced {first.value!r}; stated answer agrees",
                            tokens=first.tokens, gpu_seconds=first.gpu_seconds)

    # Disagreement is not proof the answer is wrong -- the verifier can be the wrong
    # one. Break the tie with a second independent derivation instead of blindly
    # overriding, which would let a bad verifier corrupt a correct answer.
    second = await _derive(task, rule_id, seed=173)
    tokens = first.tokens + second.tokens
    gpu = round(first.gpu_seconds + second.gpu_seconds, 4)

    if second.value is not None and _agrees(task, second.value, answer):
        return Verification(True, True, f"verifiers split ({first.value!r} vs stated); "
                            "second derivation backed the stated answer",
                            tokens=tokens, gpu_seconds=gpu)

    if second.value is not None and _agrees(task, second.value, first.value):
        return Verification(True, False,
                            f"two independent executions both produced {first.value!r}, "
                            f"contradicting the stated answer",
                            corrected=f"Verified by execution: {first.value}",
                            tokens=tokens, gpu_seconds=gpu)

    return Verification(True, None, "verifiers disagreed with each other and with the answer; "
                        "keeping the sampled answer and flagging it",
                        tokens=tokens, gpu_seconds=gpu)


@dataclass
class _Derivation:
    value: str | None
    detail: str
    tokens: int = 0
    gpu_seconds: float = 0.0


async def _derive(task: Task, rule_id: str, seed: int) -> _Derivation:
    """One independent recompute-and-execute pass."""
    prog = await recompute_program(task, rule_id, seed=seed)
    if not prog.ok:
        return _Derivation(None, f"verifier call failed: {prog.error}")
    result = execute(extract_code(prog.text), [])
    printed = (result.stdout or "").replace("CHECKS_PASSED", "").strip().splitlines()
    value = printed[-1].strip() if printed else ""
    if not result.passed or not value:
        return _Derivation(None, result.summary, prog.tokens, prog.gpu_seconds)
    return _Derivation(value, result.summary, prog.tokens, prog.gpu_seconds)


def _agrees(task: Task, a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return False
    if task.kind == "numeric":
        x, y = extract_number(a), extract_number(b)
        return x is not None and y is not None and abs(x - y) <= max(0.005, abs(x) * 1e-6)
    return a.strip().lower() in b.strip().lower() or b.strip().lower() in a.strip().lower()
