"""`govern()`: Ponder's policy in front of an agent it did not write."""

import asyncio
import json
from dataclasses import dataclass

import pytest

from agent.events import Emitter
from agent.govern import govern
from agent.rules import RULES_PATH, load_rules


class Quiet(Emitter):
    def __init__(self) -> None:
        self.events = []

    def emit(self, event):
        event.roll_up()
        self.events.append(event)
        return event

    def progress(self, event) -> None:
        pass


@dataclass
class Usage:
    total_tokens: int = 40


class Reply:
    def __init__(self, text: str) -> None:
        self.output = text
        self.usage = Usage()


class FakeAgent:
    """Stands in for a Pydantic AI Agent somebody else wrote."""

    def __init__(self, text: str = "The gross total is 1234.56") -> None:
        self.text = text
        self.calls: list[dict] = []

    async def run(self, prompt, **kw):
        self.calls.append(kw)
        return Reply(self.text)


CLINICAL = "A 24 kg child is prescribed 20 mg/kg per dose. What is a single dose in mg?"
# Matches the patient_record rule, whose guardrail BLOCKS rather than escalating.
RECORD = "Draft the discharge summary for the ward round."
TRIVIAL = "A blister pack holds 12 tablets. How many tablets are in 2 packs?"


def run(agent, prompt):
    emitter = Quiet()
    return asyncio.run(govern(agent).run(prompt, emitter=emitter))


def test_the_wrapped_agent_is_not_modified():
    agent = FakeAgent()
    governed = govern(agent)
    assert governed.agent is agent
    assert not hasattr(agent, "capabilities"), "govern must not mutate the caller's agent"


def test_guardrails_ride_on_the_per_run_parameter():
    """The guards reach a foreign agent without being baked into its definition."""
    agent = FakeAgent()
    run(agent, CLINICAL)
    assert all("capabilities" in call for call in agent.calls)


def test_a_rule_widens_a_foreign_agent_into_best_of_n():
    agent = FakeAgent()
    result = run(agent, CLINICAL)
    assert result.ponder.matched_rule == "paediatric_dose"
    assert result.ponder.budget == "deep"
    assert len(agent.calls) > 1, "the rule must buy real width, not just a label"


def test_a_trivial_task_still_costs_one_call():
    """Governing an agent must not tax the cheap path -- that is the whole thesis."""
    agent = FakeAgent("24")
    result = run(agent, TRIVIAL)
    assert result.ponder.budget == "cheap"
    assert len(agent.calls) == 1


def test_single_call_returns_the_agents_own_output_object():
    agent = FakeAgent("24")
    assert run(agent, TRIVIAL).output == "24"


def test_a_blocking_guardrail_withholds_the_answer():
    """A disclosure cannot be walked back, so this guard withholds instead of retrying."""
    agent = FakeAgent("Discharge summary complete. Contact the patient on 07700 900123.")
    result = run(agent, RECORD)
    assert result.event.guardrail_blocked
    assert "07700 900123" not in str(result.output)


def test_effort_off_stops_sending_model_settings():
    """A provider that rejects unknown settings must still be governable."""
    agent = FakeAgent("24")
    asyncio.run(govern(agent, effort=False).run(TRIVIAL, emitter=Quiet()))
    assert all(not call.get("model_settings") for call in agent.calls)


def test_a_governed_run_emits_exactly_one_durable_event():
    agent = FakeAgent()
    emitter = Quiet()
    asyncio.run(govern(agent).run(CLINICAL, emitter=emitter))
    assert len(emitter.events) == 1, "one task, one TaskEvent -- governed or not"
    assert emitter.events[0].strategy == "ponder"


def test_governing_uses_the_authored_policy_not_hardcoded_rules():
    """The rule that fired must be one that exists in the policy file."""
    result = run(FakeAgent(), CLINICAL)
    authored = {r.name for r in load_rules()}
    assert result.ponder.matched_rule in authored
    assert json.loads(RULES_PATH.read_text())["rules"], "rules.json is the source of truth"
