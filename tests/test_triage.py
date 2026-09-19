"""Triage must separate the quadrants from the prompt text alone."""

from agent.budget import decide
from agent.tasks import load_tasks
from agent.triage import heuristic_triage


def test_triage_never_sees_ground_truth():
    """Regression guard: triage takes a string, not a Task."""
    import inspect

    sig = inspect.signature(heuristic_triage)
    assert list(sig.parameters) == ["prompt"]


def test_clinical_prompts_score_high_stakes():
    t = heuristic_triage("A paediatric patient weighs 18 kg. The dose is 15 mg/kg. What is the dose in mg?")
    assert t.stakes > 0.8
    assert t.difficulty < 0.5, "a single multiplication should not read as hard"


def test_puzzles_score_low_stakes_even_when_priced_in_pounds():
    t = heuristic_triage(
        "A bat and a ball cost 1.10 pounds together. The bat costs 1.00 pound more than the "
        "ball. How many pence does the ball cost?"
    )
    assert t.stakes < 0.4, "money words alone are not consequence"


def test_every_high_stakes_task_is_routed_deep():
    for task in load_tasks():
        if task.stakes_tag != "high":
            continue
        scores = heuristic_triage(task.prompt)
        d = decide(scores.difficulty, scores.stakes, executable=task.kind == "exec")
        assert d.budget == "deep", f"{task.id} took the cheap path despite high stakes"


def test_trivial_tasks_stay_cheap():
    cheap = 0
    for task in load_tasks():
        if task.stakes_tag == "high" or task.hardness >= 0.5:
            continue
        scores = heuristic_triage(task.prompt)
        if decide(scores.difficulty, scores.stakes).budget == "cheap":
            cheap += 1
    assert cheap >= 11, "easy low-stakes work should not be escalated"
