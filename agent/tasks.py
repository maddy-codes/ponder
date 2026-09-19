"""The evaluation queue."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from agent.settings import TASKS_PATH


class Task(BaseModel):
    id: str
    prompt: str
    answer: str
    kind: Literal["numeric", "exact", "exec"]
    stakes_tag: Literal["low", "med", "high"]
    hardness: float = 0.5           # ground truth for the stub worker ONLY; triage never reads it
    checks: list[str] = Field(default_factory=list)

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
