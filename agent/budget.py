"""budget = f(difficulty, stakes).

The whole thesis lives in this function: stakes can override difficulty, so an
easy-LOOKING task with real consequences still gets deep compute. A difficulty
router gets exactly that case backwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agent.settings import settings

Budget = Literal["cheap", "deep"]


@dataclass
class Decision:
    budget: Budget
    reason: Literal["trivial", "difficulty", "stakes-override", "both"]
    sandbox: bool
    samples: int

    @property
    def is_money_shot(self) -> bool:
        return self.reason == "stakes-override"


def decide(difficulty: float, stakes: float, executable: bool = False) -> Decision:
    hard = difficulty >= settings.difficulty_deep
    consequential = stakes >= settings.stakes_override

    if hard and consequential:
        reason = "both"
    elif hard:
        reason = "difficulty"
    elif consequential:
        reason = "stakes-override"   # the money shot
    else:
        reason = "trivial"

    budget: Budget = "cheap" if reason == "trivial" else "deep"
    # Executable answers always get executed: verification is nearly free and it is
    # exactly what a sandbox is for.
    sandbox = budget == "deep" and (stakes >= settings.sandbox_stakes or executable)
    # Consequence buys width: the more it costs to be wrong, the more samples.
    samples = 1 if budget == "cheap" else settings.deep_samples + (2 if consequential else 0)
    return Decision(budget=budget, reason=reason, sandbox=sandbox, samples=samples)
