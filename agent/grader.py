"""Plain-Python grading: exact match, numeric match, or an executed check."""

from __future__ import annotations

import re

from agent.sandbox import execute
from agent.tasks import Task

_NUM = re.compile(r"-?\d[\d,]*\.?\d*")
_CODE_FENCE = re.compile(r"```(?:python|py)?\s*(.*?)```", re.DOTALL)


def extract_code(answer: str) -> str:
    """Models fence their code; graders should not care."""
    blocks = _CODE_FENCE.findall(answer or "")
    return (blocks[-1] if blocks else (answer or "")).strip()


def extract_number(text: str) -> float | None:
    """Take the last number in the response -- models restate the working first."""
    matches = _NUM.findall((text or "").replace("£", "").replace("$", ""))
    for raw in reversed(matches):
        try:
            return float(raw.replace(",", ""))
        except ValueError:
            continue
    return None


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9:.]+", " ", (text or "").lower()).strip()


def grade(task: Task, answer: str | None) -> bool | None:
    """None means "no reference to grade against" -- an ad-hoc task is not a miss."""
    if not task.has_reference:
        return None
    if not answer:
        return False
    if task.kind == "numeric":
        got = extract_number(answer)
        want = extract_number(task.answer)
        if got is None or want is None:
            return False
        return abs(got - want) <= max(0.005, abs(want) * 1e-6)
    if task.kind == "exact":
        got, want = _normalise(answer), _normalise(task.answer)
        return got == want or want in got.split() or got.endswith(want)
    if task.kind == "exec":
        return execute(extract_code(answer), task.checks).passed
    raise ValueError(f"unknown task kind: {task.kind}")
