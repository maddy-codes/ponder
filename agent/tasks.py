"""The evaluation queue."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from agent.settings import TASKS_PATH


class Task(BaseModel):
    id: str
    prompt: str
    # Empty for a task typed into Mission Control: there is no held-out answer to
    # grade against, and saying so is better than scoring it against nothing.
    answer: str = ""
    kind: Literal["numeric", "exact", "exec"] = "numeric"
    stakes_tag: Literal["low", "med", "high"] = "low"
    hardness: float = 0.5           # ground truth for the stub worker ONLY; triage never reads it
    checks: list[str] = Field(default_factory=list)

    @property
    def has_reference(self) -> bool:
        """False for an ad-hoc task. Grading and stub simulation both need to know."""
        return bool(self.answer.strip())

    @property
    def preview(self) -> str:
        p = " ".join(self.prompt.split())
        return p if len(p) <= 110 else p[:107] + "..."


def load_tasks(path=TASKS_PATH) -> list[Task]:
    tasks: list[Task] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            tasks.append(Task.model_validate(json.loads(line)))
    return tasks
