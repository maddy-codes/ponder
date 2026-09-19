"""The named-rule layer: a written policy, sitting above the numeric score."""

import pytest

from agent.ask import as_task, classify
from agent.budget import decide
from agent.grader import grade
from agent.loop import plan
from agent.rules import DOMAIN_RULES, apply, match_rule
from agent.settings import settings
from agent.tasks import load_tasks
from agent.triage import heuristic_triage

TASKS = {t.id: t for t in load_tasks()}


def test_rule_names_are_unique_and_stated():
    names = [r.name for r in DOMAIN_RULES]
    assert len(names) == len(set(names))
    assert all(r.reason and r.force_budget in {"cheap", "deep"} for r in DOMAIN_RULES)


def test_financial_rule_overrides_a_cheap_score():
    """Change 1's whole point: the policy outranks the classifier."""
    prompt = "What is the total cost of 3 items at 4.50 each?"
    scores = heuristic_triage(prompt)
    scored = decide(scores.difficulty, scores.stakes)
    assert scored.budget == "cheap", "this prompt must look cheap to the score"

    final = apply(prompt, scored)
    assert final.matched_rule == "financial_total"
    assert final.budget == "deep" and final.sandbox, "a named rule must buy deep + verify"
    assert "would have spent cheap" in final.rule_reason


def test_a_money_noun_without_a_figure_is_not_a_total():
    assert match_rule("How does a ledger work in double-entry bookkeeping?") is None


def test_escalating_rules_outrank_the_lookup_rule():
    """A dose question phrased as a lookup still escalates -- order is safety-first."""
    rule = match_rule("What year was the paediatric paracetamol dose of 15 mg/kg adopted?")
    assert rule is not None and rule.name == "clinical_dose"


def test_lookup_rule_keeps_trivia_cheap():
    final = apply("What is the capital of Australia?", decide(0.1, 0.12))
    assert final.matched_rule == "casual_lookup"
    assert final.budget == "cheap" and not final.sandbox and final.samples == 1


def test_no_match_leaves_the_scored_decision_untouched():
    scored = decide(0.9, 0.1)
    assert apply("A bat and a ball cost 1.10 pounds together.", scored) is scored


def test_rules_never_weaken_the_queue():
    """Regression guard: no rule may take compute away from a high-stakes task."""
    for task in load_tasks():
        scores = heuristic_triage(task.prompt)
        executable = task.kind == "exec"
        scored = decide(scores.difficulty, scores.stakes, executable=executable)
        final = apply(task.prompt, scored, executable=executable)
        if task.stakes_tag == "high":
            assert final.budget == "deep" and final.sandbox, task.id
        assert final.samples >= scored.samples or final.budget == "cheap", task.id


def test_baselines_never_see_the_rules():
    """An always-deep baseline that consulted a cheap rule would stop being a baseline."""
    task = TASKS["e02"]  # matches casual_lookup
    assert match_rule(task.prompt) is not None
    for strategy, budget in (("cheap", "cheap"), ("deep", "deep")):
        _, decision = plan(task, strategy)
        assert decision.budget == budget and decision.matched_rule is None


def test_ponder_records_the_rule_on_the_event_contract():
    _, decision = plan(TASKS["s01"], "ponder")
    assert decision.matched_rule == "clinical_dose" and decision.rule_reason


# --- ad-hoc tasks ---------------------------------------------------------


def test_ad_hoc_task_has_no_reference_and_is_not_graded_as_wrong():
    task = as_task("What is the closing balance after a 250 pound transfer?")
    assert not task.has_reference
    assert grade(task, "anything at all") is None, "unknown must not be reported as a miss"


def test_reference_tasks_still_grade():
    assert grade(TASKS["s01"], TASKS["s01"].answer) is True


@pytest.mark.parametrize(
    "prompt,kind",
    [
        ("Write a Python function `f(x)` that doubles x.", "exec"),
        ("Who wrote Bleak House?", "exact"),
        ("An invoice is 1,240 net. Add VAT at 20%.", "numeric"),
    ],
)
def test_classify_picks_a_usable_kind(prompt, kind):
    assert classify(prompt) == kind


def test_ad_hoc_task_flows_through_the_same_plan():
    task = as_task("What is the total cost of 3 items at 4.50 each?")
    _, decision = plan(task, "ponder")
    assert decision.matched_rule == "financial_total" and decision.budget == "deep"
