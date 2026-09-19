"""An ordinary agent, then the same agent governed.

Run it:

    uv run python examples/governed_agent.py          # TestModel, no credentials needed
    PONDER_MODE=live uv run python examples/governed_agent.py

The point of this file is the diff between the two `Agent(...)` lines below, which is
nothing, and the one `govern(...)` line, which is everything. The support agent keeps
its own model, its own tools and its own prompt. What changes is that each question it
is asked is now triaged, matched against the domain policy in `agent/rules.json`, given
the compute that policy demands, guarded, and -- when the rule says so -- executed in a
sandbox before its answer is trusted.

Watch the third question in particular. It looks like arithmetic a 7B model does in one
cheap call, and a difficulty router would spend one cheap call on it. The policy knows
it is a dose.
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from pydantic_ai import Agent  # noqa: E402

from agent.govern import govern  # noqa: E402
from agent.settings import settings  # noqa: E402


def build_support_agent() -> Agent:
    """A perfectly ordinary Pydantic AI agent. Nothing here knows Ponder exists."""

    def order_total(order_id: str) -> str:
        """Look up the net total of an order."""
        return {"4471": "1029.00", "4472": "84.00"}.get(order_id, "unknown")

    if settings.live:
        from agent.worker import _gateway_model

        model = _gateway_model(settings.rule_deep)     # Gateway -> Modal-hosted model
    else:
        from pydantic_ai.models.test import TestModel

        model = TestModel(custom_output_text="270")    # deterministic, no credentials

    return Agent(
        model,
        system_prompt="You are a support agent. Answer the customer's question directly.",
        tools=[order_total],
    )


QUESTIONS = [
    "What is the capital of France?",
    "Order 4471 is 1029.00 net. What is the gross total at 20% VAT?",
    "A paediatric patient weighs 18 kg and the dose is 15 mg/kg. What is the dose in mg?",
]


async def main() -> None:
    support = build_support_agent()
    policed = govern(support)          # <- the whole integration

    print(f"ponder :: {settings.describe()}\n")
    for question in QUESTIONS:
        result = await policed.run(question)
        p = result.ponder
        rule = p.matched_rule or "—"
        verified = {True: "verified", False: "FAILED VERIFICATION", None: "not verified"}[p.verified]
        guards = ", ".join(result.event.guardrails) or "—"
        print(f"Q  {question}")
        print(f"A  {result.output}")
        print(
            f"   rule={rule}  budget={p.budget}  samples={p.samples}  {verified}\n"
            f"   guardrails={guards}"
            + (
                "  ESCALATED (a guardrail tripped, so it bought deep compute)"
                if result.event.guardrail_escalated
                else ""
            )
        )
        print(f"   {p.tokens} tokens · {p.gpu_seconds:.2f}s · receipt in events.jsonl\n")


if __name__ == "__main__":
    asyncio.run(main())
