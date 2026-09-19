"""The named-rule layer: a written policy, sitting above the numeric score."""

import pytest

from agent.ask import as_task, classify
from agent.budget import decide
from agent.grader import grade
from agent.loop import plan
from agent.rules import apply, load_rules, match_rule
from agent.settings import settings
from agent.tasks import load_tasks
from agent.triage import heuristic_triage

TASKS = {t.id: t for t in load_tasks()}


def test_rule_names_are_unique_and_stated():
    rules = load_rules()
    names = [r.name for r in rules]
    assert len(names) == len(set(names))
    assert all(r.reason and r.force_budget in {"cheap", "deep"} for r in rules)


def test_dispensing_rule_overrides_a_cheap_score():
    """Change 1's whole point: the policy outranks the classifier.

    A vial-strength question carries no word the stakes heuristic recognises, so the
    score says cheap. The named rule knows that transposing strength and volume is how
    people get the wrong dose, and buys the deep path anyway.
    """
    prompt = "The vial contains 2 g. How many 500 mg portions does that give?"
    scores = heuristic_triage(prompt)
    scored = decide(scores.difficulty, scores.stakes)
    assert scored.budget == "cheap", "this prompt must look cheap to the score"

    final = apply(prompt, scored)
    assert final.matched_rule == "dose_dispensing"
    assert final.budget == "deep" and final.sandbox, "a named rule must buy deep + verify"
    assert "would have spent cheap" in final.rule_reason


def test_an_estimate_noun_without_a_figure_is_not_an_estimate():
    assert match_rule("How does a rough estimate differ from a precise one?") is None


def test_escalating_rules_outrank_the_lookup_rule():
    """A dose question phrased as a lookup still escalates -- order is safety-first."""
    rule = match_rule("What does the abbreviation mg/kg stand for in paediatric dosing?")
    assert rule is not None and rule.name == "paediatric_dose"


def test_lookup_rule_keeps_reference_questions_cheap():
    final = apply("What is the chemical symbol for potassium?", decide(0.1, 0.12))
    assert final.matched_rule == "clinical_reference"
    assert final.budget == "cheap" and not final.sandbox and final.samples == 1


def test_no_match_leaves_the_spend_decision_untouched():
    """No rule means the score still owns the spend. Only scope rides along, because
    an off-topic prompt is by definition the one no clinical rule claims."""
    scored = decide(0.9, 0.1)
    final = apply("A box of gloves and a box of masks cost 11.00 pounds.", scored)
    assert (final.budget, final.sandbox, final.samples) == (
        scored.budget, scored.sandbox, scored.samples
    )
    assert final.matched_rule is None and final.rule_reason is None
    assert final.guardrails == ("health_topics_only",), "scope applies with no rule"


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
    task = TASKS["e02"]  # matches clinical_reference
    assert match_rule(task.prompt) is not None
    for strategy, budget in (("cheap", "cheap"), ("deep", "deep")):
        _, decision = plan(task, strategy)
        assert decision.budget == budget and decision.matched_rule is None


def test_ponder_records_the_rule_on_the_event_contract():
    _, decision = plan(TASKS["s01"], "ponder")
    assert decision.matched_rule == "paediatric_dose" and decision.rule_reason


# --- ad-hoc tasks ---------------------------------------------------------


def test_ad_hoc_task_has_no_reference_and_is_not_graded_as_wrong():
    task = as_task("What is the running total after a 250 mg portion is removed?")
    assert not task.has_reference
    assert grade(task, "anything at all") is None, "unknown must not be reported as a miss"


def test_reference_tasks_still_grade():
    assert grade(TASKS["s01"], TASKS["s01"].answer) is True


@pytest.mark.parametrize(
    "prompt,kind",
    [
        ("Write a Python function `f(x)` that doubles x.", "exec"),
        ("What does the abbreviation BNF stand for?", "exact"),
        ("A 24 kg child is dosed at 20 mg/kg. What is the dose?", "numeric"),
    ],
)
def test_classify_picks_a_usable_kind(prompt, kind):
    assert classify(prompt) == kind


def test_ad_hoc_task_flows_through_the_same_plan():
    task = as_task("The vial contains 2 g. How many 500 mg portions does that give?")
    _, decision = plan(task, "ponder")
    assert decision.matched_rule == "dose_dispensing" and decision.budget == "deep"
