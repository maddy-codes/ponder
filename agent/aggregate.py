"""Best-of-N aggregation: majority vote over independently sampled answers."""

from __future__ import annotations

import re
from collections import Counter

from agent.grader import extract_code, extract_number
from agent.tasks import Task


def _key(task: Task, answer: str) -> str:
    if task.kind == "numeric":
        value = extract_number(answer)
        return "none" if value is None else f"{round(value, 6):g}"
    if task.kind == "exec":
        return re.sub(r"\s+", "", extract_code(answer))
    return re.sub(r"[^a-z0-9]+", " ", answer.lower()).strip()


def majority(task: Task, answers: list[str]) -> tuple[str, float]:
    """Return the winning answer and the share of samples that agreed with it.

    Agreement is a free confidence signal: N samples converging on one value is
    the reason best-of-N buys accuracy rather than just burning GPU.
    """
    usable = [a for a in answers if a and a.strip()]
    if not usable:
        return "", 0.0
    counts = Counter(_key(task, a) for a in usable)
    winner, votes = counts.most_common(1)[0]
    for answer in usable:
        if _key(task, answer) == winner:
            return answer, votes / len(usable)
    return usable[0], votes / len(usable)
